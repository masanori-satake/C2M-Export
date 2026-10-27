"""ファイルシステムエクスポート用データモデルモジュール.

エクスポート処理におけるノード情報、添付ファイル参照、スキップ記録、および全体結果のモデルを定義する。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AttachmentRef:
    """添付ファイルの参照および処理状態を表すモデル.

    Attributes:
        original_filename: Confluence 上の元の添付ファイル名
        saved_filename: ローカルに保存されたファイル名（衝突回避などの正規化後）
        saved: ローカルに正常保存されたかどうか
        download_path: Confluence REST API の `_links.download` パス（相対 URL）
        size_bytes: 添付ファイルのバイトサイズ
        skip_reason: 保存されなかった場合のスキップ・失敗理由
    """

    original_filename: str
    saved_filename: str
    saved: bool
    download_path: str = ""
    size_bytes: int = 0
    skip_reason: Optional[str] = None


@dataclass
class PageNode:
    """エクスポート対象ページの階層ノードを表すモデル.

    Attributes:
        page_id: Confluence ページ ID
        title: 元のページタイトル
        level: ツリー内での階層深度 (ルート=1)
        relative_dir_path: 出力先ルートからの相対ディレクトリパス (例: "【SPACE】ルート/子ページ")
        body_file_name: 本文ファイル名 (例: "子ページ.md" または "index.md")
        children: 子ページノードのリスト
        attachments: ページの添付ファイル参照リスト
    """

    page_id: str
    title: str
    level: int
    relative_dir_path: str
    body_file_name: str
    children: List["PageNode"] = field(default_factory=list)
    attachments: List[AttachmentRef] = field(default_factory=list)


@dataclass
class SkipRecord:
    """スキップまたは失敗した処理単位の記録モデル.

    Attributes:
        target_id: 対象識別子 (ページ ID・Space キー・ファイル名)
        target_type: 対象種別 ("page"・"space"・"attachment")
        title_or_name: ページタイトル・Space 名・添付ファイル名
        reason: スキップ・失敗の理由 (例: "単一ファイルサイズ上限超過", "除外拡張子", "DLエラー")
        size_bytes: 関連するバイトサイズ (判明している場合)
        path: 関連する相対パス
    """

    target_id: str
    target_type: str
    title_or_name: str
    reason: str
    size_bytes: int = 0
    path: str = ""


@dataclass
class ExportResult:
    """エクスポート全体の実行結果とサマリ用データモデル.

    Attributes:
        total_pages: 成功したページ数
        total_attachments: 成功した添付ファイル数
        total_bytes: 出力された総バイトサイズ
        skipped_pages: 失敗・スキップしたページおよび Space の探索失敗の記録一覧
        skipped_attachments: 失敗・スキップした添付ファイルの記録一覧
        unresolved_links_count: 相対リンク書き換えで解決できなかった参照の件数
        renamed_nodes: 衝突回避等で名称変更されたノード情報 (page_id -> 元タイトル vs 保存名)
    """

    total_pages: int = 0
    total_attachments: int = 0
    total_bytes: int = 0
    skipped_pages: List[SkipRecord] = field(default_factory=list)
    skipped_attachments: List[SkipRecord] = field(default_factory=list)
    unresolved_links_count: int = 0
    renamed_nodes: Dict[str, str] = field(default_factory=dict)
