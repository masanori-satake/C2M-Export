"""移設先（SharePoint/OneDrive）制約の判定ルールおよび相対パス算出モジュール."""

import re
from typing import Optional, Set

from c2m_export.utils import sanitize_filename

# SharePoint / OneDrive の既定制約定数
DEFAULT_PATH_LENGTH_LIMIT = 400
DEFAULT_SINGLE_FILE_MAX_MB = 250
DEFAULT_ATTACHMENT_DIR_NAME = "_attachments"

# ファイル名/フォルダ名の禁止文字 (SharePoint/OneDrive): " * : < > ? / \ |
INVALID_CHARS_PATTERN = re.compile(r'["\*\:<>\?\\/\|]')

# 制御文字 (ASCII 0-31)
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f]")

# デフォルトのブロック拡張子リスト（小文字・ドット無し）
DEFAULT_BLOCKED_EXTENSIONS = {
    "exe",
    "bat",
    "cmd",
    "sh",
    "vbs",
    "ps1",
    "msi",
    "com",
    "scr",
    "dll",
    "sys",
    "reg",
    "jar",
}

# Windows / SharePoint の予約名
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def calculate_page_relative_path(ancestors_titles: list[str], title: str) -> str:
    """ページの相対パス（`ancestor1/ancestor2/title.md`）を算出する."""
    path_segments = [sanitize_filename(t) for t in ancestors_titles] + [f"{sanitize_filename(title)}.md"]
    return "/".join(path_segments)


def calculate_attachment_relative_path(
    ancestors_titles: list[str], title: str, attachment_filename: str, attachment_dir_name: str = "_attachments"
) -> str:
    """添付ファイルの相対パス（`ancestor/title/attachment_dir/filename`）を算出する."""
    path_segments = (
        [sanitize_filename(t) for t in ancestors_titles]
        + [sanitize_filename(title)]
        + [attachment_dir_name, sanitize_filename(attachment_filename)]
    )
    return "/".join(path_segments)


def check_path_length(path: str, limit: int = DEFAULT_PATH_LENGTH_LIMIT) -> Optional[str]:
    """パス長が上限を超える場合に理由文字列を返す."""
    if len(path) > limit:
        return f"相対パス長（{len(path)}文字）が上限（{limit}文字）を超過しています"
    return None


def check_invalid_chars_or_name(name: str) -> Optional[str]:
    """ファイル名/フォルダ名に含まれる禁止文字、予約語、末尾記号等を判定する."""
    if INVALID_CHARS_PATTERN.search(name):
        return f"名前 '{name}' に禁止文字（\" * : < > ? / \\ |）が含まれています"
    if CONTROL_CHARS_PATTERN.search(name):
        return f"名前 '{name}' に制御文字が含まれています"

    # 末尾ドット/スペース、または拡張子前の末尾スペース/ドット
    base_stem = name.rsplit(".", 1)[0]
    if name.endswith(".") or name.endswith(" ") or base_stem.endswith(".") or base_stem.endswith(" "):
        return f"名前 '{name}' の末尾（または拡張子前）にドットまたはスペースが含まれています"

    # 拡張子を除いたベース名が予約語かチェック
    base_name = base_stem.upper()
    if base_name in RESERVED_NAMES:
        return f"名前 '{name}' は予約語（{base_name}）に使用されています"

    return None


def check_blocked_extension(extension: str, blocked_extensions: Optional[Set[str]] = None) -> Optional[str]:
    """ブロック対象の拡張子か判定する."""
    blocked = blocked_extensions if blocked_extensions is not None else DEFAULT_BLOCKED_EXTENSIONS
    ext_clean = extension.lower().lstrip(".")
    if ext_clean in blocked:
        return f"拡張子 '.{ext_clean}' は移設先でブロック対象となっています"
    return None


def check_large_file(file_size_bytes: Optional[int], max_mb: int = DEFAULT_SINGLE_FILE_MAX_MB) -> Optional[str]:
    """単一ファイルサイズが指定閾値（MB）を超えるか判定する."""
    if file_size_bytes is None:
        return None
    file_size_mb = file_size_bytes / (1024 * 1024)
    if file_size_mb > max_mb:
        return f"ファイルサイズ（{file_size_mb:.1f}MB）が上限（{max_mb}MB）を超過しています"
    return None
