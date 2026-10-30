"""共通 1 層 Analysis API 実装モジュール (run_analysis)."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

import requests

from c2m_export.analysis.categories import summarize_archives
from c2m_export.analysis.checkpoint import (
    CheckpointStore,
    CollectInterrupted,
    compute_scope_hash,
)
from c2m_export.analysis.extractors import (
    extract_empty_with_attachments,
    extract_restricted_pages,
    extract_risk_pages,
    extract_stale_pages,
)
from c2m_export.analysis.macros import summarize_macros
from c2m_export.analysis.params import DEFAULT_SORTS, AnalysisParams
from c2m_export.analysis.provenance import (
    enrich_empty_with_attachments,
    enrich_restricted,
    enrich_stale,
)
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
from c2m_export.analysis.workspace import (
    build_environment,
    build_visibility,
    summarize_spaces,
)
from c2m_export.assessment.analyzers import analyze_inventory
from c2m_export.assessment.collector import Collector
from c2m_export.assessment.models import PageMeta
from c2m_export.assessment.report import generate_json_report
from c2m_export.confluence import ConfluenceClient

logger = logging.getLogger(__name__)


class AnalysisConfigProtocol(Protocol):
    """run_analysis が参照する config オブジェクトの要求属性仕様 Protocol.

    主に AnalysisConfig (c2m_export.config) から供給されますが、
    汎用的な Config インスタンスや外部設定オブジェクトも受容します。
    """

    # 共通接続・対象設定 (全 Config クラス共通)
    base_url: Optional[str]
    token: Optional[str]
    proxy: Optional[str]
    root_page_ids: List[str]
    space_keys: List[str]

    # 分析・オプション設定 (AnalysisConfig に定義)
    all_spaces: bool
    cql: Optional[str]
    deep: bool
    collect_history: Optional[bool]
    collect_labels: Optional[bool]
    collect_comments: Optional[bool]
    collect_watchers: Optional[bool]
    collect_effective_restrictions: Optional[bool]
    collect_extracted_text: Optional[bool]
    collect_space_permissions: Optional[bool]


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
    client: ConfluenceClient,
    root_page_ids: List[str],
    space_keys: List[str],
    all_spaces: bool = False,
    cql: Optional[str] = None,
    shared_spaces: Optional[List[Dict]] = None,
) -> Tuple[List[str], List[str], bool]:
    """起点 (root_page_ids / space_keys / all_spaces / cql) のページIDを解決する.

    Returns:
        (resolved_root_ids, empty_space_keys, cql_failed)
    """
    resolved_ids: List[str] = list(root_page_ids) if root_page_ids else []
    empty_space_keys: List[str] = []
    cql_failed = False

    target_space_keys = list(space_keys) if space_keys else []
    if all_spaces and shared_spaces:
        for sp in shared_spaces:
            k = sp.get("key")
            if k and k not in target_space_keys:
                target_space_keys.append(k)

    if target_space_keys:
        for skey in target_space_keys:
            try:
                sp_pages = client.get_space_root_pages(skey)
                if sp_pages:
                    for page_obj in sp_pages:
                        pid = str(page_obj.get("id", ""))
                        if pid:
                            resolved_ids.append(pid)
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

    if cql:
        try:
            cql_items = client.search_cql(cql)
            for item in cql_items:
                if item.get("type") == "page":
                    cid = str(item.get("id", ""))
                    if cid:
                        resolved_ids.append(cid)
        except Exception as e:
            logger.warning(f"CQL 検索に失敗しました: {e}")
            cql_failed = True

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
    seen: set = set()
    final_root_ids = []
    for x in resolved_ids:
        if x not in seen:
            seen.add(x)
            final_root_ids.append(x)

    if not final_root_ids and not empty_space_keys:
        raise TargetNotFoundError(
            "現象: 有効な分析対象ページが存在しません。"
            "原因: 指定された起点からページを特定できませんでした。"
            "対処方法: 正しい --root-page-id, --space-key, --all-spaces, または --cql を指定してください。"
        )

    return final_root_ids, empty_space_keys, cql_failed


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
    interrupt_checker: Optional[Callable[[], bool]] = None,
) -> AnalysisResponse:
    """共通 1 層 Analysis API メイン関数.

    Args:
        params: 分析実行パラメータ (AnalysisParams)
        config: 分析設定オブジェクト (AnalysisConfig または互換 Config インスタンス)
            参照される属性一覧と出所:
            - base_url, token, proxy, root_page_ids, space_keys: 全 Config クラス共通
            - all_spaces, cql, deep, collect_*: AnalysisConfig
            - single_file_max_mb, path_length_limit, blocked_extensions, attachment_dir_name:
              AssessConfig / FsExportConfig 等から hasattr で選択的に参照。
              AnalysisConfig に属性がない場合は analyze_inventory 内の既定値に委譲。
        client: ConfluenceClient インスタンス (省略時は config から生成)
        interrupt_checker: 協調的中断判定コールバック

    Returns:
        AnalysisResponse: 分析結果オブジェクト
    """
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

        # 0. 共有 Space 一覧の取得
        shared_spaces = []
        list_spaces_failed = False
        list_spaces_error_msg = ""
        try:
            shared_spaces = client.list_spaces()
        except Exception as e:
            list_spaces_failed = True
            list_spaces_error_msg = str(e)
            logger.warning(f"Space 一覧の取得に失敗しました: {e}")

        # オプション解決 (params / config 互換)
        all_spaces = getattr(params, "all_spaces", False) or getattr(config, "all_spaces", False)

        if all_spaces and list_spaces_failed:
            raise ApiError(f"全 Space 一覧の取得に失敗しました: {list_spaces_error_msg}")
        cql = getattr(params, "cql", None) or getattr(config, "cql", None)
        deep = getattr(params, "deep", False) or getattr(config, "deep", False)

        def _resolve_flag(p_val: Optional[bool], c_val: Optional[bool]) -> bool:
            if p_val is not None:
                return p_val
            if c_val is not None:
                return c_val
            return deep

        collect_history = _resolve_flag(
            getattr(params, "collect_history", None), getattr(config, "collect_history", None)
        )
        collect_labels = _resolve_flag(getattr(params, "collect_labels", None), getattr(config, "collect_labels", None))
        collect_comments = _resolve_flag(
            getattr(params, "collect_comments", None), getattr(config, "collect_comments", None)
        )
        collect_watchers = _resolve_flag(
            getattr(params, "collect_watchers", None), getattr(config, "collect_watchers", None)
        )
        collect_effective_restrictions = _resolve_flag(
            getattr(params, "collect_effective_restrictions", None),
            getattr(config, "collect_effective_restrictions", None),
        )
        collect_extracted_text = _resolve_flag(
            getattr(params, "collect_extracted_text", None), getattr(config, "collect_extracted_text", None)
        )
        collect_space_permissions = _resolve_flag(
            getattr(params, "collect_space_permissions", None), getattr(config, "collect_space_permissions", None)
        )

        # チェックポイント設定の解決
        checkpoint_enabled = getattr(params, "checkpoint_enabled", True)
        if hasattr(config, "checkpoint_enabled") and config.checkpoint_enabled is not None:
            checkpoint_enabled = config.checkpoint_enabled

        resume = getattr(params, "resume", False) or getattr(config, "resume", False)
        checkpoint_interval = getattr(params, "checkpoint_interval", 1)
        checkpoint_dir = getattr(params, "checkpoint_dir", ".c2m_analyze_checkpoint")
        if hasattr(config, "checkpoint_dir") and config.checkpoint_dir:
            checkpoint_dir = config.checkpoint_dir

        # 1. 起点解決
        resolved_root_ids, empty_space_keys, cql_failed = _resolve_roots(
            client,
            getattr(config, "root_page_ids", []),
            getattr(config, "space_keys", []),
            all_spaces=all_spaces,
            cql=cql,
            shared_spaces=shared_spaces,
        )

        # 1.5 スコープハッシュ算出とチェックポイント初期化
        macros_requested = "macros" in params.usecases
        collect_flags = {
            "analyze_restrictions": params.analyze_restrictions if params.analyze_restrictions is not None else True,
            "collect_macros": macros_requested,
            "collect_history": collect_history,
            "collect_labels": collect_labels,
            "collect_comments": collect_comments,
            "collect_watchers": collect_watchers,
            "collect_effective_restrictions": collect_effective_restrictions,
            "collect_extracted_text": collect_extracted_text,
            "collect_space_permissions": collect_space_permissions,
        }

        scope_hash = compute_scope_hash(
            base_url=getattr(config, "base_url", None),
            root_page_ids=getattr(config, "root_page_ids", []),
            space_keys=getattr(config, "space_keys", []),
            all_spaces=all_spaces,
            cql=cql,
            collect_flags=collect_flags,
        )

        checkpoint_store: Optional[CheckpointStore] = None
        resumed_from_checkpoint = False
        checkpoint_reused_count = 0
        checkpoint_corrupted_line_count = 0
        restored_pages: List[PageMeta] = []
        resume_collected_ids: Set[str] = set()

        if checkpoint_enabled:
            checkpoint_path = Path(checkpoint_dir) / f"{scope_hash}.jsonl"
            scope_meta = {
                "root_page_ids": getattr(config, "root_page_ids", []),
                "space_keys": getattr(config, "space_keys", []),
            }
            checkpoint_store = CheckpointStore(
                checkpoint_path,
                scope_hash=scope_hash,
                scope_meta=scope_meta,
                interval=checkpoint_interval,
            )

            if resume:
                if checkpoint_store.scope_matches(scope_hash):
                    restored_pages, resume_collected_ids, corrupted_lines = checkpoint_store.load_collected()
                    resumed_from_checkpoint = True
                    checkpoint_reused_count = len(restored_pages)
                    checkpoint_corrupted_line_count = len(corrupted_lines)
                    logger.info(
                        f"チェックポイントから {checkpoint_reused_count} 件のページメタデータを復元しました ({checkpoint_path})"
                    )
                else:
                    logger.warning(
                        f"既存チェックポイント ({checkpoint_path}) のスコープハッシュが現在の実行スコープと不一致のため、復元をスキップします"
                    )

        # 2. 収集
        collector = Collector(
            client=client,
            analyze_restrictions=params.analyze_restrictions if params.analyze_restrictions is not None else True,
            collect_macros=macros_requested,
            collect_history=collect_history,
            collect_labels=collect_labels,
            collect_comments=collect_comments,
            collect_watchers=collect_watchers,
            collect_effective_restrictions=collect_effective_restrictions,
            collect_extracted_text=collect_extracted_text,
            collect_space_permissions=collect_space_permissions,
            checkpoint_store=checkpoint_store,
            resume_collected_ids=resume_collected_ids,
            interrupt_checker=interrupt_checker,
        )

        # 復元済みページの先行投入
        if restored_pages:
            collector.raw_inventory.pages.extend(restored_pages)

        # 全体把握収集
        collector.collect_workspace_overview(shared_spaces, resolved_root_ids)

        is_interrupted = False
        interrupted_reason: Optional[str] = None

        # DFS 走査
        try:
            inventory = collector.collect(resolved_root_ids)
        except CollectInterrupted:
            logger.info("収集処理が中断されました。部分集計 (partial) に移行します。")
            is_interrupted = True
            interrupted_reason = "signal"
            inventory = collector.raw_inventory
        except Exception as e:
            if len(collector.raw_inventory.pages) > 0:
                logger.error(
                    f"収集フェーズでエラーが発生しました。収集済み {len(collector.raw_inventory.pages)} 件で部分集計 (partial) を構築します: {e}"
                )
                is_interrupted = True
                interrupted_reason = "error"
                inventory = collector.raw_inventory
            else:
                raise

        # per-space 詳細調査 (未中断時のみ実行)
        if not is_interrupted:
            target_skeys = list(getattr(config, "space_keys", []) or [])
            if shared_spaces:
                for sp in shared_spaces:
                    k = sp.get("key")
                    if k and k not in target_skeys:
                        target_skeys.append(k)
            collector.collect_space_details(target_skeys)

        # 3. アセスメント集計
        assessment_options = {
            name: getattr(config, name)
            for name in ("single_file_max_mb", "path_length_limit", "blocked_extensions", "attachment_dir_name")
            if hasattr(config, name)
        }
        assess_res = analyze_inventory(
            inventory=inventory,
            stale_days=params.stale_days,
            min_body_bytes=params.min_body_bytes,
            reference_time=ref_time,
            **assessment_options,
        )

        # Base URL 取得
        base_url = getattr(config, "base_url", "") or ""

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
            records = enrich_stale(records, inventory)
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
                records = enrich_restricted(records, inventory)
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
            records = enrich_empty_with_attachments(records, inventory)
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
            records.sort(key=lambda x: x["count"], reverse=True)
            if params.mode == "summary":
                summary_items = [{"name": r["name"], "count": r["count"]} for r in records]
                uc_results["macros"] = {"total_macro_types": len(records), "macros": summary_items}
            else:
                uc_results["macros"] = {"total_macro_types": len(records), "macros": records}

        # レポートサマリ構造の再利用
        json_report_summary = generate_json_report(assess_res)["summary"]

        # 5. workspace / visibility / environment ブロック構築
        workspace_block = summarize_spaces(inventory.spaces)
        visibility_block = build_visibility(inventory.visibility, inventory)
        environment_block = build_environment(inventory.environment)

        # uncertainties 情報の収集
        unc = Uncertainties(
            skipped_page_ids=inventory.skipped_page_ids,
            skipped_attachment_refs=inventory.skipped_attachment_refs,
            restriction_failed_page_ids=inventory.restriction_failed_page_ids,
            size_meta_missing_count=inventory.size_meta_missing_count,
            macro_parse_failed_count=inventory.macro_parse_failed_count,
            empty_space_keys=empty_space_keys,
            restrictions_disabled=(params.analyze_restrictions is False),
            history_failed_count=len(inventory.history_failed_page_ids),
            label_failed_count=len(inventory.label_failed_page_ids),
            comment_failed_count=len(inventory.comment_failed_page_ids),
            effective_restriction_failed_count=len(inventory.effective_restriction_failed_page_ids),
            extracted_text_failed_count=len(inventory.extracted_text_failed_refs),
            content_watcher_failed_count=len(inventory.content_watcher_failed_refs),
            space_watcher_failed_count=len(inventory.space_watcher_failed_keys),
            space_permission_failed_count=len(inventory.space_permission_failed_keys),
            cql_failed=cql_failed,
            unavailable_apis=visibility_block.get("unavailable_apis", []),
            interrupted=is_interrupted,
            interrupted_reason=interrupted_reason,
            collected_page_count=len(inventory.pages),
            resumed_from_checkpoint=resumed_from_checkpoint,
            checkpoint_reused_count=checkpoint_reused_count,
            checkpoint_corrupted_line_count=checkpoint_corrupted_line_count,
        )

        status_str = "partial" if is_interrupted else "ok"

        # チェックポイントの後始末
        if checkpoint_store:
            checkpoint_store.finalize(success=(status_str == "ok"))

        response = AnalysisResponse(
            schema_version="1.2",
            status=status_str,
            generated_at=ref_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            mode=params.mode,
            scope=AnalysisScope(
                root_page_ids=getattr(config, "root_page_ids", []) or [],
                space_keys=getattr(config, "space_keys", []) or [],
                resolved_root_count=len(resolved_root_ids),
            ),
            workspace=workspace_block,
            visibility=visibility_block,
            environment=environment_block,
            summary=json_report_summary,
            usecases=uc_results,
            uncertainties=unc,
            error=None,
        )
        return response

    except ValueError as e:
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(code=CODE_INVALID_PARAM, message=str(e)),
        )
    except AuthFailedError as e:
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(code=CODE_AUTH_FAILED, message=str(e)),
        )
    except TargetNotFoundError as e:
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(code=CODE_TARGET_NOT_FOUND, message=str(e)),
        )
    except ApiError as e:
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(code=CODE_API_ERROR, message=str(e)),
        )
    except Exception as e:
        logger.exception("分析処理中に想定外のエラーが発生しました")
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(
                code=CODE_INTERNAL_ERROR,
                message=f"現象: 分析処理中に想定外のシステムエラーが発生しました。原因: {e}。対処方法: 管理者にお問い合わせください。",
                detail=str(e),
            ),
        )
