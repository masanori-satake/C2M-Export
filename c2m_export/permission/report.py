"""権限レポート出力 (report) モジュール.

`PermissionReport` インスタンスから Markdown および JSON 形式のレポートを生成し、
指定されたレイアウト（集約 `aggregate` または各ページ分散 `per_page`）で出力する純粋関数ロジック。
"""

import json
import logging
import os
from typing import List

from c2m_export.permission.models import PagePermission, PermissionReport

logger = logging.getLogger(__name__)

DISCLAIMER_NOTE = """> **【重要】権限レポートに関する注意点**
> 1. 本レポートは Confluence 上で設定されていたコンテンツ制限（アクセス権限）の記録であり、移行先サービス（SharePoint / OneDrive 等）へアクセス権限を自動適用するものではありません。
> 2. 親ページからの「継承権限」の実効展開は行っていません。個別制限が設定されていないページは「継承/制限なし」と表記されます。個別制限が「あり」となっている箇所が、管理者が意図的にアクセス権限を変更した対象です。
"""


def format_holders(users: List[str], groups: List[str]) -> str:
    """ユーザーおよびグループのリストを表示用文字列にフォーマットする."""
    items = []
    if users:
        items.append("ユーザー: " + ", ".join(users))
    if groups:
        items.append("グループ: " + ", ".join(groups))
    if not items:
        return "—"
    return " / ".join(items)


def generate_aggregate_markdown(report: PermissionReport) -> str:
    """集約レイアウト用の Markdown 文字列を生成する."""
    lines = ["# Confluence ページアクセス権限一覧（集約レポート）", "", DISCLAIMER_NOTE, ""]

    lines.append("| ページ | 個別制限 | Read (閲覧) | Read+Write (閲覧・編集) | Confluence URL | 相対パス |")
    lines.append("|---|---|---|---|---|---|")

    for page in report.pages:
        if page.fetch_failed:
            explicit_str = f"取得失敗 ({page.fail_reason})"
            read_str = "—"
            readwrite_str = "—"
        else:
            explicit_str = "**あり**" if page.has_explicit else "継承/制限なし"
            read_str = format_holders(page.read_users, page.read_groups)
            readwrite_str = format_holders(page.readwrite_users, page.readwrite_groups)

        rel_path_str = page.rel_path if page.rel_path else "—"
        title_esc = page.title.replace("|", "\\|")
        url_link = f"[{page.page_id}]({page.url})"

        lines.append(f"| {title_esc} | {explicit_str} | {read_str} | {readwrite_str} | {url_link} | {rel_path_str} |")

    lines.append("")
    return "\n".join(lines)


def generate_per_page_markdown(page: PagePermission) -> str:
    """各ページ分散配置用の Markdown 文字列を生成する."""
    lines = [
        f"# アクセス権限レポート: {page.title}",
        "",
        DISCLAIMER_NOTE,
        "",
        f"- **ページ ID**: `{page.page_id}`",
        f"- **Space Key**: `{page.space_key}`",
        f"- **Confluence URL**: {page.url}",
    ]

    if page.rel_path:
        lines.append(f"- **ローカル相対パス**: `{page.rel_path}`")

    if page.fetch_failed:
        lines.extend(
            [
                "- **取得状態**: 失敗",
                f"- **失敗理由**: {page.fail_reason}",
            ]
        )
    else:
        explicit_str = "あり (個別コンテンツ制限設定あり)" if page.has_explicit else "なし (親権限を継承または制限なし)"
        lines.extend(
            [
                f"- **個別制限**: {explicit_str}",
                "",
                "## 権限保有者一覧",
                "",
                "### Read 権（閲覧のみ）",
                f"- {format_holders(page.read_users, page.read_groups)}",
                "",
                "### Read+Write 権（閲覧および編集）",
                f"- {format_holders(page.readwrite_users, page.readwrite_groups)}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def generate_json_data(report: PermissionReport) -> List[dict]:
    """機械可読な JSON 用のデータ構造を生成する."""
    data = []
    for p in report.pages:
        data.append(
            {
                "page_id": p.page_id,
                "title": p.title,
                "space_key": p.space_key,
                "url": p.url,
                "rel_path": p.rel_path,
                "has_explicit": p.has_explicit,
                "fetch_failed": p.fetch_failed,
                "fail_reason": p.fail_reason,
                "read_users": p.read_users,
                "read_groups": p.read_groups,
                "readwrite_users": p.readwrite_users,
                "readwrite_groups": p.readwrite_groups,
            }
        )
    return data


def write_permission_report(
    report: PermissionReport,
    output_dir: str,
    report_layout: str = "aggregate",
    report_formats: str = "md",
    filename_prefix: str = "_permissions",
    overwrite: bool = False,
) -> List[str]:
    """設定に従い権限レポート (Markdown / JSON) をファイル出力する.

    Args:
        report: PermissionReport インスタンス
        output_dir: 出力先ディレクトリ
        report_layout: `aggregate` (集約) または `per_page` (分散)
        report_formats: `md`, `json`, または `both`
        filename_prefix: 集約ファイル名・分散ファイル名のプレフィックス (既定 `_permissions`)
        overwrite: 既存ファイルが存在する場合に上書きするかどうか (既定 `False`)

    Returns:
        生成・保存されたファイルパスのリスト
    """
    fmt = report_formats.lower()
    include_md = fmt in ("md", "markdown", "both")
    include_json = fmt in ("json", "both")

    # per_page レイアウト指定で rel_path が存在しない場合は aggregate へフォールバック
    effective_layout = report_layout.lower()
    if effective_layout == "per_page":
        has_any_rel_path = any(p.rel_path for p in report.pages)
        if not has_any_rel_path:
            logger.warning(
                "現象: レポートレイアウトに `per_page` が指定されましたが、各ページのローカル相対パスが存在しないため `aggregate` に自動フォールバックします。"
                "原因: ファイルシステムエクスポートと併用されていない単独実行。 "
                "対処方法: 必要に応じて `--report-layout aggregate` を使用してください。"
            )
            effective_layout = "aggregate"

    # 全出力先パスを算出して事前競合チェック
    target_paths: List[str] = []
    if effective_layout == "aggregate":
        if include_md:
            target_paths.append(os.path.join(output_dir, f"{filename_prefix}.md"))
        if include_json:
            target_paths.append(os.path.join(output_dir, f"{filename_prefix}.json"))
    elif effective_layout == "per_page":
        for page in report.pages:
            page_dir = os.path.join(output_dir, page.rel_path) if page.rel_path else output_dir
            if include_md:
                target_paths.append(os.path.join(page_dir, f"{filename_prefix}.md"))
            if include_json:
                target_paths.append(os.path.join(page_dir, f"{filename_prefix}.json"))

    if not overwrite:
        for path in target_paths:
            if os.path.exists(path):
                raise FileExistsError(
                    f"現象: 出力先に既存の権限レポートが存在します ({path})。 "
                    f"原因: overwrite が未指定です。 "
                    f"対処方法: --overwrite を指定するか、既存ファイルを退避してください。"
                )

    output_files: List[str] = []
    os.makedirs(output_dir, exist_ok=True)

    if effective_layout == "aggregate":
        if include_md:
            md_content = generate_aggregate_markdown(report)
            md_path = os.path.join(output_dir, f"{filename_prefix}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            output_files.append(md_path)

        if include_json:
            json_data = generate_json_data(report)
            json_path = os.path.join(output_dir, f"{filename_prefix}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            output_files.append(json_path)

    elif effective_layout == "per_page":
        for page in report.pages:
            # 相対パスが存在する場合はその配下、無ければ output_dir 直下
            page_dir = os.path.join(output_dir, page.rel_path) if page.rel_path else output_dir
            os.makedirs(page_dir, exist_ok=True)

            if include_md:
                md_content = generate_per_page_markdown(page)
                md_path = os.path.join(page_dir, f"{filename_prefix}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                output_files.append(md_path)

            if include_json:
                page_json_data = generate_json_data(PermissionReport(pages=[page]))[0]
                json_path = os.path.join(page_dir, f"{filename_prefix}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(page_json_data, f, ensure_ascii=False, indent=2)
                output_files.append(json_path)

    return output_files
