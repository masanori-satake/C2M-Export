"""堅牢性・波及防止に関するテスト。

- コードフェンスの動的伸長（構文汚染防止 / 要件15）
- 変換器レベルの例外非伝播（要件14）
- CLI レベルの波及防止・部分成功・ログ（要件14）
- ページ連結でのコードフェンス波及防止（要件15.3）
"""

import re
import logging
import pytest

from c2m_export.converter import MarkdownConverter


# ---------------------------------------------------------------------------
# タスク2: コードフェンスの動的伸長（対策1の単体検証 / 要件15.1, 15.2）
# ---------------------------------------------------------------------------


def test_wrap_code_block_normal_uses_three_backticks():
    """通常のコード（バッククォートを含まない）は 3 連フェンスのまま（退行防止）。"""
    converter = MarkdownConverter("https://example.com/wiki")
    md = converter._wrap_code_block("print('hello')", "python")
    assert "```python" in md
    # 4 連以上のフェンスは使われない
    assert "````" not in md


def test_wrap_code_block_extends_over_triple_backtick():
    """中身に ``` を含む場合、フェンスは 4 連以上に伸長され、開閉が一致する。"""
    converter = MarkdownConverter("https://example.com/wiki")
    content = "before\n```\ninner\n```\nafter"
    md = converter._wrap_code_block(content)

    fences = re.findall(r"`{3,}", md.replace(content, ""))
    # 開き・閉じの 2 つのフェンスが検出され、いずれも 4 連以上
    assert len(fences) == 2
    assert all(len(f) >= 4 for f in fences)
    # 開きと閉じの長さが一致
    assert len(fences[0]) == len(fences[1])


def test_wrap_code_block_extends_over_quad_backtick():
    """中身に 4 連バッククォートを含む場合、フェンスは 5 連以上になる。"""
    converter = MarkdownConverter("https://example.com/wiki")
    content = "x ```` y"
    md = converter._wrap_code_block(content)

    # 中身の 4 連を除いた、囲みフェンスを取り出す
    stripped = md.replace(content, "")
    fences = re.findall(r"`{3,}", stripped)
    assert len(fences) == 2
    assert all(len(f) >= 5 for f in fences)
    assert len(fences[0]) == len(fences[1])


def test_code_macro_with_inner_fence_does_not_leak():
    """コードマクロの中身に ``` が含まれても、変換結果でフェンスが割れない。"""
    converter = MarkdownConverter("https://example.com/wiki")
    html = (
        '<ac:structured-macro ac:name="code">'
        '<ac:plain-text-body><![CDATA[echo "```"]]></ac:plain-text-body>'
        "</ac:structured-macro>"
    )
    md = converter.convert(html)
    # 中身の ``` (3連) を包む外側フェンスは 4 連以上になる。
    # 外側フェンス（4連以上）が開閉ペアで揃っていることを確認する。
    outer_fences = re.findall(r"`{4,}", md)
    assert len(outer_fences) == 2
    assert len(outer_fences[0]) == len(outer_fences[1])
    # 中身の 3 連が外側フェンスより短いことで無害化されている
    assert all(len(f) > 3 for f in outer_fences)


# ---------------------------------------------------------------------------
# タスク14: 変換器レベルの堅牢性（例外を投げず情報を残す / 要件14.1, 14.2, 14.7）
# ---------------------------------------------------------------------------


def test_incomplete_xhtml_does_not_raise():
    """閉じタグ欠落・途中で切れた XHTML でも例外を投げず部分テキストを返す。"""
    converter = MarkdownConverter("https://example.com/wiki")
    broken = "<p>start<strong>bold text <table><tr><td>cell"
    md = converter.convert(broken)  # 例外が出ないこと
    assert "start" in md
    assert "cell" in md


def test_empty_body_returns_empty():
    converter = MarkdownConverter("https://example.com/wiki")
    assert converter.convert("").strip() == ""


def test_img_without_src_keeps_alt():
    converter = MarkdownConverter("https://example.com/wiki")
    md = converter.convert('<img alt="only alt" />')
    assert "only alt" in md


def test_ac_image_without_reference_does_not_raise():
    converter = MarkdownConverter("https://example.com/wiki")
    md = converter.convert('<ac:image ac:alt="lonely" />')  # 参照なし
    assert "lonely" in md


def test_ac_link_without_target_does_not_raise():
    converter = MarkdownConverter("https://example.com/wiki")
    # ri:page も ri:user も無いリンク
    md = converter.convert("<ac:link></ac:link>")
    assert isinstance(md, str)


def test_uneven_columns_table_does_not_raise():
    converter = MarkdownConverter("https://example.com/wiki")
    html = "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>x</td></tr></tbody></table>"
    md = converter.convert(html)  # 列数不揃いでも例外を投げない
    assert "| A | B |" in md
    assert "| x |" in md


def test_thead_only_empty_tbody_does_not_raise():
    converter = MarkdownConverter("https://example.com/wiki")
    html = "<table><thead><tr><th>H</th></tr></thead><tbody></tbody></table>"
    md = converter.convert(html)
    assert "| H |" in md


# ---------------------------------------------------------------------------
# タスク16: CLI レベルの波及防止・部分成功・ログ（要件14.3〜14.6）
# タスク17: ページ連結でのコードフェンス波及防止（要件15.3）
# ---------------------------------------------------------------------------

from c2m_export.cli import export_tree


class _StubClient:
    """export_tree テスト用の軽量スタブ。

    pages: {page_id: {"title", "body", "children": [child_id, ...], "raise": bool}}
    """

    def __init__(self, pages, base_url="https://example.com/wiki"):
        self.base_url = base_url
        self._pages = pages

    def get_page(self, page_id):
        page = self._pages[page_id]
        if page.get("raise"):
            raise RuntimeError(f"疑似的な取得失敗: {page_id}")
        return {
            "title": page["title"],
            "space": {"key": "DEV"},
            "body": {"storage": {"value": page.get("body", "")}},
            "_links": {"webui": f"/pages/{page_id}"},
        }

    def get_child_pages(self, page_id):
        children = self._pages[page_id].get("children", [])
        return [{"id": cid} for cid in children]


def test_export_tree_skips_failing_page_and_continues(caplog):
    """途中ページの取得失敗が後続に波及せず、部分成功で出力される。"""
    pages = {
        "root": {"title": "Root", "body": "<p>root body</p>", "children": ["c1", "c2"]},
        "c1": {"title": "Child1", "raise": True},  # 2 ページ目で失敗
        "c2": {"title": "Child2", "body": "<p>child2 body</p>"},
    }
    client = _StubClient(pages)
    converter = MarkdownConverter(client.base_url)

    with caplog.at_level(logging.WARNING):
        md, total_bytes, page_count, skipped = export_tree(client, converter, "root", stop_threshold_mb=100.0)

    # 例外は外に漏れず、成功ページの内容が含まれる（部分成功）
    assert "root body" in md
    assert "child2 body" in md
    # 失敗ページはスキップされ、成功数は 2（root, c2）
    assert page_count == 2
    assert "c1" in skipped
    # スキップと完了サマリのログが出る
    assert any("スキップ" in r.message for r in caplog.records)


def test_export_tree_no_skip_logs_success(caplog):
    pages = {
        "root": {"title": "Root", "body": "<p>ok</p>", "children": []},
    }
    client = _StubClient(pages)
    converter = MarkdownConverter(client.base_url)

    with caplog.at_level(logging.INFO):
        md, total_bytes, page_count, skipped = export_tree(client, converter, "root", stop_threshold_mb=100.0)

    assert skipped == []
    assert page_count == 1


def test_page_concatenation_code_fence_does_not_leak():
    """1 ページ目のコードブロックが 2 ページ目本文を巻き込まない（フェンス波及防止）。"""
    # 中身に ``` を含むコードマクロを持つページ + 通常本文ページ
    code_page_body = (
        '<ac:structured-macro ac:name="code">'
        '<ac:plain-text-body><![CDATA[echo "```"]]></ac:plain-text-body>'
        "</ac:structured-macro>"
    )
    pages = {
        "root": {"title": "CodePage", "body": code_page_body, "children": ["c1"]},
        "c1": {"title": "NextPage", "body": "<p>normal following text</p>"},
    }
    client = _StubClient(pages)
    converter = MarkdownConverter(client.base_url)

    md, _, page_count, skipped = export_tree(client, converter, "root", stop_threshold_mb=100.0)

    assert page_count == 2
    assert skipped == []
    # 外側フェンス（4連以上）が開閉ペアで揃っている = すべてのコードブロックが閉じている
    outer = re.findall(r"`{4,}", md)
    assert len(outer) % 2 == 0
    # 後続ページの本文が確実に出力されている（コードに飲まれていない）
    assert "normal following text" in md


@pytest.mark.parametrize("failed_id", ["root", "c1"])
def test_child_listing_failure_does_not_count_skipped_page(monkeypatch, caplog, failed_id):
    """子ページ取得失敗時も本文・バイト数・成功数・スキップ一覧が整合する。"""
    pages = {
        "root": {"title": "Root", "body": "<p>root body</p>", "children": ["c1", "c2"]},
        "c1": {"title": "Child1", "body": "<p>child1 body</p>"},
        "c2": {"title": "Child2", "body": "<p>child2 body</p>"},
    }
    client = _StubClient(pages)
    get_children = client.get_child_pages

    def failing_children(page_id):
        if page_id == failed_id:
            raise RuntimeError("子ページ一覧の取得失敗")
        return get_children(page_id)

    monkeypatch.setattr(client, "get_child_pages", failing_children)
    with caplog.at_level(logging.WARNING):
        md, total_bytes, count, skipped = export_tree(client, MarkdownConverter(client.base_url), "root", 100.0)

    assert skipped == [failed_id]
    assert f"**Page ID**: {failed_id}\n" not in md
    assert total_bytes == len(md.encode("utf-8"))
    assert count == (0 if failed_id == "root" else 2)
    if failed_id == "c1":
        assert "root body" in md
        assert "child2 body" in md
    assert any(f"成功 {count} ページ / スキップ 1 ページ" in r.message for r in caplog.records)
