from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Annotation:
    """ノードの付帯情報.

    未取得の項目は None、取得失敗は failed_fields で区別する.
    """

    has_restriction: Optional[bool] = None  # 個別制限の有無（未取得=None）
    read_subjects: List[str] = field(
        default_factory=list
    )  # Read 権のユーザー/グループ（例: "user:alice", "group:dev"）
    readwrite_subjects: List[str] = field(default_factory=list)  # Read+Write 権のユーザー/グループ
    macros: Optional[Dict[str, int]] = None  # マクロ名 -> 回数（未取得=None）
    attachment_count: Optional[int] = None  # 添付件数（未取得=None）
    last_modified: Optional[str] = None  # ISO 8601 または日付文字列 (YYYY-MM-DD)（未取得/不明=None）
    failed_fields: List[str] = field(default_factory=list)  # 取得失敗した項目名リスト


@dataclass
class TreeNode:
    """ツリー上の 1 ノード."""

    page_id: str
    title: str
    children: List["TreeNode"] = field(default_factory=list)
    annotation: Annotation = field(default_factory=Annotation)


@dataclass
class TreeResult:
    """ページツリー処理全体の統合結果データモデル."""

    schema_version: str = "1.0"
    status: str = "ok"  # "ok" | "error"
    roots: List[TreeNode] = field(default_factory=list)
    total_pages: int = 0
    included_annotations: List[str] = field(default_factory=list)
    uncertainties: Dict[str, int] = field(default_factory=dict)
    scope: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None  # status="error" 時のエラー情報
