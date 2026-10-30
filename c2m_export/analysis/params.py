from dataclasses import dataclass, field
from typing import List, Optional, Set

# 全 6 種の分析ユースケース名定数
ALL_USECASES = [
    "risk",
    "stale",
    "restricted",
    "archives",
    "empty_with_attachments",
    "macros",
]

# UC番号/ユースケース名とデフォルトの並び替えキーとの対応マップ
DEFAULT_SORTS = {
    "risk": "risk_count",  # 降順
    "stale": "days_since_modified",  # 降順
    "restricted": "page_id",  # 昇順
    "archives": None,  # 集約系（sort無視）
    "empty_with_attachments": "attachment_count",  # 降順
    "macros": None,  # 集約系（sort無視）
}


@dataclass
class AnalysisParams:
    """分析実行パラメータを保持・検証するデータクラス."""

    usecases: List[str] = field(default_factory=lambda: list(ALL_USECASES))
    mode: str = "summary"
    limit: int = 1000
    stale_days: int = 365
    min_body_bytes: int = 200
    archive_extensions: Set[str] = field(
        default_factory=lambda: {"zip", "7z", "rar", "gz", "tar", "bz2", "xz", "tgz", "lzh", "cab"}
    )
    analyze_restrictions: Optional[bool] = None
    sort: Optional[str] = None
    all_spaces: bool = False
    cql: Optional[str] = None
    deep: bool = False
    collect_history: Optional[bool] = None
    collect_labels: Optional[bool] = None
    collect_comments: Optional[bool] = None
    collect_watchers: Optional[bool] = None
    collect_effective_restrictions: Optional[bool] = None
    collect_extracted_text: Optional[bool] = None
    collect_space_permissions: Optional[bool] = None
    checkpoint_enabled: bool = True
    resume: bool = False
    checkpoint_interval: int = 1
    checkpoint_dir: str = ".c2m_analyze_checkpoint"

    def __post_init__(self):
        """インスタンス初期化後の正規化処理."""
        if self.archive_extensions:
            self.archive_extensions = {str(e).lower().lstrip(".") for e in self.archive_extensions}

    def validate(self):
        """境界規則に従い入力パラメータの検証を行う (違反時は ValueError を送出)."""
        if not isinstance(self.usecases, list) or len(self.usecases) == 0:
            raise ValueError(
                "現象: usecases が空または無効です。原因: --usecase が空集合で指定されました。対処方法: 1つ以上の有効なユースケース名を指定してください。"
            )

        for uc in self.usecases:
            if uc not in ALL_USECASES:
                raise ValueError(
                    f"現象: 未知のユースケース '{uc}' が指定されました。原因: 許可されていないユースケース名です。対処方法: 有効なユースケース {ALL_USECASES} のいずれかを指定してください。"
                )

        if self.mode not in ("summary", "detail"):
            raise ValueError(
                f"現象: モード '{self.mode}' は無効です。原因: mode に summary または detail 以外が指定されました。対処方法: --mode に summary または detail を指定してください。"
            )

        if not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError(
                f"現象: limit '{self.limit}' は無効です。原因: 1 以上の整数でない値が指定されました。対処方法: --limit に 1 以上の整数を指定してください。"
            )

        if not isinstance(self.stale_days, int) or self.stale_days < 0:
            raise ValueError(
                f"現象: stale_days '{self.stale_days}' は無効です。原因: 0 以上の整数でない値が指定されました。対処方法: --stale-days または --stale-years に 0 以上の値を指定してください。"
            )

        if not isinstance(self.min_body_bytes, int) or self.min_body_bytes < 0:
            raise ValueError(
                f"現象: min_body_bytes '{self.min_body_bytes}' は無効です。原因: 0 以上の整数でない値が指定されました。対処方法: --min-body-bytes に 0 以上の整数を指定してください。"
            )

        if not isinstance(self.checkpoint_interval, int) or self.checkpoint_interval < 1:
            raise ValueError(
                f"現象: checkpoint_interval '{self.checkpoint_interval}' は無効です。原因: 1 以上の整数でない値が指定されました。対処方法: --checkpoint-interval に 1 以上の整数を指定してください。"
            )
