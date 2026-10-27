"""同期・レジューム実行ロジック (execute_sync) の単体テスト."""

import os
from unittest.mock import MagicMock

import pytest

from c2m_export.fs_export.diff import ActionType, DiffPlan, PageDiffAction, compute_diff
from c2m_export.fs_export.manifest import (
    AttachmentManifestEntry,
    Manifest,
    ManifestRoots,
    PageManifestEntry,
    load_manifest,
)
from c2m_export.fs_export.sync import (
    AttachmentInventoryEntry,
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


def _sync_client():
    """本文取得と実際の添付書き込みを行うテスト用クライアントを返す."""
    client = MagicMock()
    client.get_page.return_value = {
        "version": {"number": 1},
        "body": {"storage": {"value": "<p>本文</p>"}},
        "space": {"key": "DEV"},
    }
    client.get_attachments.return_value = []

    def download(download_path, dest_file, max_bytes):
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        with open(dest_file, "wb") as attachment:
            return attachment.write(b"new")

    client.download_attachment.side_effect = download
    return client


@pytest.mark.parametrize("reverse_order", [False, True])
def test_sync_moves_parent_and_descendants_without_leaving_old_directories(tmp_path, reverse_order):
    """親子孫を同時に改名しても、処理順によらず既存の添付と階層を保全する."""
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(root_page_ids=["r"]),
        pages={
            "r": PageManifestEntry(1, "Old Root", None, "【DEV】 Old Root", "Old Root.md"),
            "c": PageManifestEntry(1, "Old Child", "r", "【DEV】 Old Root/Old Child", "Old Child.md"),
            "g": PageManifestEntry(
                1, "Old Grandchild", "c", "【DEV】 Old Root/Old Child/Old Grandchild", "Old Grandchild.md"
            ),
        },
    )
    for pid, entry in manifest.pages.items():
        directory = tmp_path / entry.rel_path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / entry.body_file).write_text(pid, encoding="utf-8")
        (directory / "keep.bin").write_bytes(pid.encode())
    inventory = Inventory(
        pages={
            "r": PageInventoryEntry("r", 1, "New Root", None, "DEV"),
            "c": PageInventoryEntry("c", 1, "New Child", "r", "DEV"),
            "g": PageInventoryEntry("g", 1, "New Grandchild", "c", "DEV"),
        }
    )
    plan = compute_diff(manifest, inventory)
    plan.page_actions.sort(key=lambda a: manifest.pages[a.page_id].rel_path.count("/"), reverse=reverse_order)

    execute_sync(_sync_client(), MagicMock(convert=lambda *a, **kw: "本文"), str(tmp_path), manifest, inventory, plan)

    saved = load_manifest(str(tmp_path))
    assert saved is not None
    expected = {
        "r": "【DEV】 New Root",
        "c": "【DEV】 New Root/New Child",
        "g": "【DEV】 New Root/New Child/New Grandchild",
    }
    for pid, relative in expected.items():
        assert saved.pages[pid].rel_path == relative
        assert (tmp_path / relative / "keep.bin").read_bytes() == pid.encode()
        assert (tmp_path / relative / saved.pages[pid].body_file).is_file()
    assert not list(tmp_path.rglob("*Old*"))


def test_sync_rejects_existing_move_destination_without_nesting(tmp_path):
    """移動先が既にあるとき、既存ディレクトリへ移動元を入れ子にしない."""
    old_dir = tmp_path / "【DEV】 Old"
    new_dir = tmp_path / "【DEV】 New"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "Old.md").write_text("old", encoding="utf-8")
    (new_dir / "keep.txt").write_text("existing", encoding="utf-8")
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(1, "Old", None, old_dir.name, "Old.md"),
        },
    )
    inventory = Inventory(pages={"r": PageInventoryEntry("r", 1, "New", None, "DEV")})
    client = _sync_client()

    with pytest.raises(FileExistsError, match="移動先"):
        execute_sync(client, MagicMock(), str(tmp_path), manifest, inventory, compute_diff(manifest, inventory))

    assert (old_dir / "Old.md").read_text(encoding="utf-8") == "old"
    assert list(new_dir.iterdir()) == [new_dir / "keep.txt"]
    assert manifest.pages["r"].rel_path == old_dir.name
    client.get_page.assert_not_called()


@pytest.mark.parametrize("body_missing", [False, True])
def test_unchanged_descendant_uses_new_parent_path(tmp_path, body_missing):
    """親の改名後、未変更の子孫は新しいパスで再利用または本文復旧する."""
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(1, "Old", None, "【DEV】 Old", "Old.md"),
            "c": PageManifestEntry(1, "Child", "r", "【DEV】 Old/Child", "Child.md"),
            "g": PageManifestEntry(1, "Grandchild", "c", "【DEV】 Old/Child/Grandchild", "Grandchild.md"),
        },
    )
    for pid, entry in manifest.pages.items():
        directory = tmp_path / entry.rel_path
        directory.mkdir(parents=True, exist_ok=True)
        if pid != "g" or not body_missing:
            (directory / entry.body_file).write_text(pid, encoding="utf-8")
    inventory = Inventory(
        pages={
            "r": PageInventoryEntry("r", 1, "New", None, "DEV"),
            "c": PageInventoryEntry("c", 1, "Child", "r", "DEV"),
            "g": PageInventoryEntry("g", 1, "Grandchild", "c", "DEV"),
        }
    )
    client = _sync_client()

    execute_sync(
        client,
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        manifest,
        inventory,
        compute_diff(manifest, inventory),
    )

    saved = load_manifest(str(tmp_path))
    assert saved is not None
    assert saved.pages["c"].rel_path == "【DEV】 New/Child"
    assert saved.pages["g"].rel_path == "【DEV】 New/Child/Grandchild"
    assert (tmp_path / saved.pages["g"].rel_path / "Grandchild.md").is_file()
    assert not (tmp_path / "【DEV】 Old").exists()
    fetched_ids = {call.args[0] for call in client.get_page.call_args_list}
    assert fetched_ids == ({"r", "g"} if body_missing else {"r"})


@pytest.mark.parametrize("deletion_policy", ["quarantine", "delete", "report"])
@pytest.mark.parametrize("change", ["deleted", "renamed_same_id", "renamed_new_id"])
def test_attachment_removal_uses_saved_name_and_deletion_policy(tmp_path, deletion_policy, change):
    """移動後のページでも、削除・改名前の添付に設定された削除方針を適用する."""
    old_attachment = tmp_path / "【DEV】 Old" / "assets" / "saved (2).txt"
    old_attachment.parent.mkdir(parents=True)
    old_attachment.write_bytes(b"old")
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(
                1,
                "Old",
                None,
                "【DEV】 Old",
                "Old.md",
                attachments={
                    "att": AttachmentManifestEntry(1, 3, "saved (2).txt"),
                },
            ),
        },
    )
    current_id = "att" if change == "renamed_same_id" else "new"
    current_atts = (
        {}
        if change == "deleted"
        else {
            current_id: AttachmentInventoryEntry(current_id, "new.txt", 2, 3),
        }
    )
    inventory = Inventory(pages={"r": PageInventoryEntry("r", 1, "New", None, "DEV", attachments=current_atts)})
    client = _sync_client()
    client.get_attachments.return_value = [
        {
            "id": a.attachment_id,
            "title": a.filename,
            "version": {"number": a.version},
            "extensions": {"fileSize": a.size},
            "_links": {"download": "/new"},
        }
        for a in current_atts.values()
    ]

    execute_sync(
        client,
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        manifest,
        inventory,
        compute_diff(manifest, inventory),
        attachment_dir_name="assets",
        deletion_policy=deletion_policy,
        quarantine_dir_name="backup",
    )

    moved_old = tmp_path / "【DEV】 New" / "assets" / "saved (2).txt"
    assert moved_old.exists() == (deletion_policy == "report")
    quarantined = list((tmp_path / "backup").glob("*/【DEV】 New/assets/saved (2).txt"))
    assert len(quarantined) == (1 if deletion_policy == "quarantine" else 0)
    if quarantined:
        assert quarantined[0].read_bytes() == b"old"
    if current_atts:
        assert (tmp_path / "【DEV】 New" / "assets" / "new.txt").read_bytes() == b"new"
        assert manifest.pages["r"].attachments[current_id].saved_name == "new.txt"
    else:
        assert manifest.pages["r"].attachments == {}


@pytest.mark.parametrize("body_exists", [True, False])
def test_unchanged_page_refreshes_manifest_path_and_body_name(tmp_path, body_exists):
    """未変更ページの保存先と本文名を更新し、同じパスで再利用・復旧する."""
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(1, "Root", None, "stale/Root", "old.md"),
        },
    )
    inventory = Inventory(pages={"r": PageInventoryEntry("r", 1, "Root", None, "DEV")})
    body = tmp_path / "【DEV】 Root" / "index.md"
    if body_exists:
        body.parent.mkdir()
        body.write_text("existing", encoding="utf-8")
    client = _sync_client()

    execute_sync(
        client,
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        manifest,
        inventory,
        compute_diff(manifest, inventory),
        page_filename_mode="index",
    )

    saved = load_manifest(str(tmp_path))
    assert saved is not None
    assert (saved.pages["r"].rel_path, saved.pages["r"].body_file) == ("【DEV】 Root", "index.md")
    assert body.is_file()
    assert not (tmp_path / "stale").exists()
    assert client.get_page.call_count == (0 if body_exists else 1)


def test_deferred_attachment_deletion_keeps_previous_manifest_entry(tmp_path):
    """探索失敗時に本文を更新しても、削除を保留した添付の実体と記録を保持する."""
    attachment = tmp_path / "【DEV】 Root" / "_attachments" / "keep.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"keep")
    old_entry = AttachmentManifestEntry(1, 4, "keep.txt")
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(1, "Root", None, "【DEV】 Root", "Root.md", attachments={"att": old_entry}),
        },
    )
    inventory = Inventory(discovery_incomplete=True, pages={"r": PageInventoryEntry("r", 2, "Root", None, "DEV")})

    execute_sync(
        _sync_client(),
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        manifest,
        inventory,
        compute_diff(manifest, inventory),
    )

    assert attachment.read_bytes() == b"keep"
    saved = load_manifest(str(tmp_path))
    assert saved is not None
    assert saved.pages["r"].attachments == {"att": old_entry}


def test_attachment_rename_does_not_remove_another_newly_saved_file(tmp_path):
    """改名前の保存名を別の添付が再利用しても、新しく保存した内容を退避しない."""
    attachment_dir = tmp_path / "【DEV】 Root" / "_attachments"
    attachment_dir.mkdir(parents=True)
    (attachment_dir / "a.txt").write_bytes(b"old a")
    (attachment_dir / "b.txt").write_bytes(b"old b")
    manifest = Manifest(
        "https://confluence.example.com",
        ManifestRoots(),
        pages={
            "r": PageManifestEntry(
                1,
                "Root",
                None,
                "【DEV】 Root",
                "Root.md",
                attachments={
                    "a": AttachmentManifestEntry(1, 5, "a.txt"),
                    "b": AttachmentManifestEntry(1, 5, "b.txt"),
                },
            ),
        },
    )
    inventory = Inventory(
        pages={
            "r": PageInventoryEntry(
                "r",
                1,
                "Root",
                None,
                "DEV",
                attachments={
                    "a": AttachmentInventoryEntry("a", "b.txt", 2, 3),
                    "b": AttachmentInventoryEntry("b", "c.txt", 2, 3),
                },
            )
        }
    )
    client = _sync_client()
    client.get_attachments.return_value = [
        {"id": pid, "title": name, "version": {"number": 2}, "extensions": {"fileSize": 3}}
        for pid, name in [("a", "b.txt"), ("b", "c.txt")]
    ]

    execute_sync(
        client,
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        manifest,
        inventory,
        compute_diff(manifest, inventory),
    )

    assert (attachment_dir / "b.txt").read_bytes() == b"new"
    assert (attachment_dir / "c.txt").read_bytes() == b"new"
