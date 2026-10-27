"""現在インベントリの軽量収集および同期・レジューム処理を行うモジュール.

Confluence REST API からメタデータ（軽量インベントリ）を高速収集し、
差分計画 (DiffPlan) に従って実出力の更新、移動・改名、削除退避、およびレジューム実行を行う。
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import yaml

from c2m_export.confluence import ConfluenceClient
from c2m_export.converter import MarkdownConverter
from c2m_export.fs_export.diff import ActionType, AttachmentDiffAction, DiffPlan
from c2m_export.fs_export.frontmatter import generate_frontmatter
from c2m_export.fs_export.links import rewrite_attachment_links
from c2m_export.fs_export.manifest import (
    AttachmentManifestEntry,
    Manifest,
    PageManifestEntry,
    save_manifest,
)
from c2m_export.fs_export.models import AttachmentRef, ExportResult, SkipRecord
from c2m_export.fs_export.quarantine import quarantine_path
from c2m_export.utils import generate_unique_name, mb_to_bytes, sanitize_filename

logger = logging.getLogger(__name__)


@dataclass
class AttachmentInventoryEntry:
    """軽量収集における添付ファイルのメタデータモデル."""

    attachment_id: str
    filename: str
    version: int
    size: int


@dataclass
class PageInventoryEntry:
    """軽量収集におけるページのメタデータモデル."""

    page_id: str
    version: int
    title: str
    parent_id: Optional[str]
    space_key: str
    attachments: Dict[str, AttachmentInventoryEntry] = field(default_factory=dict)


@dataclass
class Inventory:
    """収集された Confluence 側の現在状態（インベントリ）."""

    pages: Dict[str, PageInventoryEntry] = field(default_factory=dict)
    failed_page_ids: Set[str] = field(default_factory=set)
    discovery_incomplete: bool = False


def collect_inventory(
    client: ConfluenceClient,
    root_page_ids: List[str],
    space_keys: List[str],
) -> Inventory:
    """Confluence サーバから本文・バイナリを取得せず、メタデータのみのインベントリを収集する.

    Args:
        client: ConfluenceClient インスタンス
        root_page_ids: 探索起点とする root_page_id のリスト
        space_keys: 探索起点とする space_key のリスト

    Returns:
        収集結果を保持する Inventory オブジェクト
    """
    inventory = Inventory()
    visited_ids: Set[str] = set()

    # 起点ページ ID の収集
    start_page_ids: List[str] = list(root_page_ids) if root_page_ids else []

    if space_keys:
        for space_key in space_keys:
            try:
                roots = client.get_space_root_pages(space_key)
                for r in roots:
                    r_id = str(r.get("id"))
                    if r_id and r_id not in start_page_ids:
                        start_page_ids.append(r_id)
            except Exception as e:
                inventory.discovery_incomplete = True
                logger.error(
                    f"現象: Space ({space_key}) のルートページ一覧取得に失敗しました。 原因: {e} 対処方法: Space キーおよびアクセス権限を確認してください。"
                )

    # DFS でページツリーの軽量メタデータを収集
    # スタック要素: (page_id, parent_id)
    stack: List[Tuple[str, Optional[str]]] = [(pid, None) for pid in reversed(start_page_ids)]

    while stack:
        current_id, parent_id = stack.pop()
        if current_id in visited_ids:
            continue
        visited_ids.add(current_id)

        try:
            # 最小限の expand でページ情報を取得 (version, ancestors, space)
            page_data = client.get_page(current_id, expand="version,ancestors,space")
            version_num = int(page_data.get("version", {}).get("number", 1))
            title = str(page_data.get("title", ""))
            space_key = str(page_data.get("space", {}).get("key", ""))

            ancestors = page_data.get("ancestors", [])
            actual_parent_id = parent_id
            if ancestors and isinstance(ancestors, list) and len(ancestors) > 0:
                actual_parent_id = str(ancestors[-1].get("id"))

            # 添付メタデータの取得
            attachments_map: Dict[str, AttachmentInventoryEntry] = {}
            try:
                atts_data = client.get_attachments(current_id)
                for att in atts_data:
                    att_id = str(att.get("id", ""))
                    filename = str(att.get("title", ""))
                    att_version = int(att.get("version", {}).get("number", 1))
                    extensions = att.get("extensions", {})
                    size = int(extensions.get("fileSize", 0))

                    key = att_id if att_id else filename
                    attachments_map[key] = AttachmentInventoryEntry(
                        attachment_id=att_id,
                        filename=filename,
                        version=att_version,
                        size=size,
                    )
            except Exception as ae:
                inventory.discovery_incomplete = True
                logger.warning(f"ページ (ID: {current_id}) の添付ファイル一覧取得に失敗しました: {ae}")

            inventory.pages[current_id] = PageInventoryEntry(
                page_id=current_id,
                version=version_num,
                title=title,
                parent_id=actual_parent_id,
                space_key=space_key,
                attachments=attachments_map,
            )

            # 子ページの取得
            try:
                children = client.get_child_pages(current_id)
                for child in reversed(children):
                    child_id = str(child.get("id"))
                    if child_id and child_id not in visited_ids:
                        stack.append((child_id, current_id))
            except Exception as ce:
                inventory.discovery_incomplete = True
                logger.warning(f"ページ (ID: {current_id}) の子ページ一覧取得に失敗しました: {ce}")

        except Exception as e:
            logger.error(
                f"現象: ページ (ID: {current_id}) のメタデータ取得に失敗しました。 原因: {e} 対処方法: ネットワーク状況およびアクセス権限を確認してください。"
            )
            inventory.failed_page_ids.add(current_id)
            inventory.discovery_incomplete = True

    return inventory


def compute_paths_for_inventory(inventory: Inventory, page_filename_mode: str = "title") -> Dict[str, Tuple[str, str]]:
    """インベントリの全ページに対してローカルの (rel_path, body_file_name) を計算する.

    Returns:
        Dict[page_id, Tuple[relative_dir_path, body_file_name]]
    """
    paths_map: Dict[str, Tuple[str, str]] = {}
    pages = inventory.pages

    # 親子関係の構築
    children_map: Dict[Optional[str], List[str]] = {}
    for pid, p_entry in pages.items():
        parent_id = p_entry.parent_id
        if parent_id not in pages:
            parent_id = None
        children_map.setdefault(parent_id, []).append(pid)

    # 仮想ルートを含む各親の処理時に、兄弟の名前を一度だけ確定する。
    stack: List[Tuple[Optional[str], str]] = [(None, "")]
    while stack:
        parent_id, parent_rel_dir = stack.pop()
        existing_names: List[str] = []
        for pid in children_map.get(parent_id, []):
            if pid in paths_map:
                continue
            entry = pages[pid]
            title_name = sanitize_filename(entry.title or "untitled") or "untitled"
            base_name = f"【{entry.space_key or 'UNKNOWN'}】 {title_name}" if parent_id is None else title_name
            unique_name = generate_unique_name(base_name, existing_names)
            existing_names.append(unique_name)
            dir_path = f"{parent_rel_dir}/{unique_name}" if parent_rel_dir else unique_name
            if page_filename_mode == "index":
                body_file = "index.md"
            else:
                body_file = f"{title_name if parent_id is None else unique_name}.md"
            paths_map[pid] = (dir_path, body_file)
            stack.append((pid, dir_path))

    return paths_map


def execute_sync(
    client: ConfluenceClient,
    converter: MarkdownConverter,
    output_dir: str,
    manifest: Manifest,
    inventory: Inventory,
    plan: DiffPlan,
    attachment_dir_name: str = "_attachments",
    attachment_link_mode: str = "relative",
    single_file_max_mb: float = 250.0,
    exclude_extensions: Optional[List[str]] = None,
    frontmatter_fields: Optional[List[str]] = None,
    base_url: str = "",
    deletion_policy: str = "quarantine",
    quarantine_dir_name: str = "_c2m_quarantine",
    manifest_name: str = ".c2m_manifest.json",
    page_filename_mode: str = "title",
    resume: bool = False,
) -> ExportResult:
    """算出された DiffPlan を適用し、実出力とマニフェストを更新する.

    Returns:
        ExportResult サマリ情報
    """
    result = ExportResult()
    max_bytes = mb_to_bytes(single_file_max_mb)
    exclude_ext_set: Set[str] = set()
    if exclude_extensions:
        exclude_ext_set = {ext.strip().lstrip(".").lower() for ext in exclude_extensions if ext.strip()}

    computed_paths = compute_paths_for_inventory(inventory, page_filename_mode=page_filename_mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 削除アクション (DELETE) の処理
    for page_act in plan.page_actions:
        if page_act.action == ActionType.DELETE and page_act.old_entry:
            old_rel = page_act.old_entry.rel_path
            quarantine_path(
                rel_path=old_rel,
                output_dir=output_dir,
                deletion_policy=deletion_policy,
                quarantine_dir_name=quarantine_dir_name,
                timestamp=timestamp,
            )
            manifest.pages.pop(page_act.page_id, None)
            save_manifest(manifest, output_dir, manifest_name)

    # 2. 保存先の親と現在の占有者の移動を待ち、循環時のみ一時退避する。
    move_actions = sorted(
        (a for a in plan.page_actions if a.action == ActionType.MOVE_RENAME and a.old_entry),
        key=lambda a: computed_paths.get(a.page_id, (a.old_entry.rel_path if a.old_entry else "", ""))[0].count("/"),
    )
    staged_page_ids: Set[str] = set()
    while move_actions:
        progressed = False
        for page_act in move_actions[:]:
            assert page_act.old_entry is not None
            old_rel = page_act.old_entry.rel_path
            new_rel, new_body_file = computed_paths.get(page_act.page_id, (old_rel, page_act.old_entry.body_file))

            if old_rel != new_rel:
                old_abs = os.path.join(output_dir, old_rel)
                new_abs = os.path.join(output_dir, new_rel)
                # 子を先に置くと親の移動先を作ってしまうため、新しい親の確定を待つ。
                if any(
                    other.page_id != page_act.page_id and new_rel.startswith(computed_paths[other.page_id][0] + "/")
                    for other in move_actions
                ):
                    continue
                # 移動先やその祖先・子孫を占有するページが移動するまで保留する。
                if any(
                    other.page_id != page_act.page_id
                    and other.old_entry
                    and other.old_entry.rel_path != computed_paths[other.page_id][0]
                    and os.path.lexists(os.path.join(output_dir, other.old_entry.rel_path))
                    and (
                        new_rel == other.old_entry.rel_path
                        or new_rel.startswith(other.old_entry.rel_path + "/")
                        or other.old_entry.rel_path.startswith(new_rel + "/")
                    )
                    for other in move_actions
                ):
                    continue
                if new_rel.startswith(old_rel + "/") and os.path.lexists(old_abs):
                    continue

                if os.path.lexists(new_abs):
                    if not (
                        resume
                        and not os.path.lexists(old_abs)
                        and _is_resumed_move_destination(
                            new_abs,
                            {page_act.old_entry.body_file, new_body_file},
                            page_act.page_id,
                            manifest.base_url,
                        )
                    ):
                        raise FileExistsError(
                            f"現象: 移動先 ({new_rel}) が既に存在します。 原因: ローカルパスの競合。 対処方法: 既存の移動先を確認し、別の場所へ退避してから再実行してください。"
                        )
                    # 記録直前の中断でも、一緒に移動した子孫の配置を復元する。
                    _update_moved_paths(manifest, old_rel, new_rel)
                elif os.path.lexists(old_abs):
                    _move_sync_directory(output_dir, old_rel, new_rel, manifest, manifest_name)

            # 古いファイル名と新しいファイル名が異なる場合の調整
            if page_act.old_entry.body_file != new_body_file:
                old_body_abs = os.path.join(output_dir, new_rel, page_act.old_entry.body_file)
                new_body_abs = os.path.join(output_dir, new_rel, new_body_file)
                if os.path.exists(old_body_abs) and old_body_abs != new_body_abs:
                    try:
                        os.replace(old_body_abs, new_body_abs)
                    except OSError:
                        pass

            # マニフェスト情報を仮更新
            page_act.old_entry.rel_path = new_rel
            page_act.old_entry.body_file = new_body_file
            page_act.old_entry.title = page_act.current_title
            page_act.old_entry.parent_id = page_act.current_parent_id
            page_act.old_entry.state = "pending"
            save_manifest(manifest, output_dir, manifest_name)
            move_actions.remove(page_act)
            progressed = True

        if not progressed:
            # 退避済みのページを再退避せず、循環を構成する別の占有者を空ける。
            page_act = next(
                a
                for a in move_actions
                if a.page_id not in staged_page_ids
                and a.old_entry
                and os.path.lexists(os.path.join(output_dir, a.old_entry.rel_path))
            )
            assert page_act.old_entry is not None
            temporary_dir = tempfile.mkdtemp(prefix=".c2m_move_", dir=output_dir)
            temporary_rel = os.path.join(os.path.relpath(temporary_dir, output_dir), "page")
            _move_sync_directory(output_dir, page_act.old_entry.rel_path, temporary_rel, manifest, manifest_name)
            staged_page_ids.add(page_act.page_id)

    # 3. 追加・変更・未変更（レジューム整合含む）の処理
    for page_act in plan.page_actions:
        pid = page_act.page_id
        if page_act.action in (ActionType.ADD, ActionType.CHANGE, ActionType.MOVE_RENAME):
            new_rel, new_body_file = computed_paths.get(pid, ("", f"{pid}.md"))
            _process_single_page_sync(
                client=client,
                converter=converter,
                output_dir=output_dir,
                page_id=pid,
                rel_path=new_rel,
                body_file_name=new_body_file,
                title=page_act.current_title,
                parent_id=page_act.current_parent_id,
                manifest=manifest,
                manifest_name=manifest_name,
                result=result,
                attachment_dir_name=attachment_dir_name,
                attachment_link_mode=attachment_link_mode,
                max_bytes=max_bytes,
                single_file_max_mb=single_file_max_mb,
                exclude_ext_set=exclude_ext_set,
                frontmatter_fields=frontmatter_fields,
                base_url=base_url,
                attachment_actions=page_act.attachment_actions,
                deletion_policy=deletion_policy,
                quarantine_dir_name=quarantine_dir_name,
                timestamp=timestamp,
            )
        elif page_act.action == ActionType.UNCHANGED and page_act.old_entry:
            # 要件 6.1: マニフェストに完了と記録されているがローカルに実ファイルが存在しない場合は未処理として再取得
            current_rel, current_body = computed_paths.get(
                pid, (page_act.old_entry.rel_path, page_act.old_entry.body_file)
            )
            if (page_act.old_entry.rel_path, page_act.old_entry.body_file) != (current_rel, current_body):
                page_act.old_entry.rel_path = current_rel
                page_act.old_entry.body_file = current_body
                save_manifest(manifest, output_dir, manifest_name)
            body_path = os.path.join(output_dir, current_rel, current_body)

            if not os.path.exists(body_path) or page_act.old_entry.state != "done":
                logger.info(f"実ファイル欠落または未完了のため再取得します: {page_act.old_entry.title} ({pid})")
                _process_single_page_sync(
                    client=client,
                    converter=converter,
                    output_dir=output_dir,
                    page_id=pid,
                    rel_path=current_rel,
                    body_file_name=current_body,
                    title=page_act.current_title,
                    parent_id=page_act.current_parent_id,
                    manifest=manifest,
                    manifest_name=manifest_name,
                    result=result,
                    attachment_dir_name=attachment_dir_name,
                    attachment_link_mode=attachment_link_mode,
                    max_bytes=max_bytes,
                    single_file_max_mb=single_file_max_mb,
                    exclude_ext_set=exclude_ext_set,
                    frontmatter_fields=frontmatter_fields,
                    base_url=base_url,
                    attachment_actions=page_act.attachment_actions,
                    deletion_policy=deletion_policy,
                    quarantine_dir_name=quarantine_dir_name,
                    timestamp=timestamp,
                )
            else:
                # 正常スキップ（再利用）
                result.total_pages += 1

    manifest.completed = True
    manifest.finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    save_manifest(manifest, output_dir, manifest_name)

    return result


def _update_moved_paths(manifest: Manifest, old_rel: str, new_rel: str) -> None:
    """実体とともに移動したページと子孫の記録を追従させる."""
    for entry in manifest.pages.values():
        if entry.rel_path == old_rel or entry.rel_path.startswith(old_rel + "/"):
            entry.rel_path = new_rel + entry.rel_path[len(old_rel) :]


def _move_sync_directory(output_dir: str, old_rel: str, new_rel: str, manifest: Manifest, manifest_name: str) -> None:
    """一時退避も通常移動と同じく記録し、中断後の再開に備える."""
    old_abs = os.path.join(output_dir, old_rel)
    new_abs = os.path.join(output_dir, new_rel)
    os.makedirs(os.path.dirname(new_abs), exist_ok=True)
    try:
        shutil.move(old_abs, new_abs)
    except Exception as e:
        logger.error(
            f"現象: ローカルパスの移動 ({old_rel} -> {new_rel}) に失敗しました。 原因: {e} 対処方法: ファイルのアクセス権限を確認してください。"
        )
        raise
    logger.info(f"[移動/改名] ローカル配置を変更しました: {old_rel} -> {new_rel}")
    _update_moved_paths(manifest, old_rel, new_rel)
    save_manifest(manifest, output_dir, manifest_name)
    if os.path.basename(old_abs) == "page" and os.path.basename(os.path.dirname(old_abs)).startswith(".c2m_move_"):
        os.rmdir(os.path.dirname(old_abs))


def _is_resumed_move_destination(directory: str, body_files: Set[str], page_id: str, base_url: str) -> bool:
    """移動済み本文のフロントマターで、再開先が同じサーバの同じページか確認する."""
    found = False
    for body_file in body_files:
        body_path = os.path.join(directory, body_file)
        if not os.path.lexists(body_path):
            continue
        try:
            with open(body_path, encoding="utf-8") as body:
                if body.readline().strip() != "---":
                    return False
                lines = []
                for line in body:
                    if line.strip() == "---":
                        break
                    lines.append(line)
                else:
                    return False
            metadata = yaml.safe_load("".join(lines))
        except (OSError, UnicodeError, yaml.YAMLError):
            return False
        if not isinstance(metadata, dict):
            return False
        if metadata.get("confluence_url") != f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}":
            return False
        if str(metadata.get("confluence_page_id", page_id)) != page_id:
            return False
        found = True
    return found


def _process_single_page_sync(
    client: ConfluenceClient,
    converter: MarkdownConverter,
    output_dir: str,
    page_id: str,
    rel_path: str,
    body_file_name: str,
    title: str,
    parent_id: Optional[str],
    manifest: Manifest,
    manifest_name: str,
    result: ExportResult,
    attachment_dir_name: str,
    attachment_link_mode: str,
    max_bytes: int,
    single_file_max_mb: float,
    exclude_ext_set: Set[str],
    frontmatter_fields: Optional[List[str]],
    base_url: str,
    attachment_actions: Optional[List[AttachmentDiffAction]] = None,
    deletion_policy: str = "quarantine",
    quarantine_dir_name: str = "_c2m_quarantine",
    timestamp: str = "",
) -> None:
    """単一ページの取得・変換・書き込みおよびマニフェスト原子的更新を行う."""
    previous_entry = manifest.pages.get(page_id)
    previous_attachments = dict(previous_entry.attachments) if previous_entry else {}
    manifest.pages[page_id] = PageManifestEntry(
        version=0,
        title=title,
        parent_id=parent_id,
        rel_path=rel_path,
        body_file=body_file_name,
        state="pending",
        attachments=previous_attachments,
    )
    save_manifest(manifest, output_dir, manifest_name)

    # 1. Confluence ページ詳細の取得
    try:
        page_detail = client.get_page(
            page_id,
            expand="body.storage,space,version,ancestors,history.lastUpdated",
        )
    except Exception as e:
        logger.warning(
            f"現象: ページ {page_id} ({title}) の詳細取得に失敗しました。 原因: {e} 対処方法: 通信状態と権限を確認してください。"
        )
        manifest.pages[page_id].state = "failed"
        save_manifest(manifest, output_dir, manifest_name)
        result.skipped_pages.append(
            SkipRecord(
                target_id=page_id,
                target_type="page",
                title_or_name=title,
                reason=f"詳細取得エラー ({e})",
                path=rel_path,
            )
        )
        return

    version_num = int(page_detail.get("version", {}).get("number", 1))
    manifest.pages[page_id].version = version_num

    # 2. 添付ファイル処理
    att_manifest_map = dict(previous_attachments)
    for att_action in attachment_actions or []:
        if att_action.action == ActionType.DELETE and att_action.old_saved_name:
            quarantine_path(
                rel_path=os.path.join(rel_path, attachment_dir_name, att_action.old_saved_name),
                output_dir=output_dir,
                deletion_policy=deletion_policy,
                quarantine_dir_name=quarantine_dir_name,
                timestamp=timestamp,
            )
            att_manifest_map.pop(att_action.attachment_id, None)
    old_names = {a.attachment_id: a.old_saved_name for a in attachment_actions or [] if a.action != ActionType.DELETE}
    att_refs: List[AttachmentRef] = []
    try:
        raw_atts = client.get_attachments(page_id)
        saved_names: List[str] = []
        assigned_names: Dict[str, str] = {}

        # 旧名が他の添付の新名になる場合に備え、退避をすべての保存より先に行う。
        for att in raw_atts:
            orig_title = str(att.get("title", "unnamed"))
            ext = os.path.splitext(orig_title)[1].lstrip(".").lower()
            if ext in exclude_ext_set or int(att.get("extensions", {}).get("fileSize", 0)) > max_bytes:
                continue
            key = str(att.get("id", "")) or orig_title
            unique_att_name = generate_unique_name(sanitize_filename(orig_title) or "unnamed", saved_names)
            saved_names.append(unique_att_name)
            assigned_names[key] = unique_att_name
            old_name = old_names.get(key)
            if old_name and old_name != unique_att_name:
                quarantine_path(
                    rel_path=os.path.join(rel_path, attachment_dir_name, old_name),
                    output_dir=output_dir,
                    deletion_policy=deletion_policy,
                    quarantine_dir_name=quarantine_dir_name,
                    timestamp=timestamp,
                )

        for att in raw_atts:
            att_id = str(att.get("id", ""))
            orig_title = str(att.get("title", "unnamed"))
            file_size = int(att.get("extensions", {}).get("fileSize", 0))
            att_ver = int(att.get("version", {}).get("number", 1))
            dl_path = str(att.get("_links", {}).get("download", ""))
            key = att_id if att_id else orig_title

            ext = os.path.splitext(orig_title)[1].lstrip(".").lower()
            if ext in exclude_ext_set:
                att_manifest_map[key] = AttachmentManifestEntry(
                    version=att_ver, size=file_size, saved_name=orig_title, state="skipped"
                )
                continue

            if file_size > max_bytes:
                att_manifest_map[key] = AttachmentManifestEntry(
                    version=att_ver, size=file_size, saved_name=orig_title, state="skipped"
                )
                continue

            unique_att_name = assigned_names[key]

            dest_att_path = os.path.join(output_dir, rel_path, attachment_dir_name, unique_att_name)

            try:
                written_b = client.download_attachment(
                    download_path=dl_path, dest_file=dest_att_path, max_bytes=max_bytes
                )
                result.total_attachments += 1
                result.total_bytes += written_b
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=unique_att_name,
                        saved=True,
                        download_path=dl_path,
                        size_bytes=written_b,
                    )
                )
                att_manifest_map[key] = AttachmentManifestEntry(
                    version=att_ver, size=written_b, saved_name=unique_att_name, state="done"
                )
            except Exception as de:
                logger.warning(f"添付ファイル {orig_title} のダウンロードに失敗しました: {de}")
                att_manifest_map[key] = AttachmentManifestEntry(
                    version=att_ver, size=file_size, saved_name=unique_att_name, state="failed"
                )

    except Exception as ae:
        logger.warning(f"ページ {page_id} の添付一覧取得に失敗しました: {ae}")

    # 3. 本文書き込み
    try:
        storage_html = page_detail.get("body", {}).get("storage", {}).get("value", "")
        raw_markdown = converter.convert(storage_html, level=1)

        final_markdown, unresolved_cnt = rewrite_attachment_links(
            content=raw_markdown,
            attachments=att_refs,
            attachment_dir_name=attachment_dir_name,
            link_mode=attachment_link_mode,
            base_url=base_url,
        )
        result.unresolved_links_count += unresolved_cnt

        last_modified = page_detail.get("history", {}).get("lastUpdated", {}).get("when")
        space_key = page_detail.get("space", {}).get("key", "")

        frontmatter_str = generate_frontmatter(
            page_id=page_id,
            space_key=space_key,
            base_url=base_url,
            title=title,
            version=version_num,
            last_modified=last_modified,
            fields=frontmatter_fields,
        )

        full_content = frontmatter_str + final_markdown

        page_dir = os.path.join(output_dir, rel_path)
        os.makedirs(page_dir, exist_ok=True)
        body_filepath = os.path.join(page_dir, body_file_name)
        tmp_filepath = body_filepath + ".tmp"

        encoded_bytes = full_content.encode("utf-8")
        with open(tmp_filepath, "wb") as f:
            f.write(encoded_bytes)
        os.replace(tmp_filepath, body_filepath)

        result.total_pages += 1
        result.total_bytes += len(encoded_bytes)

        manifest.pages[page_id].state = "done"
        manifest.pages[page_id].attachments = att_manifest_map
        save_manifest(manifest, output_dir, manifest_name)

    except Exception as pe:
        logger.error(f"ページ {page_id} の書き込みに失敗しました: {pe}")
        manifest.pages[page_id].state = "failed"
        save_manifest(manifest, output_dir, manifest_name)
