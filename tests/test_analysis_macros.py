from c2m_export.analysis.macros import count_macros, summarize_macros
from c2m_export.assessment.models import PageMeta


def test_count_macros():
    html = """
    <div>
        <ac:structured-macro ac:name="toc"></ac:structured-macro>
        <ac:structured-macro ac:name="code"></ac:structured-macro>
        <div class="conf-macro output-block" data-macro-name="jira"></div>
        <ac:structured-macro ac:name="toc"></ac:structured-macro>
    </div>
    """
    counts = count_macros(html)
    assert counts["toc"] == 2
    assert counts["code"] == 1
    assert counts["jira"] == 1


def test_summarize_macros():
    p1 = PageMeta("100", "Page A", "SPACE", 1, 100, None, [])
    p1.macro_counts = {"toc": 2, "jira": 1, "custom_macro": 3}  # type: ignore[attr-defined]

    results = summarize_macros([p1])
    res_dict = {r["name"]: r for r in results}

    assert res_dict["toc"]["count"] == 2
    assert res_dict["toc"]["repair_category"] == "content_loss"

    assert res_dict["jira"]["count"] == 1
    assert res_dict["jira"]["repair_category"] == "external_dependency"

    assert res_dict["custom_macro"]["count"] == 3
    assert res_dict["custom_macro"]["repair_category"] == "unknown"
