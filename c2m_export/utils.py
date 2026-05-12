import re
import os
from pathlib import Path

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

def get_unique_filename(directory: str, space_key: str, title: str, page_id: str) -> Path:
    """
    【spaceKey】 Title.md 形式のファイル名を生成する。
    既存ファイルがある場合は (pageId) を付与して衝突を回避する。
    """
    # スペースキーが取得できない場合のフォールバック
    display_space_key = space_key if space_key else "UNKNOWN"

    safe_title = sanitize_filename(title)
    base_name = f"【{display_space_key}】 {safe_title}"
    filename = f"{base_name}.md"
    filepath = Path(directory) / filename

    if filepath.exists():
        filename = f"{base_name} ({page_id}).md"
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
