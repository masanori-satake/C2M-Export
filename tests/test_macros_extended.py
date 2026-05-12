import pytest
from c2m_export.converter import MarkdownConverter

def test_convert_expand_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="expand">
        <ac:parameter ac:name="title">Click to see more</ac:parameter>
        <ac:rich-text-body>
            <p>Hidden content here</p>
        </ac:rich-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "Click to see more" in md
    assert "Hidden content here" in md

def test_convert_admonition_macros():
    converter = MarkdownConverter("https://example.com/wiki")
    for name in ["note", "info", "tip"]:
        html = f'''
        <ac:structured-macro ac:name="{name}">
            <ac:rich-text-body>
                <p>This is a {name} message</p>
            </ac:rich-text-body>
        </ac:structured-macro>
        '''
        md = converter.convert(html)
        assert f"This is a {name} message" in md

def test_convert_panel_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="panel">
        <ac:parameter ac:name="title">Panel Title</ac:parameter>
        <ac:rich-text-body>
            <p>Panel content</p>
        </ac:rich-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "Panel Title" in md
    assert "Panel content" in md

def test_convert_details_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="details">
        <ac:rich-text-body>
            <table>
                <tr><td>Key</td><td>Value</td></tr>
            </table>
        </ac:rich-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "| Key | Value |" in md

def test_convert_status_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="status">
        <ac:parameter ac:name="title">IN PROGRESS</ac:parameter>
        <ac:parameter ac:name="colour">Yellow</ac:parameter>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "IN PROGRESS" in md

def test_convert_jira_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    # Single issue
    html_single = '''
    <ac:structured-macro ac:name="jira">
        <ac:parameter ac:name="key">PROJ-123</ac:parameter>
    </ac:structured-macro>
    '''
    md_single = converter.convert(html_single)
    assert "PROJ-123" in md_single

    # JQL Query
    html_jql = '''
    <ac:structured-macro ac:name="jira">
        <ac:parameter ac:name="jqlQuery">project = PROJ</ac:parameter>
    </ac:structured-macro>
    '''
    md_jql = converter.convert(html_jql)
    assert "project = PROJ" in md_jql

def test_convert_plantumlrender_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="plantumlrender">
        <ac:plain-text-body><![CDATA[alice -> bob]]></ac:plain-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "```plantuml" in md
    assert "alice -> bob" in md

def test_convert_include_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="include">
        <ac:parameter ac:name="">
            <ac:link>
                <ri:page ri:content-title="Included Page Name" />
            </ac:link>
        </ac:parameter>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "Included Page Name" in md

def test_convert_irrelevant_macros():
    converter = MarkdownConverter("https://example.com/wiki")
    irrelevant_macros = ["toc", "anchor", "pagetree", "children", "contentbylabel"]
    for name in irrelevant_macros:
        html = f'<ac:structured-macro ac:name="{name}"></ac:structured-macro>'
        md = converter.convert(html)
        assert md.strip() == ""
