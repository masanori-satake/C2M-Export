"""マニフェストモジュール (manifest.py) の単体テスト."""

import json
import os

import pytest

from c2m_export.fs_export.manifest import (
    CURRENT_SCHEMA_VERSION,
    AttachmentManifestEntry,
    Manifest,
    ManifestCorruptedError,
    ManifestRoots,
    ManifestScopeMismatchError,
    PageManifestEntry,
    load_manifest,
    save_manifest,
    verify_scope,
)


def test_manifest_serialization(tmp_path):
    """マニフェストの保存および読み込み（相互変換）を検証する."""
    out_dir = str(tmp_path)
    roots = ManifestRoots(root_page_ids=["100", "200"], space_keys=["DEV"])
    page1 = PageManifestEntry(
        version=2,
        title="Page 1",
        parent_id=None,
        rel_path="【DEV】Page 1",
        body_file="Page 1.md",
        state="done",
        attachments={"att1": AttachmentManifestEntry(version=1, size=1024, saved_name="doc.pdf", state="done")},
    )
    manifest = Manifest(
        base_url="https://confluence.example.com",
        roots=roots,
        completed=True,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:05:00Z",
        pages={"100": page1},
    )

    path = save_manifest(manifest, out_dir)
    assert os.path.exists(path)

    loaded = load_manifest(out_dir)
    assert loaded is not None
    assert loaded.base_url == "https://confluence.example.com"
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION
    assert loaded.completed is True
    assert loaded.roots.root_page_ids == ["100", "200"]
    assert loaded.roots.space_keys == ["DEV"]
    assert "100" in loaded.pages
    assert loaded.pages["100"].title == "Page 1"
    assert loaded.pages["100"].attachments["att1"].saved_name == "doc.pdf"


def test_load_manifest_non_existent(tmp_path):
    """存在しないマニフェストの読み込みで None が返ることを検証する."""
    assert load_manifest(str(tmp_path)) is None


def test_manifest_corrupted_json(tmp_path):
    """破損した JSON ファイルの読み込みで ManifestCorruptedError が発生することを検証する."""
    out_dir = str(tmp_path)
    file_path = os.path.join(out_dir, ".c2m_manifest.json")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json")

    with pytest.raises(ManifestCorruptedError):
        load_manifest(out_dir)


def test_manifest_corrupted_schema_version(tmp_path):
    """スキーマバージョンが異なるマニフェストで ManifestCorruptedError が発生することを検証する."""
    out_dir = str(tmp_path)
    file_path = os.path.join(out_dir, ".c2m_manifest.json")
    data = {
        "schema_version": 999,
        "base_url": "https://confluence.example.com",
        "roots": {"root_page_ids": [], "space_keys": []},
        "pages": {},
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ManifestCorruptedError):
        load_manifest(out_dir)


def test_verify_scope_success():
    """スコープ検証で base_url と roots が一致する場合に正常終了することを検証する."""
    roots = ManifestRoots(root_page_ids=["100"], space_keys=["DEV"])
    manifest = Manifest(
        base_url="https://confluence.example.com/",
        roots=roots,
    )

    # 末尾スラッシュの違いがあっても成功すること
    verify_scope(
        manifest,
        current_base_url="https://confluence.example.com",
        current_root_page_ids=["100"],
        current_space_keys=["DEV"],
    )


def test_verify_scope_base_url_mismatch():
    """base_url が不一致の場合に ManifestScopeMismatchError が発生することを検証する."""
    roots = ManifestRoots(root_page_ids=["100"], space_keys=[])
    manifest = Manifest(
        base_url="https://server1.example.com",
        roots=roots,
    )

    with pytest.raises(ManifestScopeMismatchError):
        verify_scope(
            manifest,
            current_base_url="https://server2.example.com",
            current_root_page_ids=["100"],
            current_space_keys=[],
        )


def test_verify_scope_roots_mismatch():
    """roots (root_page_ids または space_keys) が不一致の場合に ManifestScopeMismatchError が発生することを検証する."""
    roots = ManifestRoots(root_page_ids=["100"], space_keys=["DEV"])
    manifest = Manifest(
        base_url="https://confluence.example.com",
        roots=roots,
    )

    # root_page_ids 不一致
    with pytest.raises(ManifestScopeMismatchError):
        verify_scope(
            manifest,
            current_base_url="https://confluence.example.com",
            current_root_page_ids=["100", "200"],
            current_space_keys=["DEV"],
        )

    # space_keys 不一致
    with pytest.raises(ManifestScopeMismatchError):
        verify_scope(
            manifest,
            current_base_url="https://confluence.example.com",
            current_root_page_ids=["100"],
            current_space_keys=["PROD"],
        )
