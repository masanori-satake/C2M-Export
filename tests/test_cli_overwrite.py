import pytest
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from c2m_export.cli import main
from c2m_export.config import Config

@pytest.fixture
def mock_confluence_client():
    with patch('c2m_export.cli.ConfluenceClient') as mock:
        client = mock.return_value
        client.get_page.return_value = {
            'title': 'Test Page',
            'space': {'key': 'TEST'},
            'body': {'storage': {'value': '<p>Hello</p>'}},
            '_links': {'webui': '/pages/viewpage.action?pageId=123'}
        }
        client.get_child_pages.return_value = []
        client.base_url = "https://confluence.example.com"
        yield client

@pytest.fixture
def temp_config(tmp_path):
    config_path = tmp_path / "c2m_config.yaml"
    content = """
base_url: https://confluence.example.com
root_page_ids:
  - "123"
token: dummy-token
output_dir: {dir}
""".format(dir=str(tmp_path / "output"))
    config_path.write_text(content, encoding="utf-8")
    return config_path

def test_cli_overwrite_default_creates_suffix(tmp_path, temp_config, mock_confluence_client):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch('sys.argv', ['c2m_export', '--config', str(temp_config)]):
        with patch('c2m_export.cli.datetime') as mock_date:
            mock_date.now.return_value.strftime.return_value = "_260503_160502"
            # We need to mock datetime.now() because it's used to generate the suffix
            main()

    expected_file = output_dir / "【TEST】 Test Page_260503_160502.md"
    assert expected_file.exists()

def test_cli_overwrite_true_no_suffix(tmp_path, temp_config, mock_confluence_client):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch('sys.argv', ['c2m_export', '--config', str(temp_config), '--overwrite']):
        main()

    expected_file = output_dir / "【TEST】 Test Page.md"
    assert expected_file.exists()

def test_cli_error_if_file_exists_and_no_overwrite(tmp_path, temp_config, mock_confluence_client):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Pre-create the file with suffix
    suffix = "_260503_160502"
    existing_file = output_dir / f"【TEST】 Test Page{suffix}.md"
    existing_file.write_text("existing content")

    with patch('sys.argv', ['c2m_export', '--config', str(temp_config)]):
        with patch('c2m_export.cli.datetime') as mock_date:
            mock_date.now.return_value.strftime.return_value = suffix
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 1

def test_cli_zip_output_with_suffix(tmp_path, temp_config, mock_confluence_client):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch('sys.argv', ['c2m_export', '--config', str(temp_config), '--zip']):
        with patch('c2m_export.cli.datetime') as mock_date:
            suffix = "_260503_160502"
            mock_date.now.return_value.strftime.return_value = suffix

            # We want to check if files inside the zip have correct names
            main()

    expected_zip = output_dir / "【TEST】 Test Page_260503_160502.zip"
    assert expected_zip.exists()

    # Verify content of ZIP
    import zipfile
    with zipfile.ZipFile(expected_zip, 'r') as z:
        names = z.namelist()
        assert len(names) == 1
        assert names[0] == "【TEST】 Test Page_260503_160502.md"
