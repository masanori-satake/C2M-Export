from c2m_export.assessment.rules import (
    calculate_attachment_relative_path,
    calculate_page_relative_path,
    check_blocked_extension,
    check_invalid_chars_or_name,
    check_large_file,
    check_path_length,
)


def test_calculate_relative_paths():
    page_path = calculate_page_relative_path(["Space Root", "Parent Page"], "Target Page")
    assert page_path == "Space Root/Parent Page/Target Page.md"

    att_path = calculate_attachment_relative_path(["Space Root"], "Target Page", "sample file.pdf", "_attachments")
    assert att_path == "Space Root/Target Page/_attachments/sample file.pdf"


def test_check_path_length():
    short_path = "a" * 300
    long_path = "a" * 401
    assert check_path_length(short_path, 400) is None
    assert "401文字" in check_path_length(long_path, 400)


def test_check_invalid_chars_or_name():
    assert check_invalid_chars_or_name("ValidName.txt") is None
    assert "禁止文字" in check_invalid_chars_or_name("Invalid:Name?.txt")
    assert "末尾" in check_invalid_chars_or_name("TrailingSpace .txt")
    assert "予約語" in check_invalid_chars_or_name("CON.txt")
    assert "予約語" in check_invalid_chars_or_name("aux")


def test_check_blocked_extension():
    assert check_blocked_extension("pdf") is None
    assert "ブロック対象" in check_blocked_extension("exe")
    assert "ブロック対象" in check_blocked_extension(".BAT")


def test_check_large_file():
    small_bytes = 100 * 1024 * 1024  # 100MB
    large_bytes = 300 * 1024 * 1024  # 300MB
    assert check_large_file(small_bytes, 250) is None
    assert "300.0MB" in check_large_file(large_bytes, 250)
