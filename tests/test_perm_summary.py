"""処理サマリ (summary) モジュールのテスト."""

from c2m_export.permission.models import PagePermission, PermissionReport, PermissionResult
from c2m_export.permission.summary import write_summary


def test_write_summary(tmp_path):
    p1 = PagePermission(
        page_id="1",
        title="P1",
        space_key="S",
        url="http://url",
        has_explicit=True,
    )
    p2 = PagePermission(
        page_id="2",
        title="P2",
        space_key="S",
        url="http://url",
        fetch_failed=True,
        fail_reason="403",
    )
    report = PermissionReport(pages=[p1, p2])
    res = PermissionResult(
        report=report,
        exported_count=2,
        explicit_count=1,
        inherited_count=0,
        failed_page_ids=["2"],
    )

    summary_path = write_summary(res, str(tmp_path))

    assert summary_path.startswith(str(tmp_path))
    assert "permexport_summary_" in summary_path

    with open(summary_path, encoding="utf-8") as f:
        text = f.read()
        assert "処理ページ総数: 2 件" in text
        assert "個別制限あり: 1 件" in text
        assert "取得失敗: 1 件" in text
        assert "- 2" in text
