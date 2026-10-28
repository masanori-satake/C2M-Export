"""圧縮形式カテゴリ集約の純粋関数 (UC4)."""

from typing import Any, Dict, Set
from c2m_export.assessment.models import RawInventory

DEFAULT_ARCHIVE_EXTENSIONS: Set[str] = {
    "zip",
    "7z",
    "rar",
    "gz",
    "tar",
    "bz2",
    "xz",
    "tgz",
    "lzh",
    "cab",
}


def summarize_archives(
    inventory: RawInventory, archive_extensions: Set[str] = DEFAULT_ARCHIVE_EXTENSIONS
) -> Dict[str, Any]:
    """インベントリ内の全添付ファイルを走査し、圧縮形式カテゴリの集計を行う."""
    normalized_exts = {e.lower().lstrip(".") for e in archive_extensions} if archive_extensions else set()

    file_count = 0
    total_size_bytes = 0
    size_meta_missing_count = 0
    ext_stats: Dict[str, Dict[str, Any]] = {}

    if not normalized_exts:
        return {
            "file_count": 0,
            "total_size_bytes": 0,
            "size_meta_missing_count": 0,
            "extensions": [],
        }

    for page in inventory.pages:
        for att in page.attachments:
            # 拡張子判定 (collectorのrsplit(".", 1)による末尾トークン/extension属性を使用)
            ext = att.extension.lower()
            if ext in normalized_exts:
                file_count += 1
                if ext not in ext_stats:
                    ext_stats[ext] = {
                        "extension": ext,
                        "count": 0,
                        "total_size_bytes": 0,
                        "max_size_bytes": 0,
                    }

                stat = ext_stats[ext]
                stat["count"] += 1

                if att.file_size is not None:
                    total_size_bytes += att.file_size
                    stat["total_size_bytes"] += att.file_size
                    if att.file_size > stat["max_size_bytes"]:
                        stat["max_size_bytes"] = att.file_size
                else:
                    size_meta_missing_count += 1

    # extensions リストを total_size_bytes 降順にソート固定
    extensions_list = list(ext_stats.values())
    extensions_list.sort(key=lambda x: (x["total_size_bytes"], x["count"]), reverse=True)

    return {
        "file_count": file_count,
        "total_size_bytes": total_size_bytes,
        "size_meta_missing_count": size_meta_missing_count,
        "extensions": extensions_list,
    }
