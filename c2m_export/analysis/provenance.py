"""来歴・分類・制限情報の集約純粋関数."""

from typing import Dict, List

from c2m_export.assessment.models import RawInventory


def enrich_stale(stale_records: List[Dict], inventory: RawInventory) -> List[Dict]:
    """鮮度一覧レコードに更新者・作成者情報を付与する."""
    page_map = {p.page_id: p for p in inventory.pages}
    enriched = []
    for rec in stale_records:
        r = dict(rec)
        pid = r.get("page_id")
        pm = page_map.get(str(pid)) if pid else None
        if pm:
            r["last_updated_by"] = pm.last_updated_by
            r["created_by"] = pm.created_by
            r["owner_unknown"] = pm.owner_unknown
        else:
            r["last_updated_by"] = None
            r["created_by"] = None
            r["owner_unknown"] = False
        enriched.append(r)
    return enriched


def enrich_restricted(restricted_records: List[Dict], inventory: RawInventory) -> List[Dict]:
    """権限一覧レコードに実効閲覧制限情報を併記する."""
    page_map = {p.page_id: p for p in inventory.pages}
    enriched = []
    for rec in restricted_records:
        r = dict(rec)
        pid = r.get("page_id")
        pm = page_map.get(str(pid)) if pid else None
        if pm and pm.effective_view_restrictions:
            eff = pm.effective_view_restrictions
            r["effective_read_users"] = eff.read_users
            r["effective_read_groups"] = eff.read_groups
            r["effective_restriction_present"] = bool(eff.read_users or eff.read_groups)
        else:
            r["effective_read_users"] = []
            r["effective_read_groups"] = []
            r["effective_restriction_present"] = False
        enriched.append(r)
    return enriched


def enrich_empty_with_attachments(empty_records: List[Dict], inventory: RawInventory) -> List[Dict]:
    """本文空ページ一覧レコードに添付抽出テキスト概要とコメント情報を付与する."""
    page_map = {p.page_id: p for p in inventory.pages}
    enriched = []
    for rec in empty_records:
        r = dict(rec)
        pid = r.get("page_id")
        pm = page_map.get(str(pid)) if pid else None
        att_ext_list = []
        if pm:
            for att in pm.attachments:
                att_ext_list.append(
                    {
                        "filename": att.filename,
                        "has_extracted_text": att.has_extracted_text,
                        "extracted_text_length": att.extracted_text_length,
                    }
                )
            r["attachments_extracted_text"] = att_ext_list
            r["comment_count"] = pm.comment_count
            r["unresolved_comment_count"] = pm.unresolved_comment_count
            r["inline_comment_count"] = pm.inline_comment_count
            r["footer_comment_count"] = pm.footer_comment_count
        else:
            r["attachments_extracted_text"] = []
            r["comment_count"] = 0
            r["unresolved_comment_count"] = None
            r["inline_comment_count"] = None
            r["footer_comment_count"] = None
        enriched.append(r)
    return enriched
