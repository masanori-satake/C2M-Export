import pytest

from c2m_export.analysis.params import ALL_USECASES, AnalysisParams


def test_params_default_values():
    params = AnalysisParams()
    assert params.usecases == ALL_USECASES
    assert params.mode == "summary"
    assert params.limit == 1000
    assert params.stale_days == 365
    assert params.min_body_bytes == 200
    assert "zip" in params.archive_extensions
    assert params.analyze_restrictions is None
    assert params.sort is None
    params.validate()


def test_params_invalid_usecase():
    params = AnalysisParams(usecases=["unknown_uc"])
    with pytest.raises(ValueError) as excinfo:
        params.validate()
    assert "未知のユースケース" in str(excinfo.value)


def test_params_empty_usecases():
    params = AnalysisParams(usecases=[])
    with pytest.raises(ValueError) as excinfo:
        params.validate()
    assert "usecases が空または無効" in str(excinfo.value)


def test_params_invalid_mode():
    params = AnalysisParams(mode="invalid_mode")
    with pytest.raises(ValueError) as excinfo:
        params.validate()
    assert "mode" in str(excinfo.value)


def test_params_invalid_limit():
    params = AnalysisParams(limit=0)
    with pytest.raises(ValueError) as excinfo:
        params.validate()
    assert "limit" in str(excinfo.value)


def test_params_invalid_stale():
    params = AnalysisParams(stale_days=-1)
    with pytest.raises(ValueError) as excinfo:
        params.validate()
    assert "stale_days" in str(excinfo.value)


def test_params_archive_extensions_normalization():
    params = AnalysisParams(archive_extensions={".ZIP", "Tar.Gz", "rar"})
    assert params.archive_extensions == {"zip", "tar.gz", "rar"}
