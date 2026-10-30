from c2m_export.page_tree.builder import build_tree
from c2m_export.page_tree.models import Annotation


def test_build_tree_hierarchy_and_cycle_prevention():
    root_ids = ["1"]
    children_map = {
        "1": [{"id": "2", "title": "Child 1"}, {"id": "3", "title": "Child 2"}],
        "2": [{"id": "1", "title": "Root (cycle)"}, {"id": "4", "title": "Grandchild"}],
    }
    annotations_map = {
        "1": Annotation(attachment_count=1),
        "2": Annotation(has_restriction=True),
    }
    page_titles_map = {"1": "Root Page"}

    roots, total_count = build_tree(root_ids, children_map, annotations_map, page_titles_map)

    assert len(roots) == 1
    root_node = roots[0]
    assert root_node.page_id == "1"
    assert root_node.title == "Root Page"
    assert root_node.annotation.attachment_count == 1
    assert len(root_node.children) == 2

    # Child 1
    c1 = root_node.children[0]
    assert c1.page_id == "2"
    assert c1.title == "Child 1"
    assert len(c1.children) == 1  # Cycle "1" avoided, only "4" included

    gc = c1.children[0]
    assert gc.page_id == "4"

    # Total pages visited uniquely
    assert total_count == 4  # "1", "2", "3", "4"


def test_build_tree_max_depth():
    root_ids = ["1"]
    children_map = {
        "1": [{"id": "2", "title": "Child 1"}],
        "2": [{"id": "3", "title": "Grandchild 1"}],
    }
    page_titles_map = {"1": "Root"}

    roots, _ = build_tree(root_ids, children_map, {}, page_titles_map, max_depth=2)
    assert len(roots[0].children) == 1
    c1 = roots[0].children[0]
    assert c1.page_id == "2"
    assert len(c1.children) == 0  # Depth 3 truncated
