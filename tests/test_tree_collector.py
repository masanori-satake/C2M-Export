from unittest.mock import MagicMock

from c2m_export.confluence import ConfluenceClient
from c2m_export.page_tree.collector import collect_tree


def test_collect_tree_empty_include():
    client = MagicMock(spec=ConfluenceClient)
    client.get_space_root_pages.return_value = [{"id": "1", "title": "Home"}]
    client.get_child_pages.side_effect = lambda pid: [{"id": "2", "title": "Child"}] if pid == "1" else []

    resolved_roots, children_map, annotations_map, page_titles_map, uncertainties = collect_tree(
        client=client,
        space_keys=["TEST"],
        include=set(),
    )

    assert resolved_roots == ["1"]
    assert len(children_map["1"]) == 1
    assert page_titles_map["1"] == "Home"
    assert page_titles_map["2"] == "Child"

    # Verify no additional API calls were made!
    client.get_restrictions.assert_not_called()
    client.get_page.assert_not_called()
    client.get_attachments.assert_not_called()


def test_collect_tree_with_opt_in_and_failure_handling():
    client = MagicMock(spec=ConfluenceClient)
    client.get_page.side_effect = lambda pid, expand="": (
        {
            "title": f"Root {pid}",
            "body": {"storage": {"value": '<ac:structured-macro ac:name="code"/>'}},
            "version": {"when": "2025-08-20T00:00:00Z"},
        }
        if expand != "version" or pid == "1"
        else {"title": f"Page {pid}"}
    )
    client.get_child_pages.return_value = []
    client.get_restrictions.side_effect = Exception("Forbidden")
    client.get_attachments.return_value = [{"id": "att1"}]

    resolved_roots, children_map, annotations_map, page_titles_map, uncertainties = collect_tree(
        client=client,
        root_page_ids=["1"],
        include={"restriction", "macros", "attachments", "last_modified"},
    )

    assert resolved_roots == ["1"]
    assert "1" in annotations_map
    ann = annotations_map["1"]

    assert "restriction" in ann.failed_fields
    assert uncertainties["restriction_failed"] == 1

    assert ann.attachment_count == 1
    assert ann.macros == {"code": 1}
    assert ann.last_modified == "2025-08-20T00:00:00Z"
