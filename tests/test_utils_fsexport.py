"""ファイルシステムエクスポート用ユーティリティのテスト."""

from c2m_export.utils import bytes_to_gb, generate_unique_name


def test_bytes_to_gb():
    assert bytes_to_gb(1073741824) == 1.0
    assert bytes_to_gb(0) == 0.0


def test_generate_unique_name():
    existing = ["設計書", "設計書 (2)", "画像.png"]

    assert generate_unique_name("新規ファイル", existing) == "新規ファイル"
    assert generate_unique_name("設計書", existing) == "設計書 (3)"
    assert generate_unique_name("画像.png", existing) == "画像 (2).png"
