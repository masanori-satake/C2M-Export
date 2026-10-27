"""差分判定純粋ロジック (diff.py) の単体テスト."""

from c2m_export.fs_export.diff import ActionType, compute_diff
from c2m_export.fs_export.manifest import (
    AttachmentManifestEntry,
    Manifest,
    ManifestRoots,
    PageManifestEntry,
)
from c2m_export.fs_export.sync import (
    AttachmentInventoryEntry,
    Inventory,
    PageInventoryEntry,
)


def test_compute_diff_all_actions():
    """追加、変更、移動・改名、削除、未変更の各アクションが正確に判定されることを検証する."""
    # 前回マニフェスト
    prev_pages = {
        "100": PageManifestEntry(
            version=1,
            title="Unchanged Page",
            parent_id=None,
            rel_path="【DEV】Unchanged Page",
            body_file="Unchanged Page.md",
            state="done",
        ),
        "200": PageManifestEntry(
            version=1,
            title="Old Title",  # 今後 MOVE_RENAME
            parent_id=None,
            rel_path="【DEV】Old Title",
            body_file="Old Title.md",
            state="done",
        ),
        "300": PageManifestEntry(
            version=1,
            title="Updated Page",  # 今後 CHANGE (version 1 -> 2)
            parent_id=None,
            rel_path="【DEV】Updated Page",
            body_file="Updated Page.md",
            state="done",
        ),
        "400": PageManifestEntry(
            version=1,
            title="Deleted Page",  # 今後 DELETE
            parent_id=None,
            rel_path="【DEV】Deleted Page",
            body_file="Deleted Page.md",
            state="done",
        ),
        "500": PageManifestEntry(
            version=1,
            title="Failed Fetch Page",  # 取得失敗により削除保留されるべき
            parent_id=None,
            rel_path="【DEV】Failed Fetch Page",
            body_file="Failed Fetch Page.md",
            state="done",
        ),
    }
    manifest = Manifest(
        base_url="https://confluence.example.com",
        roots=ManifestRoots(root_page_ids=["100"], space_keys=["DEV"]),
        pages=prev_pages,
    )

    # 現在インベントリ
    curr_pages = {
        "100": PageInventoryEntry(
            page_id="100",
            version=1,
            title="Unchanged Page",
            parent_id=None,
            space_key="DEV",
        ),
        "200": PageInventoryEntry(
            page_id="200",
            version=1,
            title="New Title",  # タイトル変更
            parent_id=None,
            space_key="DEV",
        ),
        "300": PageInventoryEntry(
            page_id="300",
            version=2,  # バージョン変更
            title="Updated Page",
            parent_id=None,
            space_key="DEV",
        ),
        "600": PageInventoryEntry(
            page_id="600",
            version=1,
            title="Newly Added Page",  # 新規追加
            parent_id=None,
            space_key="DEV",
        ),
    }

    inventory = Inventory(
        pages=curr_pages,
        failed_page_ids={"500"},  # 500 は通信エラー
    )

    plan = compute_diff(manifest, inventory)

    assert plan.add_count == 1
    assert plan.change_count == 1
    assert plan.move_rename_count == 1
    assert plan.delete_count == 1
    assert plan.unchanged_count == 1

    actions_by_id = {a.page_id: a for a in plan.page_actions}

    assert actions_by_id["600"].action == ActionType.ADD
    assert actions_by_id["300"].action == ActionType.CHANGE
    assert actions_by_id["200"].action == ActionType.MOVE_RENAME
    assert actions_by_id["100"].action == ActionType.UNCHANGED
    assert actions_by_id["400"].action == ActionType.DELETE
    assert "500" not in actions_by_id  # 失敗したページは削除アクションに含まれないこと


def test_compute_diff_defers_all_deletions_when_discovery_is_incomplete():
    """探索できなかった子孫と添付の削除を保留し、確認できた追加・変更は判定する."""
    manifest = Manifest(
        base_url="https://confluence.example.com",
        roots=ManifestRoots(root_page_ids=["100"]),
        pages={
            "100": PageManifestEntry(
                1,
                "Root",
                None,
                "【DEV】 Root",
                "Root.md",
                attachments={"old": AttachmentManifestEntry(1, 3, "old.txt")},
            ),
            "200": PageManifestEntry(1, "Child", "100", "【DEV】 Root/Child", "Child.md"),
            "300": PageManifestEntry(1, "Grandchild", "200", "【DEV】 Root/Child/Grandchild", "Grandchild.md"),
        },
    )
    inventory = Inventory(
        discovery_incomplete=True,
        pages={
            "100": PageInventoryEntry("100", 2, "Root", None, "DEV"),
            "400": PageInventoryEntry("400", 1, "New", "100", "DEV"),
        },
    )

    plan = compute_diff(manifest, inventory)

    assert plan.delete_count == 0
    assert plan.change_count == 1
    assert plan.add_count == 1
    assert all(a.action != ActionType.DELETE for page in plan.page_actions for a in page.attachment_actions)
