"""共通 1 層 Analysis API 実装モジュール (run_analysis)."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from c2m_export.analysis.categories import summarize_archives
from c2m_export.analysis.extractors import (
    extract_empty_with_attachments,
    extract_restricted_pages,
    extract_risk_pages,
    extract_stale_pages,
)
from c2m_export.analysis.macros import summarize_macros
from c2m_export.analysis.params import DEFAULT_SORTS, AnalysisParams
from c2m_export.analysis.response import (
    CODE_API_ERROR,
    CODE_AUTH_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_PARAM,
    CODE_TARGET_NOT_FOUND,
    AnalysisResponse,
    AnalysisScope,
    ErrorObject,
    Uncertainties,
)
from c2m_export.assessment.analyzers import analyze_inventory
from c2m_export.assessment.collector import Collector
from c2m_export.assessment.report import generate_json_report
from c2m_export.confluence import ConfluenceClient

logger = logging.getLogger(__name__)


class AuthFailedError(Exception):
    """認証失敗例外 (401/403 HTTPError)."""

    pass


class TargetNotFoundError(Exception):
    """対象非存在例外 (404 HTTPError)."""

    pass


class ApiError(Exception):
    """API/通信エラー例外."""

    pass


def _resolve_roots(
    client: ConfluenceClient, root_page_ids: List[str], space_keys: List[str]
) -> Tuple[List[str], List[str]]:
    """起点 (root_page_ids / space_keys) のページIDを解決する.

    Returns:
        (resolved_root_ids, empty_space_keys)
    """
    resolved_ids: List[str] = list(root_page_ids) if root_page_ids else []
    empty_space_keys: List[str] = []

    if space_keys:
        for skey in space_keys:
            try:
                sp_pages = client.get_space_homepage_id(skey)
                if sp_pages:
                    if isinstance(sp_pages, list):
                        resolved_ids.extend([str(p) for p in sp_pages])
                    else:
                        resolved_ids.append(str(sp_pages))
                else:
                    empty_space_keys.append(skey)
            except requests.exceptions.HTTPError as e:
                status_code = getattr(e.response, "status_code", None)
                if status_code == 404:
                    raise TargetNotFoundError(
                        f"現象: 指定された Space キー '{skey}' が存在しません。"
                        f"原因: API が 404 Not Found を返しました。"
                        f"対処方法: 正しい Space キーを指定してください。"
                    )
                elif status_code in (401, 403):
                    raise AuthFailedError(
                        "現象: Confluence API の認証に失敗しました。"
                        "原因: トークンが無効か権限が不足しています。"
                        "対処方法: 正しいアクセストークンを指定してください。"
                    )
                else:
                    raise ApiError(f"API Error ({status_code}): {e}")
            except requests.exceptions.RequestException as e:
                raise ApiError(f"通信エラーが発生しました: {e}")
            except Exception as e:
                raise ApiError(f"起点 Space キーの解決中にエラーが発生しました: {e}")

    # 起点 page_id の確認 (ルートページIDが指定されている場合)
    if root_page_ids:
        for rid in root_page_ids:
            try:
                # ページ存在チェック
                client.get_page(rid)
            except requests.exceptions.HTTPError as e:
                status_code = getattr(e.response, "status_code", None)
                if status_code == 404:
                    raise TargetNotFoundError(
                        f"現象: ルートページ ID '{rid}' が存在しません。"
                        f"原因: API が 404 Not Found を返しました。"
                        f"対処方法: 正しいルートページ ID を指定してください。"
                    )
                elif status_code in (401, 403):
                    raise AuthFailedError(
                        "現象: Confluence API の認証に失敗しました。"
                        "原因: トークンが無効か権限が不足しています。"
                        "対処方法: 正しいアクセストークンを指定してください。"
                    )
                else:
                    raise ApiError(f"API Error ({status_code}): {e}")
            except requests.exceptions.RequestException as e:
                raise ApiError(f"通信エラーが発生しました: {e}")

    # 重複除去
    seen = set()
    final_root_ids = [x for x in resolved_ids if not (x in seen or seen.add(x))]

    if not final_root_ids and not empty_space_keys:
        raise TargetNotFoundError(
            "現象: 有効な分析対象ページが存在しません。"
            "原因: 指定された起点からページを特定できませんでした。"
            "対処方法: 正しい --root-page-id または --space-key を指定してください。"
        )

    return final_root_ids, empty_space_keys


def _paginate(records: List[Dict[str, Any]], sort_key: Optional[str], limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    """レコード列のソートと先頭 limit 件への切り詰めを行う共通ヘルパー."""
    if sort_key and records:
        reverse = sort_key != "page_id"
        records.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

    total_count = len(records)
    truncated = total_count > limit
    items = records[:limit]
    return items, truncated


def run_analysis(
    params: AnalysisParams,
    config: Any,
    client: Optional[ConfluenceClient] = None,
) -> AnalysisResponse:
    """共通 1 層 Analysis API メイン関数."""
    try:
        # パラメータ検証
        params.validate()

        # 参照時刻共有
        ref_time = datetime.now(timezone.utc)

        # Client 初期化
        if client is None:
            if not config.base_url or not config.token:
                raise ValueError("base_url and token are required in config")
            client = ConfluenceClient(base_url=config.base_url, token=config.token, proxy=config.proxy)

        # 1. 起点解決
        resolved_root_ids, empty_space_keys = _resolve_roots(client, config.root_page_ids, config.space_keys)

        # 2. 収集
        macros_requested = "macros" in params.usecases
        collector = Collector(
            client=client,
            analyze_restrictions=params.analyze_restrictions if params.analyze_restrictions is not None else True,
            collect_macros=macros_requested,
        )
        inventory = collector.collect(resolved_root_ids)

        # 3. アセスメント集計
        assess_res = analyze_inventory(
            inventory=inventory,
            single_file_max_mb=getattr(config, "single_file_max_mb", 100),
            path_length_limit=getattr(config, "path_length_limit", 250),
            blocked_extensions=getattr(config, "blocked_extensions", set()),
            attachment_dir_name=getattr(config, "attachment_dir_name", "_attachments"),
            stale_days=params.stale_days,
            min_body_bytes=params.min_body_bytes,
            reference_time=ref_time,
        )

        # Base URL 取得
        base_url = config.base_url or ""

        # 4. 各ユースケース結果構築
        uc_results: Dict[str, Any] = {}

        # UC1: risk
        if "risk" in params.usecases:
            records = extract_risk_pages(assess_res, base_url)
            total_count = len(records)
            uc_block: Dict[str, Any] = {
                "counts": {
                    "total_risk_pages": total_count,
                    "risk_summary": assess_res.risk_summary_counts,
                }
            }
            if params.mode == "detail":
                sort_key = params.sort or DEFAULT_SORTS["risk"]
                items, truncated = _paginate(records, sort_key, params.limit)
                uc_block["counts"]["total_count"] = total_count
                uc_block["counts"]["truncated"] = truncated
                uc_block["items"] = items
            uc_results["risk"] = uc_block

        # UC2: stale
        if "stale" in params.usecases:
            records = extract_stale_pages(inventory, params.stale_days, ref_time)
            total_count = len(records)
            uc_block = {
                "counts": {
                    "stale_page_count": total_count,
                    "stale_threshold_days": params.stale_days,
                    "freshness_distribution": assess_res.freshness_distribution,
                }
            }
            if params.mode == "detail":
                sort_key = params.sort or DEFAULT_SORTS["stale"]
                items, truncated = _paginate(records, sort_key, params.limit)
                uc_block["counts"]["total_count"] = total_count
                uc_block["counts"]["truncated"] = truncated
                uc_block["items"] = items
            uc_results["stale"] = uc_block

        # UC3: restricted
        if "restricted" in params.usecases:
            if params.analyze_restrictions is False:
                uc_block = {
                    "counts": {
                        "explicit_restriction_count": 0,
                        "unique_users_count": 0,
                        "unique_groups_count": 0,
                    }
                }
                if params.mode == "detail":
                    uc_block["counts"]["total_count"] = 0
                    uc_block["counts"]["truncated"] = False
                    uc_block["items"] = []
            else:
                records = extract_restricted_pages(inventory, base_url)
                total_count = len(records)
                uc_block = {
                    "counts": {
                        "explicit_restriction_count": total_count,
                        "unique_users_count": len(assess_res.unique_restriction_users),
                        "unique_groups_count": len(assess_res.unique_restriction_groups),
                    }
                }
                if params.mode == "detail":
                    sort_key = params.sort or DEFAULT_SORTS["restricted"]
                    items, truncated = _paginate(records, sort_key, params.limit)
                    uc_block["counts"]["total_count"] = total_count
                    uc_block["counts"]["truncated"] = truncated
                    uc_block["items"] = items
            uc_results["restricted"] = uc_block

        # UC4: archives
        if "archives" in params.usecases:
            archive_res = summarize_archives(inventory, params.archive_extensions)
            uc_results["archives"] = archive_res

        # UC5: empty_with_attachments
        if "empty_with_attachments" in params.usecases:
            records = extract_empty_with_attachments(inventory, params.min_body_bytes)
            total_count = len(records)
            uc_block = {
                "counts": {
                    "empty_with_attachments_count": total_count,
                    "min_body_bytes_threshold": params.min_body_bytes,
                }
            }
            if params.mode == "detail":
                sort_key = params.sort or DEFAULT_SORTS["empty_with_attachments"]
                items, truncated = _paginate(records, sort_key, params.limit)
                uc_block["counts"]["total_count"] = total_count
                uc_block["counts"]["truncated"] = truncated
                uc_block["items"] = items
            uc_results["empty_with_attachments"] = uc_block

        # UC6: macros
        if "macros" in params.usecases:
            records = summarize_macros(inventory.pages)
            # ソートは count 降順固定
            records.sort(key=lambda x: x["count"], reverse=True)
            if params.mode == "summary":
                # summary モード時は repair_* 情報を省く
                summary_items = [{"name": r["name"], "count": r["count"]} for r in records]
                uc_results["macros"] = {"total_macro_types": len(records), "macros": summary_items}
            else:
                uc_results["macros"] = {"total_macro_types": len(records), "macros": records}

        # レポートサマリ構造の再利用
        json_report_summary = generate_json_report(assess_res)["summary"]

        # uncertainties 情報の収集
        unc = Uncertainties(
            skipped_page_ids=inventory.skipped_page_ids,
            skipped_attachment_refs=inventory.skipped_attachment_refs,
            restriction_failed_page_ids=inventory.restriction_failed_page_ids,
            size_meta_missing_count=inventory.size_meta_missing_count,
            macro_parse_failed_count=inventory.macro_parse_failed_count,
            empty_space_keys=empty_space_keys,
            restrictions_disabled=(params.analyze_restrictions is False),
        )

        response = AnalysisResponse(
            schema_version="1.0",
            status="ok",
            generated_at=ref_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            mode=params.mode,
            scope=AnalysisScope(
                root_page_ids=config.root_page_ids or [],
                space_keys=config.space_keys or [],
                resolved_root_count=len(resolved_root_ids),
            ),
            summary=json_report_summary,
            usecases=uc_results,
            uncertainties=unc,
            error=None,
        )
        return response

    except ValueError as e:
        return AnalysisResponse(
            status="error",
            error=ErrorObject(code=CODE_INVALID_PARAM, message=str(e)),
        )
    except AuthFailedError as e:
        return AnalysisResponse(
            status="error",
            error=ErrorObject(code=CODE_AUTH_FAILED, message=str(e)),
        )
    except TargetNotFoundError as e:
        return AnalysisResponse(
            status="error",
            error=ErrorObject(code=CODE_TARGET_NOT_FOUND, message=str(e)),
        )
    except ApiError as e:
        return AnalysisResponse(
            status="error",
            error=ErrorObject(code=CODE_API_ERROR, message=str(e)),
        )
    except Exception as e:
        logger.exception("分析処理中に想定外のエラーが発生しました")
        return AnalysisResponse(
            status="error",
            error=ErrorObject(
                code=CODE_INTERNAL_ERROR,
                message=f"現象: 分析処理中に想定外のシステムエラーが発生しました。原因: {e}。対処方法: 管理者にお問い合わせください。",
                detail=str(e),
            ),
        )
