import json

from c2m_export.page_tree.models import Annotation, TreeNode, TreeResult
from c2m_export.page_tree.renderers import render_json, render_markdown, render_text, render_tree


def _sample_result():
    child = TreeNode(
        page_id="2",
        title="Child Page",
        annotation=Annotation(has_restriction=True, read_subjects=["group:dev"], attachment_count=2),
    )
    root = TreeNode(
        page_id="1",
        title="Root Page",
        annotation=Annotation(last_modified="2025-08-20T00:00:00Z"),
        children=[child],
    )
    return TreeResult(
        schema_version="1.0",
        status="ok",
        roots=[root],
        total_pages=2,
        included_annotations=["restriction", "attachments", "last_modified"],
        scope={"space_keys": ["TEST"], "root_page_ids": []},
    )


def test_render_text():
    res = _sample_result()
    output = render_text(res)
    assert "Root Page  [id:1] (2025-08-20)" in output
    assert "└── Child Page  [id:2] 🔒  📎2" in output


def test_render_markdown():
    res = _sample_result()
    output = render_markdown(res)
    assert "- Root Page `1` (2025-08-20)" in output
    assert "  - Child Page `2` 🔒  📎2" in output
    assert "## アクセス制限詳細" in output
    assert "| 2 | Child Page | group:dev | - |" in output


def test_render_json():
    res = _sample_result()
    output = render_json(res)
    data = json.loads(output)
    assert data["schema_version"] == "1.0"
    assert data["total_pages"] == 2
    assert len(data["roots"]) == 1
    assert data["roots"][0]["page_id"] == "1"
    assert data["roots"][0]["children"][0]["page_id"] == "2"


def test_render_tree_dispatcher():
    res = _sample_result()
    assert render_tree(res, fmt="text") == render_text(res)
    assert render_tree(res, fmt="markdown") == render_markdown(res)
    assert render_tree(res, fmt="json") == render_json(res)
