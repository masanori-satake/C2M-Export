import pytest
from c2m_export.converter import MarkdownConverter

def test_convert_basic():
    converter = MarkdownConverter("https://example.com/wiki")
    html = "<h1>Title</h1><p>Hello <b>World</b></p>"
    md = converter.convert(html)
    assert "# Title" in md
    assert "Hello **World**" in md

def test_convert_table():
    converter = MarkdownConverter("https://example.com/wiki")
    html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>D1</td><td>D2</td></tr></table>"
    md = converter.convert(html)
    assert "| H1 | H2 |" in md
    assert "| --- | --- |" in md
    assert "| D1 | D2 |" in md

def test_convert_macros():
    converter = MarkdownConverter("https://example.com/wiki")
    # Code macro
    html_code = '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[print("hello")]]></ac:plain-text-body></ac:structured-macro>'
    md_code = converter.convert(html_code)
    assert "```" in md_code
    assert 'print("hello")' in md_code

    # PlantUML macro
    html_puml = '<ac:structured-macro ac:name="plantuml"><ac:plain-text-body><![CDATA[alice -> bob]]></ac:plain-text-body></ac:structured-macro>'
    md_puml = converter.convert(html_puml)
    assert "```plantuml" in md_puml
    assert "alice -> bob" in md_puml
