"""個別一覧抽出の純粋関数群（UC1/UC2/UC3/UC5）.

本モジュールの関数はAPI非依存であり、ソートや件数制限を行わず、
該当条件にマッチするすべての全件レコード列を返す。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from c2m_export.assessment.analyzers import parse_iso_datetime
from c2m_export.assessment.models import AssessmentResult, RawInventory


def extract_risk_pages(result: AssessmentResult, base_url: str) -> List[Dict[str, Any]]:
    """UC1: 移設リスクが高いページをページ単位で集約して抽出する."""
    pages_map: Dict[str, Dict[str, Any]] = {}
    page_title_map: Dict[str, str] = {p.page_id: p.title for p in result.raw_inventory.pages}

    for item in result.risk_items:
        page_id = item.page_id
        if page_id not in pages_map:
            title = page_title_map.get(page_id, "")
            clean_base = base_url.rstrip("/")
            url = f"{clean_base}/pages/viewpage.action?pageId={page_id}" if clean_base else ""
            pages_map[page_id] = {
                "page_id": page_id,
                "title": title,
                "url": url,
                "risk_types": [],
                "risk_count": 0,
                "reasons": [],
            }

        entry = pages_map[page_id]
        if item.risk_type not in entry["risk_types"]:
            entry["risk_types"].append(item.risk_type)
        entry["reasons"].append(item.reason)

    records = list(pages_map.values())
    for r in records:
        r["risk_count"] = len(r["reasons"])

    return records


def extract_stale_pages(
    inventory: RawInventory, stale_days: int, reference_time: datetime
) -> List[Dict[str, Any]]:
    """UC2: 直近 N 日（または年）以上更新されていないページを抽出する."""
    stale_records: List[Dict[str, Any]] = []

    # reference_time が naive の場合は UTC に揃える
    if reference_time.tzinfo is None:
        ref_time = reference_time.replace(tzinfo=timezone.utc)
    else:
        ref_time = reference_time

    for page in inventory.pages:
        if not page.last_modified:
            continue
        dt = parse_iso_datetime(page.last_modified)
        if dt is None:
            continue

        # tz 正規化: naive な datetime の場合は UTC に変換
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        days_since = (ref_time - dt).days
        if days_since >= stale_days:
            stale_records.append(
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "last_modified": page.last_modified,
                    "days_since_modified": days_since,
                }
            )

    return stale_records


def extract_restricted_pages(inventory: RawInventory, base_url: str) -> List[Dict[str, Any]]:
    """UC3: 個別権限（明示的なコンテンツ制限）が設定されているページを抽出する."""
    restricted_records: List[Dict[str, Any]] = []
    clean_base = base_url.rstrip("/")

    for page in inventory.pages:
        res = page.restriction
        if res and res.has_explicit:
            url = f"{clean_base}/pages/viewpage.action?pageId={page.page_id}" if clean_base else ""
            restricted_records.append(
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "url": url,
                    "read_users": list(res.read_users),
                    "read_groups": list(res.read_groups),
                    "readwrite_users": list(res.update_users),
                    "readwrite_groups": list(res.update_groups),
                }
            )

    return restricted_records


def extract_empty_with_attachments(inventory: RawInventory, min_body_bytes: int) -> List[Dict[str, Any]]:
    """UC5: 添付ファイルが存在し、かつ本文サイズが極小のページを抽出する."""
    records: List[Dict[str, Any]] = []

    for page in inventory.pages:
        if len(page.attachments) > 0 and page.body_bytes < min_body_bytes:
            records.append(
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "attachment_count": len(page.attachments),
                    "body_bytes": page.body_bytes,
                }
            )

    return records
