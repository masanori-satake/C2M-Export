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
