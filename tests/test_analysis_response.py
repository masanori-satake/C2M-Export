from c2m_export.analysis.response import (
    CODE_INVALID_PARAM,
    AnalysisResponse,
    AnalysisScope,
    ErrorObject,
    Uncertainties,
)


def test_analysis_response_to_dict():
    resp = AnalysisResponse(
        status="ok",
        generated_at="2026-03-31T00:00:00Z",
        mode="summary",
        scope=AnalysisScope(root_page_ids=["100"], space_keys=["DEV"], resolved_root_count=2),
        summary={"level_distribution": {1: 5, 2: 3}},
        usecases={"risk": {"counts": {"total": 1}}},
        uncertainties=Uncertainties(size_meta_missing_count=2),
    )

    d = resp.to_dict()
    assert d["schema_version"] == "1.0"
    assert d["status"] == "ok"
    assert d["generated_at"] == "2026-03-31T00:00:00Z"
    assert d["scope"]["resolved_root_count"] == 2
    # Ensure level_distribution keys are stringified
    assert d["summary"]["level_distribution"] == {"1": 5, "2": 3}
    assert d["uncertainties"]["size_meta_missing_count"] == 2
    assert "error" not in d


def test_analysis_response_error_to_dict():
    err = ErrorObject(
        code=CODE_INVALID_PARAM, message="現象: 不正パラメータ 原因: limit<1 対処: 1以上の整数を指定してください"
    )
    resp = AnalysisResponse(status="error", error=err)

    d = resp.to_dict()
    assert d["status"] == "error"
    assert d["error"]["code"] == CODE_INVALID_PARAM
    assert "現象" in d["error"]["message"]
