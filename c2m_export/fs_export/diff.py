"""差分判定純粋関数モジュール.

前回マニフェストと現在インベントリを比較し、追加・変更・削除・移動/改名・未変更の DiffPlan を算出する。
I/O 依存を持たない純粋関数として実装する。
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

from c2m_export.fs_export.manifest import Manifest, PageManifestEntry

if TYPE_CHECKING:
    from c2m_export.fs_export.sync import Inventory, PageInventoryEntry


class ActionType(str, Enum):
    """差分アクションの種別."""

    ADD = "add"
    CHANGE = "change"
    MOVE_RENAME = "move_rename"
    DELETE = "delete"
    UNCHANGED = "unchanged"


@dataclass
class AttachmentDiffAction:
    """添付ファイルの差分アクション."""

    attachment_id: str
    action: ActionType
    filename: str
    version: int
    size: int
    old_saved_name: Optional[str] = None


@dataclass
class PageDiffAction:
    """ページの差分アクション."""

    page_id: str
    action: ActionType
    current_version: int
    current_title: str
    current_parent_id: Optional[str]
    old_entry: Optional[PageManifestEntry] = None
    new_entry: Optional[Any] = None
    attachment_actions: List[AttachmentDiffAction] = field(default_factory=list)


@dataclass
class DiffPlan:
    """全体のエクスポート差分計画."""

    page_actions: List[PageDiffAction] = field(default_factory=list)

    @property
    def add_count(self) -> int:
        return sum(1 for a in self.page_actions if a.action == ActionType.ADD)

    @property
    def change_count(self) -> int:
        return sum(1 for a in self.page_actions if a.action == ActionType.CHANGE)

    @property
    def move_rename_count(self) -> int:
        return sum(1 for a in self.page_actions if a.action == ActionType.MOVE_RENAME)

    @property
    def delete_count(self) -> int:
        return sum(1 for a in self.page_actions if a.action == ActionType.DELETE)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for a in self.page_actions if a.action == ActionType.UNCHANGED)


def compute_diff(
    manifest: Optional[Manifest],
    inventory: "Inventory",
) -> DiffPlan:
    """前回マニフェストと現在インベントリを突き合わせ、DiffPlan を算出する純粋関数.

    Args:
        manifest: 前回実行時のマニフェスト（初回フル取得後または存在しない場合は None または空 pages）
        inventory: 今回収集された Confluence インベントリ

    Returns:
        算出された DiffPlan
    """
    plan = DiffPlan()

    prev_pages: Dict[str, PageManifestEntry] = manifest.pages if manifest else {}
    curr_pages: Dict[str, PageInventoryEntry] = inventory.pages
    failed_ids: Set[str] = inventory.failed_page_ids

    prev_page_ids = set(prev_pages.keys())
    curr_page_ids = set(curr_pages.keys())

    # 1. 現在のみ存在 -> 追加 (ADD)
    added_ids = curr_page_ids - prev_page_ids
    for pid in added_ids:
        curr_p = curr_pages[pid]
        att_actions = []
        for att_id, att in curr_p.attachments.items():
            att_actions.append(
                AttachmentDiffAction(
                    attachment_id=att_id,
                    action=ActionType.ADD,
                    filename=att.filename,
                    version=att.version,
                    size=att.size,
                )
            )
        plan.page_actions.append(
            PageDiffAction(
                page_id=pid,
                action=ActionType.ADD,
                current_version=curr_p.version,
                current_title=curr_p.title,
                current_parent_id=curr_p.parent_id,
                new_entry=curr_p,
                attachment_actions=att_actions,
            )
        )

    # 2. 両方に存在 -> 変更 / 移動・改名 / 未変更 の判定
    common_ids = curr_page_ids & prev_page_ids
    for pid in common_ids:
        prev_p = prev_pages[pid]
        curr_p = curr_pages[pid]

        version_changed = curr_p.version != prev_p.version
        title_changed = curr_p.title != prev_p.title
        parent_changed = curr_p.parent_id != prev_p.parent_id

        # 添付の差分計算
        att_actions = _compute_attachment_diff(prev_p.attachments, curr_p.attachments)
        if inventory.discovery_incomplete:
            att_actions = [a for a in att_actions if a.action != ActionType.DELETE]
        has_att_changes = any(a.action != ActionType.UNCHANGED for a in att_actions)

        # アクション種別の判定
        if title_changed or parent_changed:
            action_type = ActionType.MOVE_RENAME
        elif version_changed or has_att_changes or prev_p.state != "done":
            action_type = ActionType.CHANGE
        else:
            action_type = ActionType.UNCHANGED

        plan.page_actions.append(
            PageDiffAction(
                page_id=pid,
                action=action_type,
                current_version=curr_p.version,
                current_title=curr_p.title,
                current_parent_id=curr_p.parent_id,
                old_entry=prev_p,
                new_entry=curr_p,
                attachment_actions=att_actions,
            )
        )

    # 3. 前回のみ存在 -> 削除 (DELETE)
    # ただし、収集時に通信失敗した page_id は削除と誤認せず除外する (要件 4.6)
    removed_ids = prev_page_ids - curr_page_ids
    if inventory.discovery_incomplete:
        logger.warning("インベントリの探索が不完全なため、削除判定を保留します。通信状態と権限を確認してください。")
        removed_ids = set()
    for pid in sorted(removed_ids):
        if pid in failed_ids:
            logger.warning(f"ページ (ID: {pid}) は取得失敗のため削除判定から保留されました。")
            continue

        prev_p = prev_pages[pid]
        plan.page_actions.append(
            PageDiffAction(
                page_id=pid,
                action=ActionType.DELETE,
                current_version=prev_p.version,
                current_title=prev_p.title,
                current_parent_id=prev_p.parent_id,
                old_entry=prev_p,
            )
        )

    return plan


def _compute_attachment_diff(prev_atts: Dict[str, Any], curr_atts: Dict[str, Any]) -> List[AttachmentDiffAction]:
    """添付ファイルの差分を計算するヘパー関数."""
    actions = []
    prev_keys = set(prev_atts.keys())
    curr_keys = set(curr_atts.keys())

    # 新規添付
    for k in curr_keys - prev_keys:
        curr_a = curr_atts[k]
        actions.append(
            AttachmentDiffAction(
                attachment_id=k,
                action=ActionType.ADD,
                filename=curr_a.filename,
                version=curr_a.version,
                size=curr_a.size,
            )
        )

    # 共通添付
    for k in curr_keys & prev_keys:
        prev_a = prev_atts[k]
        curr_a = curr_atts[k]
        if curr_a.version != prev_a.version or curr_a.size != prev_a.size or prev_a.state != "done":
            act = ActionType.CHANGE
        else:
            act = ActionType.UNCHANGED

        actions.append(
            AttachmentDiffAction(
                attachment_id=k,
                action=act,
                filename=curr_a.filename,
                version=curr_a.version,
                size=curr_a.size,
                old_saved_name=prev_a.saved_name,
            )
        )

    # 削除添付
    for k in prev_keys - curr_keys:
        prev_a = prev_atts[k]
        actions.append(
            AttachmentDiffAction(
                attachment_id=k,
                action=ActionType.DELETE,
                filename=prev_a.saved_name,
                version=prev_a.version,
                size=prev_a.size,
                old_saved_name=prev_a.saved_name,
            )
        )

    return actions
