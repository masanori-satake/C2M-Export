"""アセスメントインベントリの分析・集計・リスク集約を行う純粋ロジック."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from c2m_export.assessment.models import (
    AssessmentResult,
    PageMeta,
    RawInventory,
    RiskItem,
)
from c2m_export.assessment.rules import (
    DEFAULT_ATTACHMENT_DIR_NAME,
    DEFAULT_BLOCKED_EXTENSIONS,
    DEFAULT_PATH_LENGTH_LIMIT,
    DEFAULT_SINGLE_FILE_MAX_MB,
    calculate_attachment_relative_path,
    calculate_page_relative_path,
    check_blocked_extension,
    check_invalid_chars_or_name,
    check_large_file,
    check_path_length,
)
from c2m_export.utils import sanitize_filename

logger = logging.getLogger(__name__)


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """ISO8601形式の文字列を datetime オブジェクトに変換する."""
    if not dt_str:
        return None
    try:
        # 末尾 Z を UTC オフセットに変換
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None


def analyze_inventory(
    inventory: RawInventory,
    single_file_max_mb: int = DEFAULT_SINGLE_FILE_MAX_MB,
    path_length_limit: int = DEFAULT_PATH_LENGTH_LIMIT,
    blocked_extensions: Optional[Set[str]] = None,
    attachment_dir_name: str = DEFAULT_ATTACHMENT_DIR_NAME,
    stale_days: int = 365,
    min_body_bytes: int = 200,
    reference_time: Optional[datetime] = None,
) -> AssessmentResult:
    """RawInventory を分析し AssessmentResult を生成する純粋関数."""
    if blocked_extensions is None:
        blocked_extensions = DEFAULT_BLOCKED_EXTENSIONS

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    total_pages = len(inventory.pages)
    total_attachments = 0
    estimated_body_bytes = 0
    total_attachment_bytes = 0
    max_depth = 0

    level_distribution: Dict[int, int] = defaultdict(int)
    space_summary: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"pages": 0, "attachments": 0, "attachment_bytes": 0}
    )

    ext_counter: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_size": 0, "max_size": 0}
    )
    mime_counter: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_size": 0, "max_size": 0}
    )

    stale_page_count = 0
    empty_page_count = 0
    date_parse_fail_count = 0
    freshness_distribution: Dict[str, int] = {
        "within_30_days": 0,
        "within_90_days": 0,
        "within_180_days": 0,
        "within_365_days": 0,
        "over_365_days": 0,
        "unknown": 0,
    }

    explicit_restriction_count = 0
    unique_read_users: Set[str] = set()
    unique_read_groups: Set[str] = set()
    unique_update_users: Set[str] = set()
    unique_update_groups: Set[str] = set()
    read_only_restriction_count = 0
    read_write_restriction_count = 0

    risk_items: List[RiskItem] = []
    risk_summary_counts: Dict[str, int] = defaultdict(int)

    # ページごとの同名子ページ衝突検出用: (parent_id/space, level, normalized_title) -> List[PageMeta]
    child_page_names: Dict[Tuple[str, int, str], List[PageMeta]] = defaultdict(list)

    for page in inventory.pages:
        # 深さとレベル分布
        max_depth = max(max_depth, page.level)
        level_distribution[page.level] += 1

        # 本文サイズ概算とSpace集計
        estimated_body_bytes += page.body_bytes
        space_summary[page.space_key]["pages"] += 1

        # 鮮度分析
        if page.body_bytes < min_body_bytes:
            empty_page_count += 1

        dt = parse_iso_datetime(page.last_modified)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_ago = (reference_time - dt).days
            if days_ago >= stale_days:
                stale_page_count += 1

            if days_ago <= 30:
                freshness_distribution["within_30_days"] += 1
            elif days_ago <= 90:
                freshness_distribution["within_90_days"] += 1
            elif days_ago <= 180:
                freshness_distribution["within_180_days"] += 1
            elif days_ago <= 365:
                freshness_distribution["within_365_days"] += 1
            else:
                freshness_distribution["over_365_days"] += 1
        else:
            if page.last_modified:
                date_parse_fail_count += 1
            freshness_distribution["unknown"] += 1

        # 権限分析
        if page.restriction:
            if page.restriction.has_explicit:
                explicit_restriction_count += 1
                unique_read_users.update(page.restriction.read_users)
                unique_read_groups.update(page.restriction.read_groups)
                unique_update_users.update(page.restriction.update_users)
                unique_update_groups.update(page.restriction.update_groups)

                has_read = bool(page.restriction.read_users or page.restriction.read_groups)
                has_update = bool(page.restriction.update_users or page.restriction.update_groups)

                if has_read and not has_update:
                    read_only_restriction_count += 1
                elif has_update:
                    read_write_restriction_count += 1

        # リスク分析: ページパス長・名前チェック
        page_path = calculate_page_relative_path(page.ancestors_titles, page.title)
        path_err = check_path_length(page_path, path_length_limit)
        if path_err:
            risk_items.append(
                RiskItem(
                    page_id=page.page_id,
                    item_name=page.title,
                    target_path=page_path,
                    risk_type="PATH_LENGTH",
                    reason=path_err,
                )
            )
            risk_summary_counts["PATH_LENGTH"] += 1

        name_err = check_invalid_chars_or_name(page.title)
        if name_err:
            risk_items.append(
                RiskItem(
                    page_id=page.page_id,
                    item_name=page.title,
                    target_path=page_path,
                    risk_type="INVALID_CHAR",
                    reason=name_err,
                )
            )
            risk_summary_counts["INVALID_CHAR"] += 1

        # 同名衝突用データの集計（親キーとして ancestors_titles の文字列表現とレベルを使用）
        parent_key = "/".join(page.ancestors_titles)
        norm_title = sanitize_filename(page.title).lower()
        child_page_names[(parent_key, page.level, norm_title)].append(page)

        # 添付ファイル分析
        attachment_names_in_page: Dict[str, List[str]] = defaultdict(list)
        for att in page.attachments:
            total_attachments += 1
            space_summary[page.space_key]["attachments"] += 1

            size = att.file_size or 0
            if att.file_size is not None:
                total_attachment_bytes += size
                space_summary[page.space_key]["attachment_bytes"] += size

            # 拡張子・MIME集計
            ext_key = att.extension if att.extension else "(no_extension)"
            ext_counter[ext_key]["count"] += 1
            ext_counter[ext_key]["total_size"] += size
            ext_counter[ext_key]["max_size"] = max(ext_counter[ext_key]["max_size"], size)

            mime_key = att.media_type if att.media_type else "(unknown_mime)"
            mime_counter[mime_key]["count"] += 1
            mime_counter[mime_key]["total_size"] += size
            mime_counter[mime_key]["max_size"] = max(mime_counter[mime_key]["max_size"], size)

            # 添付ファイルのリスク判定
            att_path = calculate_attachment_relative_path(
                page.ancestors_titles, page.title, att.filename, attachment_dir_name
            )

            att_path_err = check_path_length(att_path, path_length_limit)
            if att_path_err:
                risk_items.append(
                    RiskItem(
                        page_id=page.page_id,
                        item_name=att.filename,
                        target_path=att_path,
                        risk_type="PATH_LENGTH",
                        reason=att_path_err,
                    )
                )
                risk_summary_counts["PATH_LENGTH"] += 1

            att_name_err = check_invalid_chars_or_name(att.filename)
            if att_name_err:
                risk_items.append(
                    RiskItem(
                        page_id=page.page_id,
                        item_name=att.filename,
                        target_path=att_path,
                        risk_type="INVALID_CHAR",
                        reason=att_name_err,
                    )
                )
                risk_summary_counts["INVALID_CHAR"] += 1

            blocked_err = check_blocked_extension(att.extension, blocked_extensions)
            if blocked_err:
                risk_items.append(
                    RiskItem(
                        page_id=page.page_id,
                        item_name=att.filename,
                        target_path=att_path,
                        risk_type="BLOCKED_EXT",
                        reason=blocked_err,
                    )
                )
                risk_summary_counts["BLOCKED_EXT"] += 1

            large_err = check_large_file(att.file_size, single_file_max_mb)
            if large_err:
                risk_items.append(
                    RiskItem(
                        page_id=page.page_id,
                        item_name=att.filename,
                        target_path=att_path,
                        risk_type="LARGE_FILE",
                        reason=large_err,
                    )
                )
                risk_summary_counts["LARGE_FILE"] += 1

            norm_att_name = sanitize_filename(att.filename).lower()
            attachment_names_in_page[norm_att_name].append(att.filename)

        # ページ内同名添付の衝突チェック
        for norm_att, raw_names in attachment_names_in_page.items():
            if len(raw_names) > 1:
                reason = f"同一ページ内に正規化後同名となる添付ファイルが複数存在します: {', '.join(raw_names)}"
                risk_items.append(
                    RiskItem(
                        page_id=page.page_id,
                        item_name=norm_att,
                        target_path=calculate_page_relative_path(page.ancestors_titles, page.title),
                        risk_type="DUPLICATE_NAME",
                        reason=reason,
                    )
                )
                risk_summary_counts["DUPLICATE_NAME"] += 1

    # ページ間の階層内同名衝突チェック
    for (_parent, _level, _norm_title), pages_list in child_page_names.items():
        if len(pages_list) > 1:
            raw_titles = [p.title for p in pages_list]
            reason = f"同一階層に正規化後同名となるページが複数存在します: {', '.join(raw_titles)}"
            for p in pages_list:
                risk_items.append(
                    RiskItem(
                        page_id=p.page_id,
                        item_name=p.title,
                        target_path=calculate_page_relative_path(p.ancestors_titles, p.title),
                        risk_type="DUPLICATE_NAME",
                        reason=reason,
                    )
                )
                risk_summary_counts["DUPLICATE_NAME"] += 1

    # 拡張子別集計を降順ソート
    extension_summary = [
        {"extension": ext, "count": data["count"], "total_size": data["total_size"], "max_size": data["max_size"]}
        for ext, data in sorted(ext_counter.items(), key=lambda x: x[1]["total_size"], reverse=True)
    ]

    mime_summary = [
        {"media_type": mime, "count": data["count"], "total_size": data["total_size"], "max_size": data["max_size"]}
        for mime, data in sorted(mime_counter.items(), key=lambda x: x[1]["total_size"], reverse=True)
    ]

    unique_all_users = sorted(list(unique_read_users | unique_update_users))
    unique_all_groups = sorted(list(unique_read_groups | unique_update_groups))

    return AssessmentResult(
        total_pages=total_pages,
        total_attachments=total_attachments,
        estimated_body_bytes=estimated_body_bytes,
        total_attachment_bytes=total_attachment_bytes,
        max_depth=max_depth,
        level_distribution=dict(level_distribution),
        space_summary=dict(space_summary),
        extension_summary=extension_summary,
        mime_summary=mime_summary,
        stale_page_count=stale_page_count,
        empty_page_count=empty_page_count,
        freshness_distribution=freshness_distribution,
        explicit_restriction_count=explicit_restriction_count,
        unique_restriction_users=unique_all_users,
        unique_restriction_groups=unique_all_groups,
        read_only_restriction_count=read_only_restriction_count,
        read_write_restriction_count=read_write_restriction_count,
        risk_items=risk_items,
        risk_summary_counts=dict(risk_summary_counts),
        raw_inventory=inventory,
    )
