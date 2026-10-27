"""添付参照のリンク書き換え (リンクリゾルバ) モジュール.

Markdown 本文中に含まれる添付ファイル参照 (画像や添付リンク) を、
相対パス (`relative` モード) または Confluence 上の絶対 URL (`original` モード) へ書き換える純粋関数を提供する。
"""

import re
from typing import Dict, List, Tuple

from c2m_export.fs_export.models import AttachmentRef


def rewrite_attachment_links(
    content: str,
    attachments: List[AttachmentRef],
    attachment_dir_name: str = "_attachments",
    link_mode: str = "relative",
    base_url: str = "",
) -> Tuple[str, int]:
    """Markdown 本文中の添付参照リンクを書き換える.

    Args:
        content: 変換済みの Markdown 本文文字列
        attachments: そのページの添付ファイル参照オブジェクトのリスト
        attachment_dir_name: 添付ファイルを格納するサブディレクトリ名
        link_mode: リンクモード ("relative" または "original")
        base_url: Confluence のベース URL (original モード用)

    Returns:
        Tuple[書き換え後の Markdown 本文文字列, 相対モード時の未解決リンク件数]
    """
    if not attachments:
        return content, 0

    # 元ファイル名 -> AttachmentRef のマッピング作成
    att_map: Dict[str, AttachmentRef] = {att.original_filename: att for att in attachments}

    clean_base = base_url.rstrip("/")
    unresolved_count = 0

    # Markdown 画像・リンク形式 ![alt](path) や [text](path) を対象とする正規表現
    # 例: ![image.png](image.png) や [doc.pdf](doc.pdf)
    pattern = re.compile(r"(!?\[.*?\])\((<[^>]+>|[^)]+)\)")

    def replacer(match: re.Match) -> str:
        nonlocal unresolved_count
        prefix = match.group(1)
        target = match.group(2).strip()

        # target が <> で囲まれている場合の解除
        clean_target = target
        if clean_target.startswith("<") and clean_target.endswith(">"):
            clean_target = clean_target[1:-1]

        # 外部 URL またはアンカー等はスキップ
        if clean_target.startswith("http://") or clean_target.startswith("https://") or clean_target.startswith("#"):
            return match.group(0)

        # att_map にマッチするか
        att = att_map.get(clean_target)
        if not att:
            # 該当する添付情報が見つからない場合
            if link_mode == "relative":
                unresolved_count += 1
            return match.group(0)

        if link_mode == "original":
            if att.download_path:
                dl_path = att.download_path
                if not dl_path.startswith("/"):
                    dl_path = "/" + dl_path
                new_url = f"{clean_base}{dl_path}"
                if any(char in new_url for char in " ()"):
                    new_url = f"<{new_url}>"
                return f"{prefix}({new_url})"
            return match.group(0)
        else:  # relative モード
            if att.saved:
                new_rel_path = f"{attachment_dir_name}/{att.saved_filename}"
                if any(char in new_rel_path for char in " ()"):
                    new_rel_path = f"<{new_rel_path}>"
                return f"{prefix}({new_rel_path})"
            else:
                # ローカル保存に失敗/未保存の場合、元の参照のまま残し未解決としてカウント
                unresolved_count += 1
                return match.group(0)

    rewritten_content = pattern.sub(replacer, content)
    return rewritten_content, unresolved_count
