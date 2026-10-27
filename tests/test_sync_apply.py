"""同期・レジューム実行ロジック (execute_sync) の単体テスト."""

import os
from unittest.mock import MagicMock

import pytest

from c2m_export.fs_export.diff import ActionType, DiffPlan, PageDiffAction
from c2m_export.fs_export.manifest import (
    Manifest,
    ManifestRoots,
    PageManifestEntry,
    load_manifest,
)
from c2m_export.fs_export.sync import (
    Inventory,
    PageInventoryEntry,
    execute_sync,
)


def test_execute_sync_apply_plan(tmp_path):
    """execute_sync が DiffPlan (追加、移動・改名、削除) を適用し、実ファイルとマニフェストを正しく更新することを検証する."""
    out_dir = str(tmp_path)

    # 既存のローカルファイル（旧タイトルのページ）を準備
    old_page_dir = os.path.join(out_dir, "【DEV】 Old Title")
    os.makedirs(old_page_dir, exist_ok=True)
    old_body = os.path.join(old_page_dir, "Old Title.md")
    with open(old_body, "w", encoding="utf-8") as f:
        f.write("old content")

    # 削除対象のローカルファイル
    del_page_dir = os.path.join(out_dir, "【DEV】 Delete Me")
    os.makedirs(del_page_dir, exist_ok=True)
    with open(os.path.join(del_page_dir, "Delete Me.md"), "w", encoding="utf-8") as f:
        f.write("delete content")

    manifest = Manifest(
        base_url="https://confluence.example.com",
        roots=ManifestRoots(root_page_ids=["100", "200"], space_keys=["DEV"]),
        pages={
            "100": PageManifestEntry(
                version=1,
                title="Old Title",
                parent_id=None,
                rel_path="【DEV】 Old Title",
                body_file="Old Title.md",
                state="done",
            ),
            "200": PageManifestEntry(
                version=1,
                title="Delete Me",
                parent_id=None,
                rel_path="【DEV】 Delete Me",
                body_file="Delete Me.md",
                state="done",
            ),
        },
    )

    inventory = Inventory(
        pages={
            "100": PageInventoryEntry(page_id="100", version=1, title="New Title", parent_id=None, space_key="DEV"),
            "300": PageInventoryEntry(page_id="300", version=1, title="Added Page", parent_id=None, space_key="DEV"),
        }
    )

    plan = DiffPlan(
        page_actions=[
            PageDiffAction(
                page_id="100",
                action=ActionType.MOVE_RENAME,
                current_version=1,
                current_title="New Title",
                current_parent_id=None,
                old_entry=manifest.pages["100"],
            ),
            PageDiffAction(
                page_id="200",
                action=ActionType.DELETE,
                current_version=1,
                current_title="Delete Me",
                current_parent_id=None,
                old_entry=manifest.pages["200"],
            ),
            PageDiffAction(
                page_id="300",
                action=ActionType.ADD,
                current_version=1,
                current_title="Added Page",
                current_parent_id=None,
            ),
        ]
    )

    client = MagicMock()
    client.get_page.side_effect = lambda pid, expand=None: {
        "100": {
            "id": "100",
            "title": "New Title",
            "version": {"number": 1},
            "body": {"storage": {"value": "<p>Updated Content</p>"}},
            "space": {"key": "DEV"},
        },
        "300": {
            "id": "300",
            "title": "Added Page",
            "version": {"number": 1},
            "body": {"storage": {"value": "<p>Added Content</p>"}},
            "space": {"key": "DEV"},
        },
    }[pid]
    client.get_attachments.return_value = []

    converter = MagicMock()
    converter.convert.return_value = "Converted Content"

    execute_sync(
        client=client,
        converter=converter,
        output_dir=out_dir,
        manifest=manifest,
        inventory=inventory,
        plan=plan,
        base_url="https://confluence.example.com",
    )

    # 検証: 削除対象が元ディレクトリからなくなっていること（退避先へ移動）
    assert not os.path.exists(del_page_dir)

    # 検証: 旧ディレクトリ名が新ディレクトリ名に変更されていること
    assert not os.path.exists(old_page_dir)
    new_page_dir = os.path.join(out_dir, "【DEV】 New Title")
    assert os.path.exists(new_page_dir)
    assert os.path.exists(os.path.join(new_page_dir, "New Title.md"))

    # 検証: 追加されたページが存在すること
    added_page_dir = os.path.join(out_dir, "【DEV】 Added Page")
    assert os.path.exists(added_page_dir)

    # 検証: マニフェストが正常に保存され更新されていること
    saved_m = load_manifest(out_dir)
    assert saved_m is not None
    assert saved_m.completed is True
    assert "200" not in saved_m.pages
    assert "100" in saved_m.pages
    assert saved_m.pages["100"].title == "New Title"
    assert "300" in saved_m.pages
    assert saved_m.pages["300"].title == "Added Page"
