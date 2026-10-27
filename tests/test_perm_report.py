"""権限レポート出力 (report) モジュールのテスト."""

import json

from c2m_export.permission.models import PagePermission, PermissionReport
from c2m_export.permission.report import (
    generate_aggregate_markdown,
    generate_per_page_markdown,
    write_permission_report,
)


def test_generate_aggregate_markdown():
    p1 = PagePermission(
        page_id="1",
        title="親ページ",
        space_key="DEV",
        url="https://example.com/pages/1",
        rel_path="【DEV】 親ページ",
        has_explicit=True,
        read_users=["山田 (yamada)"],
        read_groups=["devs"],
    )
    p2 = PagePermission(
        page_id="2",
        title="子ページ",
        space_key="DEV",
        url="https://example.com/pages/2",
        rel_path="【DEV】 親ページ/子ページ",
        has_explicit=False,
    )
    report = PermissionReport(pages=[p1, p2])

    md = generate_aggregate_markdown(report)
    assert "# Confluence ページアクセス権限一覧（集約レポート）" in md
    assert "自動適用するものではありません" in md
    assert "親ページ" in md
    assert "**あり**" in md
    assert "継承/制限なし" in md
    assert "山田 (yamada)" in md


def test_write_permission_report_aggregate_and_per_page(tmp_path):
    p1 = PagePermission(
        page_id="10",
        title="テスト 10",
        space_key="TEST",
        url="https://example.com/10",
        rel_path="TEST_10",
        has_explicit=True,
        read_users=["userA"],
    )
    report = PermissionReport(pages=[p1])

    # 1. aggregate layout with 'both' format
    files = write_permission_report(
        report=report,
        output_dir=str(tmp_path),
        report_layout="aggregate",
        report_formats="both",
    )

    assert len(files) == 2
    md_file = tmp_path / "_permissions.md"
    json_file = tmp_path / "_permissions.json"
    assert md_file.exists()
    assert json_file.exists()

    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
        assert data[0]["page_id"] == "10"
        assert data[0]["has_explicit"] is True

    # 2. per_page layout with md
    out_dir_per_page = tmp_path / "per_page_out"
    files_per = write_permission_report(
        report=report,
        output_dir=str(out_dir_per_page),
        report_layout="per_page",
        report_formats="md",
    )

    expected_per_page_file = out_dir_per_page / "TEST_10" / "_permissions.md"
    assert expected_per_page_file.exists()
    assert len(files_per) == 1


def test_write_permission_report_fallback_when_no_rel_path(tmp_path):
    p1 = PagePermission(
        page_id="20",
        title="単独実行ページ",
        space_key="TEST",
        url="https://example.com/20",
        rel_path=None,
        has_explicit=False,
    )
    report = PermissionReport(pages=[p1])

    files = write_permission_report(
        report=report,
        output_dir=str(tmp_path),
        report_layout="per_page",  # Specified per_page but rel_path is None
        report_formats="md",
    )

    # Should fallback to aggregate _permissions.md in output_dir
    expected_file = tmp_path / "_permissions.md"
    assert expected_file.exists()
    assert len(files) == 1
