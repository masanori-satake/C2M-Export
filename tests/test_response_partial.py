"""AnalysisResponse および Uncertainties の拡張フィールドの検証テスト."""

from c2m_export.analysis.response import AnalysisResponse, Uncertainties


def test_uncertainties_default_fields():
    """Uncertainties に追加された新規キーがデフォルト値で初期化され to_dict に出力されることを確認."""
    unc = Uncertainties()
    assert unc.interrupted is False
    assert unc.interrupted_reason is None
    assert unc.collected_page_count == 0
    assert unc.resumed_from_checkpoint is False
    assert unc.checkpoint_reused_count == 0
    assert unc.checkpoint_corrupted_line_count == 0

    resp = AnalysisResponse(uncertainties=unc)
    assert resp.schema_version == "1.2"
    assert resp.status == "ok"

    res_dict = resp.to_dict()
    assert res_dict["schema_version"] == "1.2"
    assert res_dict["status"] == "ok"
    assert res_dict["uncertainties"]["interrupted"] is False
    assert res_dict["uncertainties"]["interrupted_reason"] is None
    assert res_dict["uncertainties"]["collected_page_count"] == 0
    assert res_dict["uncertainties"]["resumed_from_checkpoint"] is False
    assert res_dict["uncertainties"]["checkpoint_reused_count"] == 0
    assert res_dict["uncertainties"]["checkpoint_corrupted_line_count"] == 0


def test_analysis_response_partial_status():
    """status="partial" を持つ AnalysisResponse の構築および to_dict 出力を確認."""
    unc = Uncertainties(
        interrupted=True,
        interrupted_reason="signal",
        collected_page_count=42,
        resumed_from_checkpoint=True,
        checkpoint_reused_count=10,
        checkpoint_corrupted_line_count=1,
    )
    resp = AnalysisResponse(status="partial", uncertainties=unc)

    assert resp.status == "partial"
    res_dict = resp.to_dict()
    assert res_dict["status"] == "partial"
    assert res_dict["uncertainties"]["interrupted"] is True
    assert res_dict["uncertainties"]["interrupted_reason"] == "signal"
    assert res_dict["uncertainties"]["collected_page_count"] == 42
    assert res_dict["uncertainties"]["resumed_from_checkpoint"] is True
    assert res_dict["uncertainties"]["checkpoint_reused_count"] == 10
    assert res_dict["uncertainties"]["checkpoint_corrupted_line_count"] == 1
