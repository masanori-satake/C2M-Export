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
    for name in ["note", "info", "tip", "warning"]:
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
    assert "【ステータス: IN PROGRESS】" in md

def test_convert_jira_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    # Single issue
    html_single = '''
    <ac:structured-macro ac:name="jira">
        <ac:parameter ac:name="key">PROJ-123</ac:parameter>
    </ac:structured-macro>
    '''
    md_single = converter.convert(html_single)
    assert "【JIRA課題: PROJ-123】" in md_single

    # JQL Query
    html_jql = '''
    <ac:structured-macro ac:name="jira">
        <ac:parameter ac:name="jqlQuery">project = PROJ</ac:parameter>
    </ac:structured-macro>
    '''
    md_jql = converter.convert(html_jql)
    assert "【JIRAクエリ: project = PROJ】" in md_jql

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

def test_convert_noformat_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    html = '''
    <ac:structured-macro ac:name="noformat">
        <ac:plain-text-body><![CDATA[plain text here]]></ac:plain-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html)
    assert "```" in md
    assert "plain text here" in md

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
    assert "他ページからの埋め込み内容: Included Page Name" in md

def test_convert_irrelevant_macros():
    converter = MarkdownConverter("https://example.com/wiki")
    irrelevant_macros = ["toc", "anchor", "pagetree", "children", "contentbylabel"]
    for name in irrelevant_macros:
        html = f'<ac:structured-macro ac:name="{name}"></ac:structured-macro>'
        md = converter.convert(html)
        assert md.strip() == ""

def test_convert_empty_macros():
    converter = MarkdownConverter("https://example.com/wiki")

    # Code macro with no body
    html_code = '<ac:structured-macro ac:name="code"></ac:structured-macro>'
    assert converter.convert(html_code).strip() == ""

    # PlantUML macro with no body
    html_puml = '<ac:structured-macro ac:name="plantumlrender"></ac:structured-macro>'
    assert converter.convert(html_puml).strip() == ""

    # Jira macro with no params
    html_jira = '<ac:structured-macro ac:name="jira"></ac:structured-macro>'
    assert converter.convert(html_jira).strip() == ""

    # Include macro with no content-title
    html_include = '<ac:structured-macro ac:name="include"></ac:structured-macro>'
    assert converter.convert(html_include).strip() == ""

    # Legacy code macro with no pre
    html_legacy = '<div class="conf-macro" data-macro-name="code"></div>'
    assert converter.convert(html_legacy).strip() == ""

def test_header_level_shift_inside_macro():
    converter = MarkdownConverter("https://example.com/wiki")
    # level=2 means h1 should become ##
    html = '''
    <ac:structured-macro ac:name="expand">
        <ac:rich-text-body>
            <h1>Heading in Macro</h1>
        </ac:rich-text-body>
    </ac:structured-macro>
    '''
    md = converter.convert(html, level=2)
    assert "## Heading in Macro" in md
