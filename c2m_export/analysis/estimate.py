"""分析の事前見積もり (spec 0012).

本実行を行わず、起点解決と子孫ページ数の取得だけで対象規模・想定リクエスト数・
推定所要秒数を返す。推定所要は、見積もり自身の API 呼び出しで実測した
平均レイテンシに収集モデルの想定リクエスト数を掛けて算出する。
本実行は本文取得を含むため推定より重く、値は下限寄りの目安である。
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, cast

from c2m_export.analysis.api import ApiError, AuthFailedError, TargetNotFoundError, _resolve_roots
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.response import (
    CODE_API_ERROR,
    CODE_AUTH_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_PARAM,
    CODE_TARGET_NOT_FOUND,
    AnalysisResponse,
    AnalysisScope,
    ErrorObject,
)
from c2m_export.confluence import ConfluenceClient

logger = logging.getLogger(__name__)

# スキル経由実行の既定上限（spec 0011）。推定がこれを超えるかを判定する。
SKILL_DEFAULT_TIMEOUT_SECONDS = 300
# 「大きい」対象の閾値（spec 0012 の判断事項）。
LARGE_ESTIMATED_SECONDS = 120.0
LARGE_TARGET_PAGES = 500
# 実測レイテンシが得られない場合のフォールバック（秒/リクエスト）。
FALLBACK_AVG_LATENCY_SECONDS = 0.3
# 全体把握・環境情報などの固定リクエスト数の近似。
FIXED_REQUESTS = 5
# 全体把握フェーズの Space 単位コスト（ラベル取得 + ルートページ取得）の近似。
OVERVIEW_REQUESTS_PER_SPACE = 2


class _CountingClient:
    """API 呼び出し件数を数える薄いプロキシ（レイテンシ実測用）.

    属性アクセスを透過し、呼び出し可能な属性については件数を数えてから委譲する。
    """

    def __init__(self, inner: Any):
        self._inner = inner
        self.calls = 0

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if callable(attr):

            def _wrapper(*args: Any, **kwargs: Any) -> Any:
                self.calls += 1
                return attr(*args, **kwargs)

            return _wrapper
        return attr


def _resolve_collect_flags(params: AnalysisParams, config: Any) -> Dict[str, bool]:
    """収集フラグを本実行 (run_analysis) と同じ規則で解決する (params > config > deep)."""
    deep = getattr(params, "deep", False) or getattr(config, "deep", False)

    def _resolve_flag(p_val: Optional[bool], c_val: Optional[bool]) -> bool:
        if p_val is not None:
            return p_val
        if c_val is not None:
            return c_val
        return deep

    return {
        "analyze_restrictions": params.analyze_restrictions if params.analyze_restrictions is not None else True,
        "collect_history": _resolve_flag(
            getattr(params, "collect_history", None), getattr(config, "collect_history", None)
        ),
        "collect_labels": _resolve_flag(
            getattr(params, "collect_labels", None), getattr(config, "collect_labels", None)
        ),
        "collect_comments": _resolve_flag(
            getattr(params, "collect_comments", None), getattr(config, "collect_comments", None)
        ),
        "collect_watchers": _resolve_flag(
            getattr(params, "collect_watchers", None), getattr(config, "collect_watchers", None)
        ),
        "collect_effective_restrictions": _resolve_flag(
            getattr(params, "collect_effective_restrictions", None),
            getattr(config, "collect_effective_restrictions", None),
        ),
        "collect_extracted_text": _resolve_flag(
            getattr(params, "collect_extracted_text", None), getattr(config, "collect_extracted_text", None)
        ),
        "collect_space_permissions": _resolve_flag(
            getattr(params, "collect_space_permissions", None), getattr(config, "collect_space_permissions", None)
        ),
    }


def estimate_analysis(
    params: AnalysisParams,
    config: Any,
    client: Optional[ConfluenceClient] = None,
    interrupt_checker: Optional[Callable[[], bool]] = None,
) -> AnalysisResponse:
    """事前見積もりを実行し、estimate フィールド入りのレスポンスを返す.

    Args:
        params: 分析実行パラメータ (本実行と同じものを受け取り、対象と収集フラグの解決に使う)
        config: 分析設定オブジェクト (AnalysisConfig 互換)
        client: ConfluenceClient インスタンス (省略時は config から生成)
        interrupt_checker: 協調的中断判定コールバック (見積もりは短時間のため未使用だが、
            run_analysis との呼び出し互換のために受け取る)

    Returns:
        AnalysisResponse: status="ok" で estimate に見積もり結果を含むレスポンス。
        エラー時は本実行と同じエラーコード体系で status="error" を返す。
    """
    try:
        params.validate()

        p_max_pages = getattr(params, "max_pages", None)
        c_max_pages = getattr(config, "max_pages", None)
        max_pages = p_max_pages if p_max_pages is not None else c_max_pages

        if client is None:
            if not config.base_url or not config.token:
                raise ValueError("base_url and token are required in config")
            client_kwargs = {"base_url": config.base_url, "proxy": config.proxy}
            client_kwargs["token"] = config.token
            if getattr(config, "connect_timeout_seconds", None) is not None:
                client_kwargs["connect_timeout"] = config.connect_timeout_seconds
            if getattr(config, "read_timeout_seconds", None) is not None:
                client_kwargs["read_timeout"] = config.read_timeout_seconds
            client = ConfluenceClient(**client_kwargs)

        counting = _CountingClient(client)
        measure_start = time.monotonic()

        # Space 一覧（全体把握フェーズの規模把握と all_spaces の起点解決に必要）
        all_spaces = getattr(params, "all_spaces", False) or getattr(config, "all_spaces", False)
        shared_spaces: List[Dict[str, Any]] = []
        list_spaces_failed = False
        try:
            shared_spaces = counting.list_spaces()
        except Exception as e:
            # 認証失敗は「一覧取得の失敗」として包まず、本実行経路と
            # 同じ AUTH_FAILED として伝播させる（再試行可否の判断材料のため）
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (401, 403):
                raise AuthFailedError(
                    "現象: Confluence API の認証に失敗しました。"
                    "原因: トークンが無効か権限が不足しています。"
                    "対処方法: 正しいアクセストークンを指定してください。"
                )
            list_spaces_failed = True
            logger.warning(f"Space 一覧の取得に失敗しました: {e}")
        if all_spaces and list_spaces_failed:
            raise ApiError("全 Space 一覧の取得に失敗しました")

        # 起点解決（本実行と同一の関数を再利用。計数プロキシは透過委譲するため
        # ConfluenceClient として扱う）
        cql = getattr(params, "cql", None) or getattr(config, "cql", None)
        resolved_root_ids, empty_space_keys, cql_failed = _resolve_roots(
            cast(ConfluenceClient, counting),
            getattr(config, "root_page_ids", []),
            getattr(config, "space_keys", []),
            all_spaces=all_spaces,
            cql=cql,
            shared_spaces=shared_spaces,
        )

        # 起点ごとの子孫ページ数
        per_root: List[Dict[str, Any]] = []
        count_failed_root_ids: List[str] = []
        target_pages = 0
        for rid in resolved_root_ids:
            descendant_count: Optional[int] = None
            try:
                res = counting.get_descendant_page_count(rid)
                if isinstance(res, dict) and isinstance(res.get("count"), int):
                    descendant_count = res["count"]
            except Exception as e:
                logger.warning(f"ページ {rid} の子孫数取得に失敗しました: {e}")
            if descendant_count is None:
                count_failed_root_ids.append(rid)
                descendant_count = 0
            subtree_total = 1 + descendant_count
            target_pages += subtree_total
            per_root.append(
                {
                    "root_page_id": rid,
                    "descendant_count": descendant_count,
                    "total_pages": subtree_total,
                }
            )

        measured_elapsed = time.monotonic() - measure_start
        measured_calls = counting.calls
        avg_latency = measured_elapsed / measured_calls if measured_calls > 0 else FALLBACK_AVG_LATENCY_SECONDS

        # 収集モデル
        flags = _resolve_collect_flags(params, config)
        requests_per_page = 3  # get_page / get_attachments / get_child_pages
        if flags["analyze_restrictions"]:
            requests_per_page += 1
        for key in (
            "collect_history",
            "collect_labels",
            "collect_comments",
            "collect_watchers",
            "collect_effective_restrictions",
        ):
            if flags[key]:
                requests_per_page += 1

        num_spaces = len(shared_spaces) if isinstance(shared_spaces, list) else 0
        if all_spaces:
            num_target_spaces = num_spaces
        else:
            num_target_spaces = len(getattr(config, "space_keys", []) or [])
        space_detail_per_space = int(flags["collect_space_permissions"]) + int(flags["collect_watchers"])
        fixed_requests = (
            FIXED_REQUESTS + OVERVIEW_REQUESTS_PER_SPACE * num_spaces + space_detail_per_space * num_target_spaces
        )

        effective_pages = min(target_pages, max_pages) if max_pages is not None else target_pages
        estimated_requests = fixed_requests + effective_pages * requests_per_page
        estimated_seconds = round(estimated_requests * avg_latency, 1)

        notes = [
            "推定所要は見積もり自身の軽量な API 呼び出しの実測レイテンシに基づく下限寄りの目安です。本実行は本文取得を含むため、実際はこれより長くなる場合があります。",
            "起点同士の配下が重なる場合、対象ページ数は重なり分を二重に数えます。",
        ]
        if flags["collect_extracted_text"]:
            notes.append(
                "添付本文抽出 (collect_extracted_text) は添付単位のリクエストのため、ページ単位の推定には含めていません。"
            )
        if count_failed_root_ids:
            notes.append(
                "一部の起点で子孫ページ数を取得できず、起点ページのみとして数えています（過小評価の可能性があります）。"
            )
        if cql_failed:
            notes.append("CQL 検索に失敗したため、CQL 由来の起点は対象に含まれていません。")

        estimate = {
            "target_pages": target_pages,
            "effective_pages": effective_pages,
            "max_pages": max_pages,
            "per_root": per_root,
            "count_failed_root_page_ids": count_failed_root_ids,
            "empty_space_keys": empty_space_keys,
            "cql_failed": cql_failed,
            "requests_per_page": requests_per_page,
            "fixed_requests": fixed_requests,
            "estimated_requests": estimated_requests,
            "measured_calls": measured_calls,
            "measured_avg_latency_seconds": round(avg_latency, 4),
            "estimated_seconds": estimated_seconds,
            "exceeds_skill_default_timeout": estimated_seconds > SKILL_DEFAULT_TIMEOUT_SECONDS,
            "skill_default_timeout_seconds": SKILL_DEFAULT_TIMEOUT_SECONDS,
            "is_large": estimated_seconds > LARGE_ESTIMATED_SECONDS or target_pages > LARGE_TARGET_PAGES,
            "large_thresholds": {
                "estimated_seconds": LARGE_ESTIMATED_SECONDS,
                "target_pages": LARGE_TARGET_PAGES,
            },
            "notes": notes,
        }

        ref_time = datetime.now(timezone.utc)
        return AnalysisResponse(
            schema_version="1.2",
            status="ok",
            generated_at=ref_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            mode=params.mode,
            scope=AnalysisScope(
                root_page_ids=getattr(config, "root_page_ids", []) or [],
                space_keys=getattr(config, "space_keys", []) or [],
                resolved_root_count=len(resolved_root_ids),
            ),
            estimate=estimate,
        )

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
        logger.exception("見積もり処理中に想定外のエラーが発生しました")
        return AnalysisResponse(
            schema_version="1.2",
            status="error",
            error=ErrorObject(
                code=CODE_INTERNAL_ERROR,
                message=f"現象: 見積もり処理中に想定外のシステムエラーが発生しました。原因: {e}。対処方法: 管理者にお問い合わせください。",
                detail=str(e),
            ),
        )
