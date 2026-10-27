"""同期時の各階層のパス割当を検証する."""

import pytest

from c2m_export.fs_export.sync import Inventory, PageInventoryEntry, compute_paths_for_inventory


@pytest.mark.parametrize("mode", ["title", "index"])
def test_paths_are_unique_for_siblings_at_every_depth(mode):
    """ルート・子・孫・ひ孫でも同名の兄弟に別々の保存先を割り当てる."""
    inventory = Inventory(
        pages={
            pid: PageInventoryEntry(pid, 1, "Same", parent, "DEV")
            for pid, parent in [
                ("r1", None),
                ("r2", None),
                ("c1", "r1"),
                ("c2", "r1"),
                ("g1", "c1"),
                ("g2", "c1"),
                ("gg1", "g2"),
                ("gg2", "g2"),
            ]
        }
    )

    paths = compute_paths_for_inventory(inventory, mode)

    expected_dirs = {
        "r1": "【DEV】 Same",
        "r2": "【DEV】 Same (2)",
        "c1": "【DEV】 Same/Same",
        "c2": "【DEV】 Same/Same (2)",
        "g1": "【DEV】 Same/Same/Same",
        "g2": "【DEV】 Same/Same/Same (2)",
        "gg1": "【DEV】 Same/Same/Same (2)/Same",
        "gg2": "【DEV】 Same/Same/Same (2)/Same (2)",
    }
    assert {pid: path for pid, (path, _) in paths.items()} == expected_dirs
    assert len(set(paths.values())) == len(inventory.pages)
    for pid, (_, body) in paths.items():
        expected_body = "Same.md" if pid.startswith("r") else expected_dirs[pid].rsplit("/", 1)[-1] + ".md"
        assert body == ("index.md" if mode == "index" else expected_body)
