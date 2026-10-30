from c2m_export.page_tree.annotations import aggregate_macros, classify_restriction, inline_marks
from c2m_export.page_tree.models import Annotation


def test_aggregate_macros():
    xhtml = """
    <p>Test</p>
    <ac:structured-macro ac:name="code"></ac:structured-macro>
    <ac:structured-macro ac:name="code"></ac:structured-macro>
    <div class="conf-macro" data-macro-name="plantuml"></div>
    """
    res = aggregate_macros(xhtml)
    assert res == {"code": 2, "plantuml": 1}


def test_classify_restriction():
    restrictions_data = {
        "read": {
            "restrictions": {
                "user": {"results": [{"username": "alice"}]},
                "group": {"results": [{"name": "dev-team"}]},
            }
        },
        "update": {
            "restrictions": {
                "user": {"results": [{"username": "bob"}]},
            }
        },
    }
    has_r, read_sub, rw_sub = classify_restriction(restrictions_data)
    assert has_r is True
    assert read_sub == ["user:alice", "group:dev-team"]
    assert rw_sub == ["user:bob"]


def test_inline_marks():
    ann = Annotation(
        has_restriction=True,
        attachment_count=3,
        macros={"code": 2, "plantuml": 1},
        last_modified="2025-08-20T10:00:00.000Z",
    )
    m = inline_marks(ann, ascii=False)
    assert "🔒" in m
    assert "📎3" in m
    assert "⚙2" in m  # 2 distinct macro types
    assert "(2025-08-20)" in m

    m_ascii = inline_marks(ann, ascii=True)
    assert "[R]" in m_ascii
    assert "att:3" in m_ascii
    assert "mac:2" in m_ascii
    assert "(2025-08-20)" in m_ascii
