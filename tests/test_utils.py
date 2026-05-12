import pytest
from pathlib import Path
from c2m_export.utils import sanitize_filename, get_unique_filename, is_within_size_limit

def test_sanitize_filename():
    assert sanitize_filename('test:file*name?.md') == 'test_file_name_.md'
    assert sanitize_filename('CON') == '_CON'
    assert sanitize_filename('A' * 300) == 'A' * 200

def test_get_unique_filename(tmp_path):
    directory = tmp_path
    space_key = "KEY"
    title = "Title"
    page_id = "123"

    # First time
    filepath = get_unique_filename(directory, space_key, title, page_id)
    assert filepath.name == "【KEY】 Title.md"

    # Create file
    filepath.touch()

    # Second time with same name
    filepath_collision = get_unique_filename(directory, space_key, title, page_id)
    assert filepath_collision.name == "【KEY】 Title (123).md"

def test_get_unique_filename_none_space(tmp_path):
    directory = tmp_path
    assert get_unique_filename(directory, None, "Title", "123").name == "【UNKNOWN】 Title.md"

def test_is_within_size_limit():
    # 10MB limit
    limit_mb = 10
    limit_bytes = 10 * 1024 * 1024

    assert is_within_size_limit(limit_bytes - 1, limit_mb) is True
    assert is_within_size_limit(limit_bytes, limit_mb) is True
    assert is_within_size_limit(limit_bytes + 1, limit_mb) is False
