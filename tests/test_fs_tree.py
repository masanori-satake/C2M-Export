"""ツリー巡回とローカルパス割当のテスト."""

from unittest.mock import MagicMock

import pytest

from c2m_export.fs_export.tree import build_page_tree


def test_build_page_tree_success():
    client = MagicMock()
    client.get_page.return_value = {
        "id": "100",
        "title": "ルートページ",
        "space": {"key": "DOC"},
    }
    client.get_child_pages.side_effect = [
        [
            {"id": "101", "title": "子ページA"},
            {"id": "102", "title": "子ページA"},  # タイトル重複
        ],
        [],  # 子ページ101の子
        [],  # 子ページ102の子
    ]

    root_nodes, renamed, visited = build_page_tree(
        client, root_page_ids=["100"], space_keys=[], page_filename_mode="title"
    )

    assert len(root_nodes) == 1
    root = root_nodes[0]
    assert root.page_id == "100"
    assert root.relative_dir_path == "【DOC】 ルートページ"
    assert root.body_file_name == "ルートページ.md"

    assert len(root.children) == 2
    c1, c2 = root.children
    assert c1.relative_dir_path == "【DOC】 ルートページ/子ページA"
    assert c1.body_file_name == "子ページA.md"

    assert c2.relative_dir_path == "【DOC】 ルートページ/子ページA (2)"
    assert c2.body_file_name == "子ページA (2).md"

    assert "102" in renamed
    assert "100" in visited and "101" in visited and "102" in visited


def test_build_page_tree_index_mode():
    client = MagicMock()
    client.get_page.return_value = {
        "id": "200",
        "title": "Top",
        "space": {"key": "KEY"},
    }
    client.get_child_pages.return_value = []

    root_nodes, _, _ = build_page_tree(client, root_page_ids=["200"], space_keys=[], page_filename_mode="index")

    assert root_nodes[0].body_file_name == "index.md"


def test_build_page_tree_records_root_failures_and_continues():
    client = MagicMock()
    client.get_page.side_effect = [RuntimeError("403 Forbidden"), {"id": "200", "title": "成功"}]
    client.get_child_pages.return_value = []
    skipped_pages = []

    root_nodes, _, visited = build_page_tree(client, ["100", "200"], [], skipped_pages=skipped_pages)

    assert [node.page_id for node in root_nodes] == ["200"]
    assert visited == {"200"}
    assert len(skipped_pages) == 1
    assert skipped_pages[0].target_id == "100"
    assert skipped_pages[0].target_type == "page"
    assert skipped_pages[0].reason == "ルートページ取得失敗 (403 Forbidden)"


def test_build_page_tree_records_space_failures_and_continues():
    client = MagicMock()
    client.get_space_root_pages.side_effect = [
        RuntimeError("403 Forbidden"),
        [{"id": "200", "title": "成功", "space": {"key": "DOC"}}],
    ]
    client.get_child_pages.return_value = []
    skipped_pages = []

    root_nodes, _, visited = build_page_tree(client, [], ["PRIVATE", "DOC"], skipped_pages=skipped_pages)

    assert [node.page_id for node in root_nodes] == ["200"]
    assert visited == {"200"}
    assert len(skipped_pages) == 1
    assert skipped_pages[0].target_id == "PRIVATE"
    assert skipped_pages[0].target_type == "space"
    assert skipped_pages[0].title_or_name == "Space PRIVATE"
    assert skipped_pages[0].reason == "Space ルートページ一覧取得失敗 (403 Forbidden)"


@pytest.mark.parametrize("failed_id", ["100", "101", "103"])
@pytest.mark.parametrize("from_space", [False, True])
def test_build_page_tree_records_child_failures_and_keeps_known_pages(failed_id, from_space):
    client = MagicMock()
    root = {"id": "100", "title": "Root", "space": {"key": "DOC"}}
    client.get_page.return_value = root
    client.get_space_root_pages.return_value = [root]
    children = {
        "100": [{"id": "101", "title": "Child"}, {"id": "102", "title": "Sibling"}],
        "101": [{"id": "103", "title": "Grandchild"}],
        "102": [],
        "103": [],
    }

    def get_children(page_id):
        if page_id == failed_id:
            raise RuntimeError("通信エラー")
        return children[page_id]

    client.get_child_pages.side_effect = get_children
    skipped_pages = []

    root_nodes, _, visited = build_page_tree(
        client, [] if from_space else ["100"], ["DOC"] if from_space else [], skipped_pages=skipped_pages
    )

    assert root_nodes[0].page_id == "100"
    expected_paths = {
        "100": ("Root", "【DOC】 Root"),
        "101": ("Child", "【DOC】 Root/Child"),
        "103": ("Grandchild", "【DOC】 Root/Child/Grandchild"),
    }
    assert len(skipped_pages) == 1
    failure = skipped_pages[0]
    assert failure.target_id == failed_id
    assert failure.target_type == "page"
    assert (failure.title_or_name, failure.path) == expected_paths[failed_id]
    assert failure.reason == "子ページ取得失敗 (通信エラー)"
    assert failed_id in visited
    if failed_id != "100":
        assert [node.page_id for node in root_nodes[0].children] == ["101", "102"]
        assert "102" in visited
    if failed_id == "103":
        assert root_nodes[0].children[0].children[0].page_id == "103"
