"""ツリー構築のためのメタデータおよび付帯情報収集（collector）モジュール.

指定された起点（space_keys / root_page_ids）から Confluence REST API を用いて階層構造と付帯情報を収集する。
付帯情報は opt-in（include に指定された項目のみ）で取得し、指定がない場合は追加 API 呼び出しを行わない。
個別ページの取得エラーはページ単位で握りつぶし、failed_fields および uncertainties に記録して処理を継続する。
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from c2m_export.confluence import ConfluenceClient
from c2m_export.page_tree.annotations import aggregate_macros, classify_restriction
from c2m_export.page_tree.models import Annotation

logger = logging.getLogger(__name__)


def collect_tree(
    client: ConfluenceClient,
    space_keys: Optional[List[str]] = None,
    root_page_ids: Optional[List[str]] = None,
    include: Optional[Set[str]] = None,
    max_depth: Optional[int] = None,
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]], Dict[str, Annotation], Dict[str, str], Dict[str, int]]:
    """Confluence REST API を呼び出して階層ツリーおよび選択された付帯情報を収集する.

    Args:
        client: ConfluenceClient インスタンス
        space_keys: 起点とする Space キーのリスト
        root_page_ids: 起点とするルートページ ID のリスト
        include: 取得対象の付帯情報集合 {"restriction", "macros", "attachments", "last_modified"}
        max_depth: 探索の最大階層深さ

    Returns:
        Tuple[
            resolved_root_ids: ルートページ ID リスト,
            children_map: page_id -> 子ページ情報リスト,
            annotations_map: page_id -> Annotation,
            page_titles_map: page_id -> ページタイトル,
            uncertainties: 項目別失敗件数などの不確実性統計
        ]
    """
    include_set = include or set()
    resolved_root_ids: List[str] = []
    children_map: Dict[str, List[Dict[str, Any]]] = {}
    annotations_map: Dict[str, Annotation] = {}
    page_titles_map: Dict[str, str] = {}
    visited_ids: Set[str] = set()

    uncertainties: Dict[str, int] = {
        "restriction_failed": 0,
        "macro_failed": 0,
        "attachment_failed": 0,
        "history_failed": 0,
        "child_fetch_failed": 0,
    }

    last_root_exception: Optional[Exception] = None

    # 1. 起点（ルートページ ID）の解決
    if space_keys:
        for sk in space_keys:
            try:
                roots = client.get_space_root_pages(sk)
                for r in roots:
                    r_id = str(r["id"])
                    if r_id not in resolved_root_ids:
                        resolved_root_ids.append(r_id)
                    if "title" in r:
                        page_titles_map[r_id] = str(r["title"])
            except Exception as e:
                last_root_exception = e
                logger.warning(
                    f"現象: Space {sk} のルートページ一覧取得に失敗しました。 原因: {e} 対処方法: Space キーおよびアクセス権限を確認してください。"
                )

    if root_page_ids:
        for r_id in root_page_ids:
            r_id_str = str(r_id)
            try:
                p_data = client.get_page(r_id_str, expand="version")
                if isinstance(p_data, dict):
                    if r_id_str not in resolved_root_ids:
                        resolved_root_ids.append(r_id_str)
                    if "title" in p_data:
                        page_titles_map[r_id_str] = str(p_data["title"])
            except Exception as e:
                last_root_exception = e
                logger.warning(
                    f"現象: ルートページ {r_id_str} の基本情報取得に失敗しました。 原因: {e} 対処方法: ページ ID およびアクセス権限を確認してください。"
                )

    # 起点を1件も解決できなかった場合は例外を再送出する
    if not resolved_root_ids:
        if last_root_exception is not None:
            raise last_root_exception
        raise requests.exceptions.HTTPError(
            "現象: 起点ページまたは Space が見つかりませんでした。原因: 指定された --space-key または --root-page-id に該当するコンテンツが存在しないか権限がありません。対処方法: 指定内容およびアクセス権限を確認してください。",
            response=type("Response", (), {"status_code": 404})(),
        )

    # 2. 階層および付帯情報の再帰収集
    def _traverse_and_collect(page_id: str, current_depth: int):
        if page_id in visited_ids:
            return
        visited_ids.add(page_id)

        ann = Annotation()

        # 付帯情報がある場合のみ追加 API 呼び出しを行う (要件 3.3 / 14.6)
        if include_set:
            # A. 個別制限
            if "restriction" in include_set:
                try:
                    restr_data = client.get_restrictions(page_id)
                    has_r, r_sub, rw_sub = classify_restriction(restr_data)
                    ann.has_restriction = has_r
                    ann.read_subjects = r_sub
                    ann.readwrite_subjects = rw_sub
                except Exception as e:
                    logger.debug(f"ページ {page_id} の権限取得失敗: {e}")
                    ann.failed_fields.append("restriction")
                    uncertainties["restriction_failed"] += 1

            # B. マクロおよび最終更新日（API呼び出しの集約最適化）
            need_macros = "macros" in include_set
            need_modified = "last_modified" in include_set

            if need_macros or need_modified:
                try:
                    if need_macros and need_modified:
                        p_info = client.get_page(page_id, expand="body.storage,version")
                    elif need_macros:
                        p_info = client.get_page(page_id, expand="body.storage")
                    else:
                        p_info = client.get_page(page_id, expand="version")

                    if need_macros:
                        try:
                            storage_xhtml = p_info.get("body", {}).get("storage", {}).get("value", "")
                            ann.macros = aggregate_macros(storage_xhtml)
                        except Exception as e:
                            logger.debug(f"ページ {page_id} のマクロ解析失敗: {e}")
                            ann.failed_fields.append("macros")
                            uncertainties["macro_failed"] += 1

                    if need_modified:
                        v_when = p_info.get("version", {}).get("when")
                        if v_when:
                            ann.last_modified = str(v_when)
                        else:
                            ann.failed_fields.append("last_modified")
                            uncertainties["history_failed"] += 1
                except Exception as e:
                    logger.debug(f"ページ {page_id} の詳細情報取得失敗: {e}")
                    if need_macros:
                        ann.failed_fields.append("macros")
                        uncertainties["macro_failed"] += 1
                    if need_modified:
                        ann.failed_fields.append("last_modified")
                        uncertainties["history_failed"] += 1

            # C. 添付件数
            if "attachments" in include_set:
                try:
                    atts = client.get_attachments(page_id)
                    ann.attachment_count = len(atts)
                except Exception as e:
                    logger.debug(f"ページ {page_id} の添付一覧取得失敗: {e}")
                    ann.failed_fields.append("attachments")
                    uncertainties["attachment_failed"] += 1

        annotations_map[page_id] = ann

        # 深さ制限チェック
        if max_depth is not None and max_depth > 0 and current_depth >= max_depth:
            children_map[page_id] = []
            return

        # 子ページ一覧の取得（階層構築用）
        try:
            children = client.get_child_pages(page_id)
            children_map[page_id] = children
            for c in children:
                c_id = str(c.get("id"))
                if c_id:
                    if "title" in c:
                        page_titles_map[c_id] = str(c["title"])
                    _traverse_and_collect(c_id, current_depth + 1)
        except Exception as e:
            logger.warning(
                f"現象: ページ {page_id} の子ページ一覧取得に失敗しました。 原因: {e} 対処方法: アクセス権限を確認してください。"
            )
            children_map[page_id] = []
            uncertainties["child_fetch_failed"] += 1

    for root_id in resolved_root_ids:
        _traverse_and_collect(root_id, current_depth=1)

    return resolved_root_ids, children_map, annotations_map, page_titles_map, uncertainties
