"""ConfluenceClient のファイルシステムエクスポート用拡張のテスト."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from c2m_export.confluence import ConfluenceClient


def test_download_attachment_success(tmp_path):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]

    dest_file = tmp_path / "sub" / "test.txt"

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        bytes_written = client.download_attachment("/download/test.txt", str(dest_file))
        assert bytes_written == 12
        assert dest_file.read_bytes() == b"chunk1chunk2"
        mock_get.assert_called_once_with("https://confluence.example.com/download/test.txt", stream=True, timeout=60)


def test_download_attachment_exceeds_max_bytes(tmp_path):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]

    dest_file = tmp_path / "test.txt"

    with patch.object(client.session, "get", return_value=mock_response):
        with pytest.raises(ValueError, match="単一ファイルサイズ上限"):
            client.download_attachment("/download/test.txt", str(dest_file), max_bytes=5)

    assert not dest_file.exists()


def test_download_attachment_retry_on_server_error(tmp_path):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    err_response = MagicMock()
    err_response.status_code = 500

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.iter_content.return_value = [b"data"]

    dest_file = tmp_path / "retry.txt"

    with patch.object(client.session, "get", side_effect=[err_response, ok_response]) as mock_get:
        with patch("time.sleep"):
            bytes_written = client.download_attachment("/download/retry.txt", str(dest_file), retries=2)
            assert bytes_written == 4
            assert mock_get.call_count == 2


@pytest.mark.parametrize(
    "external_url",
    [
        "https://evil-attacker.com/malicious",
        "http://169.254.169.254/latest/meta-data",
        "//untrusted-host.com/payload",
    ],
)
def test_download_attachment_external_url_blocked(tmp_path, external_url):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    dest_file = tmp_path / "blocked.txt"

    with patch.object(client.session, "get") as mock_get:
        with pytest.raises(ValueError, match="許可されていない外部ホスト"):
            client.download_attachment(external_url, str(dest_file))
        mock_get.assert_not_called()


def test_download_attachment_absolute_same_domain_success(tmp_path):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"valid_data"]

    dest_file = tmp_path / "valid.txt"
    same_domain_url = "https://confluence.example.com/download/valid.txt"

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        bytes_written = client.download_attachment(same_domain_url, str(dest_file))
        assert bytes_written == 10
        mock_get.assert_called_once_with(same_domain_url, stream=True, timeout=60)
