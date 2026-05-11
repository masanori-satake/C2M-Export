import re
import os
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes a string to be a safe Windows filename.
    """
    # Remove invalid characters: < > : " / \ | ? *
    # Also remove control characters
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    # Remove trailing dots and spaces
    s = s.rstrip('. ')
    # Avoid reserved names
    reserved = {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4",
        "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }
    if s.upper() in reserved:
        s = "_" + s
    # Limit length (Windows has a 255 char limit for components)
    if len(s) > 200:
        s = s[:200]
    return s

def get_unique_filename(directory: str, space_key: str, title: str, page_id: str) -> Path:
    """
    Generates a unique filename following the rules:
    【<spaceKey>】 <トップページタイトル>.md
    If exists, append (<pageId>)
    """
    safe_title = sanitize_filename(title)
    base_name = f"【{space_key}】 {safe_title}"
    filename = f"{base_name}.md"
    filepath = Path(directory) / filename

    if filepath.exists():
        filename = f"{base_name} ({page_id}).md"
        filepath = Path(directory) / filename

    return filepath

def is_within_size_limit(current_bytes: int, stop_threshold_mb: float) -> bool:
    """
    Checks if current size is within the stop threshold.
    """
    threshold_bytes = stop_threshold_mb * 1024 * 1024
    return current_bytes <= threshold_bytes

def mb_to_bytes(mb: float) -> int:
    return int(mb * 1024 * 1024)

def bytes_to_mb(b: int) -> float:
    return b / (1024 * 1024)
