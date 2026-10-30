"""分析機能の出力JSONレスポンスモデルおよびエラーオブジェクト定義.

JSON スキーマ概要:
{
  "schema_version": "1.2",
  "status": "ok" | "partial" | "error",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "mode": "summary" | "detail",
  "scope": {
    "root_page_ids": ["..."],
    "space_keys": ["..."],
    "resolved_root_count": int
  },
  "workspace": { ... },  # ワークスペース概要（total_spaces, spaces 等）
  "visibility": { ... }, # アクセス可否・匿名アクセス概要（anonymous_access, unavailable_apis 等）
  "environment": { ... },# Confluence 環境情報（confluence_version 等）
  "summary": { ... },  # 既存 assessment summary と同一構造
  "usecases": { ... }, # UC1〜UC6 の結果ブロック
  "uncertainties": {
    "skipped_page_ids": ["..."],
    "skipped_attachment_refs": ["..."],
    "restriction_failed_page_ids": ["..."],
    "size_meta_missing_count": int,
    "macro_parse_failed_count": int,
    "empty_space_keys": ["..."],
    "restrictions_disabled": bool,
    "history_failed_count": int,
    "label_failed_count": int,
    "comment_failed_count": int,
    "effective_restriction_failed_count": int,
    "extracted_text_failed_count": int,
    "content_watcher_failed_count": int,
    "space_watcher_failed_count": int,
    "space_permission_failed_count": int,
    "cql_failed": bool,
    "unavailable_apis": ["..."],
    "interrupted": bool,
    "interrupted_reason": null | "signal" | "error",
    "collected_page_count": int,
    "resumed_from_checkpoint": bool,
    "checkpoint_reused_count": int,
    "checkpoint_corrupted_line_count": int
  },
  "error": null | { "code": "...", "message": "...", "detail": "..." }
}
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# エラーコード定数定義
CODE_INVALID_PARAM = "INVALID_PARAM"
CODE_AUTH_FAILED = "AUTH_FAILED"
CODE_TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
CODE_API_ERROR = "API_ERROR"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"
CODE_PARTIAL = "PARTIAL"


@dataclass
class ErrorObject:
    """エラー詳細情報を保持するデータクラス."""

    code: str
    message: str  # 日本語 (現象/原因/対処)
    detail: Optional[str] = None


@dataclass
class AnalysisScope:
    """分析対象スコープ情報 (認証トークン等の秘匿情報は含めない)."""

    root_page_ids: List[str] = field(default_factory=list)
    space_keys: List[str] = field(default_factory=list)
    resolved_root_count: int = 0


@dataclass
class Uncertainties:
    """不確実性・スキップ発生項目の不確実性レポート."""

    skipped_page_ids: List[str] = field(default_factory=list)
    skipped_attachment_refs: List[str] = field(default_factory=list)
    restriction_failed_page_ids: List[str] = field(default_factory=list)
    size_meta_missing_count: int = 0
    macro_parse_failed_count: int = 0
    empty_space_keys: List[str] = field(default_factory=list)
    restrictions_disabled: bool = False
    history_failed_count: int = 0
    label_failed_count: int = 0
    comment_failed_count: int = 0
    effective_restriction_failed_count: int = 0
    extracted_text_failed_count: int = 0
    content_watcher_failed_count: int = 0
    space_watcher_failed_count: int = 0
    space_permission_failed_count: int = 0
    cql_failed: bool = False
    unavailable_apis: List[str] = field(default_factory=list)
    interrupted: bool = False
    interrupted_reason: Optional[str] = None
    collected_page_count: int = 0
    resumed_from_checkpoint: bool = False
    checkpoint_reused_count: int = 0
    checkpoint_corrupted_line_count: int = 0


@dataclass
class AnalysisResponse:
    """分析実行結果の最上位レスポンスモデル."""

    schema_version: str = "1.2"
    status: str = "ok"  # "ok" | "partial" | "error"
    generated_at: str = ""
    mode: str = "summary"
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    workspace: Optional[Dict[str, Any]] = None
    visibility: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, Any]] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    usecases: Dict[str, Any] = field(default_factory=dict)
    uncertainties: Uncertainties = field(default_factory=Uncertainties)
    error: Optional[ErrorObject] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON シリアライズ用の辞書形式へ変換する (errorがNoneの場合は除外)."""
        res = asdict(self)
        if res.get("error") is None:
            res.pop("error", None)

        # level_distribution のキーが int の場合は str に変換（JSON互換性のため）
        if "summary" in res and isinstance(res["summary"], dict):
            lvl_dist = res["summary"].get("level_distribution")
            if isinstance(lvl_dist, dict):
                res["summary"]["level_distribution"] = {str(k): v for k, v in lvl_dist.items()}

        return res
