"""権限エクスポート用のデータモデル群.

Confluenceのコンテンツ制限（Read/Read+Write権限）を保持・管理するためのデータ構造を提供する。
継承された制限は実効権限へ展開せず、個別制限を持たないページは「継承/制限なし」として扱う。
Confluence APIの操作キー `update` を本モデルでは `readwrite` (Read+Write権) として表現する。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PagePermission:
    """単一ページの権限情報を保持するデータ構造.

    Attributes:
        page_id: Confluence ページID
        title: ページタイトル
        space_key: Space Key
        url: Confluence WebページURL
        rel_path: ファイルシステム出力併用時のローカル相対パス（単独実行時は None）
        has_explicit: 個別制限が設定されている場合 True。親継承または制限なしの場合 False
        read_users: Read権（閲覧のみ）が個別に与えられたユーザーの表示文字列リスト (例: "山田太郎 (t.yamada)")
        read_groups: Read権が個別に与えられたグループ名のリスト
        readwrite_users: Read+Write権（編集権限/update操作キー）が個別に与えられたユーザーの表示文字列リスト
        readwrite_groups: Read+Write権が個別に与えられたグループ名のリスト
        fetch_failed: 権限情報の取得に失敗した場合 True
        fail_reason: 取得失敗時の日本語による理由説明
    """

    page_id: str
    title: str
    space_key: str
    url: str
    rel_path: Optional[str] = None
    has_explicit: bool = False
    read_users: List[str] = field(default_factory=list)
    read_groups: List[str] = field(default_factory=list)
    readwrite_users: List[str] = field(default_factory=list)
    readwrite_groups: List[str] = field(default_factory=list)
    fetch_failed: bool = False
    fail_reason: str = ""


@dataclass
class PermissionReport:
    """収集された全ページの権限レポート構造.

    Attributes:
        pages: 収集された PagePermission のリスト
    """

    pages: List[PagePermission] = field(default_factory=list)


@dataclass
class PermissionResult:
    """権限エクスポート処理全体の実行結果サマリデータ構造.

    Attributes:
        report: 収集された PermissionReport
        exported_count: 権限を処理/出力した全ページ数
        explicit_count: 個別制限が設定されていたページ数
        inherited_count: 個別制限がなく継承/制限なしとして処理されたページ数
        failed_page_ids: 権限取得に失敗したページIDのリスト
    """

    report: PermissionReport
    exported_count: int
    explicit_count: int
    inherited_count: int
    failed_page_ids: List[str] = field(default_factory=list)
