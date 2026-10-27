import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from c2m_export.assessment.models import (
    AssessmentResult,
    AttachmentMeta,
    PageMeta,
    RawInventory,
    RestrictionMeta,
)
from c2m_export.assessment.report import (
    generate_json_report,
    generate_markdown_report,
    write_reports,
)


@pytest.fixture
def dummy_result():
    inventory = RawInventory(
        pages=[
            PageMeta(
                page_id="100",
                title="Sample Page",
                space_key="DEMO",
                level=1,
                body_bytes=1000,
                last_modified="2025-01-01T00:00:00Z",
                ancestors_titles=[],
                attachments=[
                    AttachmentMeta(
                        page_id="100",
                        filename="sample.png",
                        extension="png",
                        media_type="image/png",
                        file_size=2048,
                        version=1,
                    )
                ],
                restriction=RestrictionMeta(has_explicit=False),
            )
        ]
    )

    return AssessmentResult(
        total_pages=1,
        total_attachments=1,
        estimated_body_bytes=1000,
        total_attachment_bytes=2048,
        max_depth=1,
        level_distribution={1: 1},
        space_summary={"DEMO": {"pages": 1, "attachments": 1, "attachment_bytes": 2048}},
        extension_summary=[{"extension": "png", "count": 1, "total_size": 2048, "max_size": 2048}],
        mime_summary=[{"media_type": "image/png", "count": 1, "total_size": 2048, "max_size": 2048}],
        stale_page_count=0,
        empty_page_count=0,
        freshness_distribution={"within_30_days": 1},
        explicit_restriction_count=0,
        unique_restriction_users=[],
        unique_restriction_groups=[],
        read_only_restriction_count=0,
        read_write_restriction_count=0,
        risk_items=[],
        risk_summary_counts={},
        raw_inventory=inventory,
    )


def test_generate_markdown_report(dummy_result):
    md = generate_markdown_report(dummy_result)
    assert "# Confluence アセスメントレポート" in md
    assert "概算値" in md
    assert "DEMO" in md
    assert "sample.png" not in md  # リスク項目に無いためリスク一覧には登場しない
    assert "総ページ数**: 1 ページ" in md


def test_generate_json_report(dummy_result):
    json_data = generate_json_report(dummy_result)
    assert json_data["summary"]["total_pages"] == 1
    assert json_data["summary"]["space_summary"]["DEMO"]["pages"] == 1
    assert len(json_data["attachments"]["extension_summary"]) == 1


def test_write_reports(dummy_result):
    with TemporaryDirectory() as tmpdir:
        md_p, json_p = write_reports(
            dummy_result,
            output_dir=tmpdir,
            base_filename="test_report",
            report_format="both",
            overwrite=False,
        )

        assert md_p.exists()
        assert json_p.exists()

        md_content = md_p.read_text(encoding="utf-8")
        assert "# Confluence アセスメントレポート" in md_content

        json_content = json.loads(json_p.read_text(encoding="utf-8"))
        assert json_content["summary"]["total_pages"] == 1

        # 重複書き込みで FileExistsError が発生することを確認
        with pytest.raises(FileExistsError):
            write_reports(
                dummy_result,
                output_dir=tmpdir,
                base_filename="test_report",
                report_format="both",
                overwrite=False,
            )
