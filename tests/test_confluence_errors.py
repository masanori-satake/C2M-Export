"""通信例外の秘匿情報除去と呼び出し元のエラー分類を検証する."""

import json
import traceback
from unittest.mock import MagicMock, call

import pytest
import requests

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.config import AnalysisConfig
from c2m_export.confluence import ConfluenceClient

SIGNED_URL = "https://confluence.example.com/download/file?signature=PRIVATE_SIGNATURE"


@pytest.fixture(params=["request", "download"])
def operation(request, tmp_path, monkeypatch):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    transport = MagicMock()
    monkeypatch.setattr("c2m_export.confluence.time.sleep", lambda _: None)
    if request.param == "request":
        monkeypatch.setattr(client.session, "request", transport)

        def invoke(retries=3):
            return client._request("GET", "/rest/api/content/1", retries=retries)
    else:
        monkeypatch.setattr(client.session, "get", transport)

        def invoke(retries=3):
            return client.download_attachment(SIGNED_URL, str(tmp_path / "file"), retries=retries)

    return invoke, transport


@pytest.mark.parametrize("retries", [1, 3])
@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503, 599])
def test_http_failure_keeps_only_status(operation, status, retries, monkeypatch, caplog):
    invoke, transport = operation
    sleep = MagicMock()
    monkeypatch.setattr("c2m_export.confluence.time.sleep", sleep)
    response = requests.Response()
    response.status_code = status
    response.url = SIGNED_URL
    response.reason = SIGNED_URL
    response.headers["Location"] = SIGNED_URL
    response._content = SIGNED_URL.encode()
    response.request = requests.Request("GET", SIGNED_URL).prepare()
    transport.return_value = response

    with pytest.raises(requests.exceptions.HTTPError) as caught:
        invoke(retries=retries)

    error = caught.value
    assert transport.call_count == retries
    assert sleep.call_args_list == [call(2.0 * (2**i)) for i in range(retries - 1)]
    assert str(status) in str(error)
    assert SIGNED_URL not in str(error)
    assert (
        "PRIVATE_SIGNATURE"
        not in "".join(traceback.format_exception(type(error), error, error.__traceback__)) + caplog.text
    )
    assert error.request is None
    assert error.response is not response
    assert error.response.status_code == status
    assert error.response.url is None
    assert error.response.reason is None
    assert error.response.request is None
    assert not error.response.headers
    assert not error.response.content


@pytest.mark.parametrize(
    "error_type",
    [
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        requests.exceptions.RequestException,
    ],
)
def test_network_failure_hides_original_message(operation, error_type, caplog):
    invoke, transport = operation
    original = error_type(SIGNED_URL, request=requests.Request("GET", SIGNED_URL).prepare())
    transport.side_effect = original

    with pytest.raises(requests.exceptions.RequestException) as caught:
        invoke()

    error = caught.value
    assert error is not original
    assert transport.call_count == 3
    assert SIGNED_URL not in str(error)
    assert (
        "PRIVATE_SIGNATURE"
        not in "".join(traceback.format_exception(type(error), error, error.__traceback__)) + caplog.text
    )
    assert error.request is None
    assert error.response is None


def test_stream_failure_is_sanitized_and_removes_partial_file(tmp_path, monkeypatch, caplog):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    response = MagicMock(status_code=200)

    def chunks(**kwargs):
        yield b"partial"
        raise requests.exceptions.ChunkedEncodingError(SIGNED_URL)

    response.iter_content.side_effect = chunks
    transport = MagicMock(return_value=response)
    monkeypatch.setattr(client.session, "get", transport)
    monkeypatch.setattr("c2m_export.confluence.time.sleep", lambda _: None)
    destination = tmp_path / "file"

    with pytest.raises(requests.exceptions.RequestException) as caught:
        client.download_attachment(SIGNED_URL, str(destination))

    assert transport.call_count == 3
    assert not destination.exists()
    assert (
        "PRIVATE_SIGNATURE"
        not in "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
        + caplog.text
    )


@pytest.mark.parametrize("scope", ["root_page_ids", "space_keys"])
@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (401, "AUTH_FAILED"),
        (403, "AUTH_FAILED"),
        (404, "TARGET_NOT_FOUND"),
        (429, "API_ERROR"),
        (500, "API_ERROR"),
        (503, "API_ERROR"),
        (599, "API_ERROR"),
    ],
)
def test_analysis_preserves_http_error_classification(scope, status, expected_code, monkeypatch, caplog):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    response = requests.Response()
    response.status_code = status
    response.url = SIGNED_URL
    monkeypatch.setattr(client.session, "request", MagicMock(return_value=response))
    monkeypatch.setattr("c2m_export.confluence.time.sleep", lambda _: None)
    config = AnalysisConfig()
    config.base_url = client.base_url
    setattr(config, scope, ["1"])

    result = run_analysis(AnalysisParams(), config, client)

    assert result.status == "error"
    assert result.error.code == expected_code
    assert "PRIVATE_SIGNATURE" not in json.dumps(result.to_dict()) + caplog.text
