"""Frontmatter (YAML フロントマター) 生成モジュール.

エクスポートされた Markdown ファイルの先頭に付与するメタデータブロックを生成する。
"""

from datetime import datetime
from typing import Dict, List, Optional


def generate_frontmatter(
    page_id: str,
    space_key: str,
    base_url: str,
    title: str,
    version: Optional[int] = None,
    last_modified: Optional[str] = None,
    exported_at: Optional[str] = None,
    fields: Optional[List[str]] = None,
) -> str:
    """ページメタデータから YAML フロントマター文字列を生成する.

    Args:
        page_id: Confluence ページ ID
        space_key: Space キー
        base_url: Confluence のベース URL
        title: ページタイトル
        version: ページのバージョン番号
        last_modified: 最終更新日時 (ISO 8601 形式文字列)
        exported_at: エクスポート日時 (ISO 8601 形式文字列、未指定時は現在時刻)
        fields: フロントマターに含めるフィールド名のリスト。None の場合はすべての標準項目を出力する。

    Returns:
        --- で囲まれた YAML フロントマターブロック文字列 (末尾改行付き)
    """
    clean_base = base_url.rstrip("/")
    confluence_url = f"{clean_base}/pages/viewpage.action?pageId={page_id}"

    if exported_at is None:
        exported_at = datetime.now().astimezone().isoformat()

    all_data: Dict[str, str] = {
        "confluence_url": confluence_url,
        "confluence_page_id": str(page_id),
        "confluence_space_key": str(space_key),
        "title": title,
    }

    if version is not None:
        all_data["version"] = str(version)
    if last_modified:
        all_data["last_modified"] = str(last_modified)
    all_data["exported_at"] = str(exported_at)

    if fields is not None:
        selected_keys = [f for f in fields if f in all_data]
        # 最低限 confluence_url は必須とする
        if "confluence_url" not in selected_keys:
            selected_keys.insert(0, "confluence_url")
    else:
        selected_keys = list(all_data.keys())

    lines = ["---"]
    for key in selected_keys:
        val = all_data[key]
        # YAML で安全に扱うため、ダブルクォートやエスケープ処理を実施
        safe_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}: "{safe_val}"')
    lines.append("---")
    lines.append("")

    return "\n".join(lines) + "\n"
