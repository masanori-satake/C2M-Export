"""アセスメント機能のデータモデル定義."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AttachmentMeta:
    """添付ファイルのメタデータモデル.

    Attributes:
        page_id: 添付先のページID
        filename: ファイル名
        extension: 小文字化されたドット無しの拡張子（無い場合は空文字）
        media_type: MIMEタイプ（取得不能なら空文字）
        file_size: バイト単位のファイルサイズ（メタデータ欠落時は None）
        version: バージョン番号
    """

    page_id: str
    filename: str
    extension: str
    media_type: str
    file_size: Optional[int]
    version: Optional[int] = None


@dataclass
class RestrictionMeta:
    """ページのアクセス制限（コンテンツ制限）メタデータモデル.

    Attributes:
        has_explicit: 個別制限が設定されているか（False = 継承/制限なし）
        read_users: 閲覧権限を持つユーザー一覧（username）
        read_groups: 閲覧権限を持つグループ一覧（groupname）
        update_users: 編集権限を持つユーザー一覧（username）
        update_groups: 編集権限を持つグループ一覧（groupname）
        fetch_failed: 制限情報の取得に失敗したか
    """

    has_explicit: bool
    read_users: List[str] = field(default_factory=list)
    read_groups: List[str] = field(default_factory=list)
    update_users: List[str] = field(default_factory=list)
    update_groups: List[str] = field(default_factory=list)
    fetch_failed: bool = False


@dataclass
class PageMeta:
    """ページのメタデータモデル.

    Attributes:
        page_id: ページID
        title: ページタイトル
        space_key: Spaceキー
        level: 階層レベル（起点ルート = 1）
        body_bytes: Storage Format（XHTML）のUTF-8バイト長（本文概算用）
        last_modified: 最終更新日時（ISO8601形式文字列）
        ancestors_titles: 親からルートへ至るタイトルリスト（ルート→自身の手前）
        attachments: 添付メタデータのリスト
        restriction: コンテンツ制限メタデータ
    """

    page_id: str
    title: str
    space_key: str
    level: int
    body_bytes: int
    last_modified: Optional[str]
    ancestors_titles: List[str]
    attachments: List[AttachmentMeta] = field(default_factory=list)
    restriction: Optional[RestrictionMeta] = None
    macro_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class RawInventory:
    """Collectorによって収集された生のメタデータインベントリ.

    Attributes:
        pages: 収集された全ページのメタデータリスト
        skipped_page_ids: 取得失敗等によりスキップされたページIDリスト
        skipped_attachment_refs: 取得失敗した添付参照リスト（"page_id:filename" 等）
        restriction_failed_page_ids: 制限情報取得に失敗したページIDリスト
        size_meta_missing_count: fileSize メタデータが欠落していた添付件数
    """

    pages: List[PageMeta] = field(default_factory=list)
    skipped_page_ids: List[str] = field(default_factory=list)
    skipped_attachment_refs: List[str] = field(default_factory=list)
    restriction_failed_page_ids: List[str] = field(default_factory=list)
    size_meta_missing_count: int = 0
    macro_parse_failed_count: int = 0


@dataclass
class RiskItem:
    """検出された個別リスク項目.

    Attributes:
        page_id: 対象ページID
        item_name: 対象の名前（ページタイトルまたは添付ファイル名）
        target_path: 想定相対パス
        risk_type: リスク種別（PATH_LENGTH, INVALID_CHAR, RESERVED_NAME, BLOCKED_EXT, LARGE_FILE, DUPLICATE_NAME）
        reason: リスクの詳細理由（日本語説明）
    """

    page_id: str
    item_name: str
    target_path: str
    risk_type: str
    reason: str


@dataclass
class AssessmentResult:
    """Analyzerによって集計・算出された最終アセスメント結果.

    Attributes:
        total_pages: 総ページ数
        total_attachments: 総添付ファイル数
        estimated_body_bytes: 本文の推定総バイト数（Storage Format生サイズ合計）
        total_attachment_bytes: 添付ファイルのメタサイズ合計バイト数
        max_depth: 階層の最大深さ
        level_distribution: 階層レベル別のページ数分布（level: count）
        space_summary: Space別の集計（space_key: {pages, attachments, attachment_bytes}）
        extension_summary: 拡張子別集計リスト（降順）
        mime_summary: MIMEタイプ別集計リスト
        stale_page_count: 長期未更新ページ数
        empty_page_count: 本文空/極小ページ数
        freshness_distribution: 最終更新日時の期間別分布
        explicit_restriction_count: 個別アクセス制限が設定されているページ数
        unique_restriction_users: 権限に登場するユニークユーザー一覧
        unique_restriction_groups: 権限に登場するユニークグループ一覧
        read_only_restriction_count: Read権限のみ設定されているページ数
        read_write_restriction_count: Read+Write権限が設定されているページ数
        risk_items: 検出された個別リスク項目のリスト
        risk_summary_counts: リスク種別ごとの件数サマリ
        raw_inventory: 収集時のインベントリデータ
    """

    total_pages: int
    total_attachments: int
    estimated_body_bytes: int
    total_attachment_bytes: int
    max_depth: int
    level_distribution: Dict[int, int]
    space_summary: Dict[str, Dict[str, int]]
    extension_summary: List[Dict[str, object]]
    mime_summary: List[Dict[str, object]]
    stale_page_count: int
    empty_page_count: int
    freshness_distribution: Dict[str, int]
    explicit_restriction_count: int
    unique_restriction_users: List[str]
    unique_restriction_groups: List[str]
    read_only_restriction_count: int
    read_write_restriction_count: int
    risk_items: List[RiskItem]
    risk_summary_counts: Dict[str, int]
    raw_inventory: RawInventory
