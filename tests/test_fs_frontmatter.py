"""Frontmatter 生成機能のテスト."""

from c2m_export.fs_export.frontmatter import generate_frontmatter


def test_generate_frontmatter_default():
    fm = generate_frontmatter(
        page_id="12345",
        space_key="TEST",
        base_url="https://confluence.example.com/",
        title="テスト ページ",
        version=3,
        last_modified="2026-01-01T00:00:00+09:00",
        exported_at="2026-02-01T00:00:00+09:00",
    )

    assert fm.startswith("---\n")
    assert 'confluence_url: "https://confluence.example.com/pages/viewpage.action?pageId=12345"' in fm
    assert 'confluence_page_id: "12345"' in fm
    assert 'confluence_space_key: "TEST"' in fm
    assert 'title: "テスト ページ"' in fm
    assert 'version: "3"' in fm
    assert 'last_modified: "2026-01-01T00:00:00+09:00"' in fm
    assert 'exported_at: "2026-02-01T00:00:00+09:00"' in fm
    assert fm.endswith("---\n\n")


def test_generate_frontmatter_selected_fields():
    fm = generate_frontmatter(
        page_id="12345",
        space_key="TEST",
        base_url="https://confluence.example.com",
        title="テスト ページ",
        fields=["title", "confluence_page_id"],
    )

    # confluence_url は強制的に挿入される
    assert 'confluence_url: "' in fm
    assert 'title: "テスト ページ"' in fm
    assert 'confluence_page_id: "12345"' in fm
    assert "confluence_space_key" not in fm
