import re
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Union, Optional

def sanitize_filename(filename: str) -> str:
    """
    文字列をWindowsのファイル名として安全な形式に変換する。
    """
    # 制御文字およびWindowsで禁止されている記号をアンダースコアに置換
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    # 末尾のドットとスペースはOS制限により削除
    s = s.rstrip('. ')
    # Windows予約語との衝突回避（例: CON, PRN 等）
    reserved = {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4",
        "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }
    if s.upper() in reserved:
        s = "_" + s
    # Windowsのファイル名長制限(255文字)を考慮して切り詰め
    if len(s) > 200:
        s = s[:200]
    return s

def get_unique_filename(directory: str, space_key: str, title: str, suffix: str = "") -> Path:
    """
    【spaceKey】 Title.md 形式のファイル名を生成する。
    suffixが指定されている場合は、Titleの末尾に付与する。
    """
    # スペースキーが取得できない場合のフォールバック
    display_space_key = space_key if space_key else "UNKNOWN"

    safe_title = sanitize_filename(title or "untitled")
    filename = f"【{display_space_key}】 {safe_title}{suffix}.md"
    filepath = Path(directory) / filename

    return filepath

def is_within_size_limit(current_bytes: int, stop_threshold_mb: float) -> bool:
    """
    現在のバイト数が指定された閾値(MB)以下であるか判定する。
    """
    threshold_bytes = stop_threshold_mb * 1024 * 1024
    return current_bytes <= threshold_bytes

def mb_to_bytes(mb: float) -> int:
    return int(mb * 1024 * 1024)

def bytes_to_mb(b: int) -> float:
    return b / (1024 * 1024)


def generate_zip_filename(space_key: Optional[str], title: Optional[str], suffix: str = "") -> str:
    """
    【spaceKey】 Title.zip 形式のファイル名を生成する。
    suffixが指定されている場合は、Titleの末尾に付与する。
    """
    display_space = space_key if space_key else "UNKNOWN"
    safe_title = sanitize_filename(title or "untitled")
    return f"【{display_space}】 {safe_title}{suffix}.zip"

def create_zip_file(zip_path: Path, files: List[Tuple[str, str]]):
    """
    指定されたファイル名と内容のリストからZipファイルを作成する。
    files: [(filename, content), ...]
    """
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename, content in files:
            zipf.writestr(filename, content)
