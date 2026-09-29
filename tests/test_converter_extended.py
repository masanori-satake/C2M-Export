"""拡充された Markdown 変換表現のテスト（spec 0002）。

表の再設計、インライン/ブロック要素、ネストリスト、タスクリスト、画像、
ページリンク・メンション・絵文字・レイアウトなどを検証する。
"""
import pytest

from c2m_export.converter import MarkdownConverter


@pytest.fixture
def converter():
    return MarkdownConverter("https://example.com/wiki")


# ---------------------------------------------------------------------------
# タスク4: 表変換（要件1, 12）
# ---------------------------------------------------------------------------

def test_table_with_thead_tbody(converter):
    """thead/tbody で囲まれた表が消えず、ヘッダー・ボディともに出力される。"""
    html = """
    <table>
        <thead><tr><th>H1</th><th>H2</th></tr></thead>
        <tbody>
            <tr><td>D1</td><td>D2</td></tr>
            <tr><td>D3</td><td>D4</td></tr>
        </tbody>
    </table>
    """
    md = converter.convert(html)
    assert "| H1 | H2 |" in md
    assert "| --- | --- |" in md
    assert "| D1 | D2 |" in md
    assert "| D3 | D4 |" in md


def test_table_tbody_only_first_th_is_header(converter):
    """thead が無く tbody のみでも、先頭行が th を含めばヘッダーになる。"""
    html = """
    <table>
        <tbody>
            <tr><th>Key</th><th>Value</th></tr>
            <tr><td>a</td><td>b</td></tr>
        </tbody>
    </table>
    """
    md = converter.convert(html)
    assert "| Key | Value |" in md
    assert "| --- | --- |" in md
    assert "| a | b |" in md


def test_table_without_header(converter):
    """全 td でヘッダーが特定できない表は、空ヘッダー + 区切り線を出力する。"""
    html = """
    <table>
        <tbody>
            <tr><td>D1</td><td>D2</td></tr>
        </tbody>
    </table>
    """
    md = converter.convert(html)
    assert "| --- | --- |" in md
    assert "| D1 | D2 |" in md
    # 空ヘッダー行が存在する
    assert "|  |  |" in md


def test_table_direct_tr_backward_compat(converter):
    """table 直下に tr を持つ従来形式も引き続き変換できる（後方互換）。"""
    html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>D1</td><td>D2</td></tr></table>"
    md = converter.convert(html)
    assert "| H1 | H2 |" in md
    assert "| D1 | D2 |" in md


def test_table_cell_pipe_escaped(converter):
    """セル内の | がエスケープされ、表が破綻しない。"""
    html = "<table><tr><th>H</th></tr><tr><td>a|b</td></tr></table>"
    md = converter.convert(html)
    assert "a\\|b" in md


# ---------------------------------------------------------------------------
# タスク6: インライン/ブロック要素（要件2,3,4,9,10,11）
# ---------------------------------------------------------------------------

def test_blockquote(converter):
    html = "<blockquote><p>quoted text</p></blockquote>"
    md = converter.convert(html)
    assert "> quoted text" in md


def test_horizontal_rule(converter):
    md = converter.convert("<hr/>")
    assert "---" in md


def test_strikethrough(converter):
    md = converter.convert("<p>a <del>gone</del> b</p>")
    assert "~~gone~~" in md


def test_underline_keeps_text(converter):
    md = converter.convert("<p>a <u>underlined</u> b</p>")
    assert "underlined" in md


def test_superscript_subscript_keep_text(converter):
    md = converter.convert("<p>H<sub>2</sub>O and x<sup>2</sup></p>")
    assert "H2O" in md
    assert "x2" in md


def test_pre_block(converter):
    md = converter.convert("<pre>plain code line</pre>")
    assert "```" in md
    assert "plain code line" in md


def test_definition_list(converter):
    html = "<dl><dt>Term</dt><dd>Definition</dd></dl>"
    md = converter.convert(html)
    assert "**Term**" in md
    assert "Definition" in md


# ---------------------------------------------------------------------------
# タスク8: ネストリスト（要件5）
# ---------------------------------------------------------------------------

def test_nested_unordered_list_indent(converter):
    html = "<ul><li>parent<ul><li>child</li></ul></li></ul>"
    md = converter.convert(html)
    assert "- parent" in md
    # 子項目はインデントされる
    assert "  - child" in md


def test_nested_ordered_list(converter):
    html = "<ol><li>first<ol><li>sub</li></ol></li></ol>"
    md = converter.convert(html)
    assert "1. first" in md
    assert "  1. sub" in md


# ---------------------------------------------------------------------------
# タスク12: タスクリスト・画像・リンク・固有要素（要件6,7,8,11）
# ---------------------------------------------------------------------------

def test_task_list(converter):
    html = (
        "<ac:task-list>"
        "<ac:task><ac:task-status>complete</ac:task-status><ac:task-body>done item</ac:task-body></ac:task>"
        "<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>todo item</ac:task-body></ac:task>"
        "</ac:task-list>"
    )
    md = converter.convert(html)
    assert "- [x] done item" in md
    assert "- [ ] todo item" in md


def test_img_tag(converter):
    md = converter.convert('<img src="/download/x.png" alt="diagram" />')
    assert "![diagram](https://example.com/wiki/download/x.png)" in md


def test_ac_image_attachment(converter):
    html = '<ac:image ac:alt="figure"><ri:attachment ri:filename="a.png" /></ac:image>'
    md = converter.convert(html)
    assert "![figure](a.png)" in md


def test_ac_image_url(converter):
    html = '<ac:image><ri:url ri:value="https://cdn.example.com/b.png" /></ac:image>'
    md = converter.convert(html)
    assert "https://cdn.example.com/b.png" in md


def test_ac_link_page_with_space_key(converter):
    html = '<ac:link><ri:page ri:content-title="My Page" ri:space-key="DEV" /></ac:link>'
    md = converter.convert(html)
    assert "[My Page](https://example.com/wiki/display/DEV/My%20Page)" in md


def test_ac_link_page_without_space_key_keeps_title(converter):
    html = '<ac:link><ri:page ri:content-title="Orphan Page" /></ac:link>'
    md = converter.convert(html)
    assert "Orphan Page" in md
    # URL は付かない
    assert "](http" not in md


def test_ac_link_page_display_text_priority(converter):
    html = (
        '<ac:link><ri:page ri:content-title="Real Title" ri:space-key="DEV" />'
        '<ac:plain-text-link-body>Display Text</ac:plain-text-link-body></ac:link>'
    )
    md = converter.convert(html)
    assert "[Display Text](https://example.com/wiki/display/DEV/Real%20Title)" in md


def test_ac_link_user_mention(converter):
    html = '<ac:link><ri:user ri:username="jdoe" /></ac:link>'
    md = converter.convert(html)
    assert "@jdoe" in md


def test_ac_emoticon(converter):
    html = '<p><ac:emoticon ac:name="smile" ac:emoji-fallback="\U0001F642" /></p>'
    md = converter.convert(html)
    assert "\U0001F642" in md


def test_ac_layout_keeps_content(converter):
    html = (
        "<ac:layout><ac:layout-section><ac:layout-cell><p>cell content</p>"
        "</ac:layout-cell></ac:layout-section></ac:layout>"
    )
    md = converter.convert(html)
    assert "cell content" in md
