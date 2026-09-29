"""Web エクスポートが部分成功を含めダウンロードまで完了することを検証する。"""
import io
import zipfile
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from c2m_export import web


def _run_web():
    from c2m_export.web import main
    main()


@pytest.mark.parametrize('zip_output', [False, True])
@pytest.mark.parametrize('skip_child', [False, True])
def test_web_export_completes(monkeypatch, zip_output, skip_child):
    client = MagicMock()
    client.base_url = 'https://example.com/wiki'
    page = {
        'title': 'Root', 'space': {'key': 'DEV'},
        'body': {'storage': {'value': '<p>exported body</p>'}},
        '_links': {'webui': '/pages/root'},
    }
    def get_page(page_id):
        if page_id != 'root':
            raise RuntimeError('子ページの取得失敗')
        return page

    client.get_page.side_effect = get_page
    client.get_child_pages.return_value = [{'id': 'child'}] if skip_child else []
    monkeypatch.setattr(web, 'ConfluenceClient', lambda *args: client)
    monkeypatch.setattr(web.Config, 'load', lambda self: None)

    app = AppTest.from_function(_run_web).run()
    for field in app.text_input:
        field.set_value({'Base URL': client.base_url, 'Token': 'test-token', 'Root Page ID #1': 'root'}[field.label])
    for checkbox in app.checkbox:
        checkbox.set_value(zip_output if checkbox.label == 'Zip圧縮してダウンロード' else False)
    next(button for button in app.button if button.label == 'エクスポート開始').click().run()

    assert not app.exception
    assert not app.error
    result = app.session_state.export_result
    if zip_output:
        assert result['mime'] == 'application/zip'
        with zipfile.ZipFile(io.BytesIO(result['data'])) as archive:
            assert archive.namelist() == ['【DEV】 Root.md']
            content = archive.read('【DEV】 Root.md').decode('utf-8')
    else:
        assert result['mime'] == 'text/markdown'
        assert result['file_name'] == '【DEV】 Root.md'
        content = result['data']
    assert 'exported body' in content
    assert '**Page ID**: child' not in content
    assert not web.export_lock.locked()
