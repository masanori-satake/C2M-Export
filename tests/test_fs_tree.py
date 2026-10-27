"""ツリー巡回とローカルパス割当のテスト."""

from unittest.mock import MagicMock

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
