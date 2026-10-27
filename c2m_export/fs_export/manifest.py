"""マニフェスト管理モジュール.

エクスポートの状態および進捗を永続化・読み込み・検証するためのデータモデルと関数を提供する。
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_NAME = ".c2m_manifest.json"


class ManifestError(Exception):
    """マニフェスト操作の基本例外."""

    pass


class ManifestCorruptedError(ManifestError):
    """マニフェストファイル破損・欠落例外."""

    pass


class ManifestScopeMismatchError(ManifestError):
    """マニフェストのスコープ（対象サーバ・ルート）不一致例外."""

    pass


@dataclass
class AttachmentManifestEntry:
    """マニフェスト内の添付ファイル情報エントリーモデル."""

    version: int
    size: int
    saved_name: str
    state: str = "done"  # "done" | "pending" | "failed" | "skipped"

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換する."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttachmentManifestEntry":
        """辞書形式から生成する."""
        return cls(
            version=int(d.get("version", 0)),
            size=int(d.get("size", 0)),
            saved_name=str(d.get("saved_name", "")),
            state=str(d.get("state", "done")),
        )


@dataclass
class PageManifestEntry:
    """マニフェスト内のページ情報エントリーモデル."""

    version: int
    title: str
    parent_id: Optional[str]
    rel_path: str
    body_file: str
    state: str = "done"  # "done" | "pending" | "failed"
    attachments: Dict[str, AttachmentManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換する."""
        return {
            "version": self.version,
            "title": self.title,
            "parent_id": self.parent_id,
            "rel_path": self.rel_path,
            "body_file": self.body_file,
            "state": self.state,
            "attachments": {k: v.to_dict() for k, v in self.attachments.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PageManifestEntry":
        """辞書形式から生成する."""
        atts = {}
        raw_atts = d.get("attachments", {})
        if isinstance(raw_atts, dict):
            for k, v in raw_atts.items():
                if isinstance(v, dict):
                    atts[k] = AttachmentManifestEntry.from_dict(v)
        return cls(
            version=int(d.get("version", 0)),
            title=str(d.get("title", "")),
            parent_id=d.get("parent_id"),
            rel_path=str(d.get("rel_path", "")),
            body_file=str(d.get("body_file", "")),
            state=str(d.get("state", "done")),
            attachments=atts,
        )


@dataclass
class ManifestRoots:
    """マニフェスト対象のルート指定モデル."""

    root_page_ids: List[str] = field(default_factory=list)
    space_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換する."""
        return {
            "root_page_ids": sorted(list(self.root_page_ids)),
            "space_keys": sorted(list(self.space_keys)),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ManifestRoots":
        """辞書形式から生成する."""
        r_ids = [str(x) for x in d.get("root_page_ids", [])] if isinstance(d.get("root_page_ids"), list) else []
        s_keys = [str(x) for x in d.get("space_keys", [])] if isinstance(d.get("space_keys"), list) else []
        return cls(root_page_ids=r_ids, space_keys=s_keys)


@dataclass
class Manifest:
    """マニフェスト全体のルートモデル."""

    base_url: str
    roots: ManifestRoots
    schema_version: int = CURRENT_SCHEMA_VERSION
    completed: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    pages: Dict[str, PageManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換する."""
        return {
            "schema_version": self.schema_version,
            "base_url": self.base_url,
            "roots": self.roots.to_dict(),
            "completed": self.completed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pages": {k: v.to_dict() for k, v in self.pages.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Manifest":
        """辞書形式から生成する."""
        schema_v = d.get("schema_version")
        if schema_v != CURRENT_SCHEMA_VERSION:
            raise ManifestCorruptedError(
                f"現象: マニフェストのスキーマバージョンが不正です。 原因: 期待値={CURRENT_SCHEMA_VERSION}, 実際={schema_v}。 対処方法: --full オプションを指定してフル取得を実行してください。"
            )

        base_url = d.get("base_url")
        if not base_url or not isinstance(base_url, str):
            raise ManifestCorruptedError(
                "現象: マニフェストの base_url 情報が不正または不足しています。 原因: 必須フィールド base_url が存在しません。 対処方法: --full オプションを指定してフル取得を実行してください。"
            )

        roots_data = d.get("roots")
        if not isinstance(roots_data, dict):
            raise ManifestCorruptedError(
                "現象: マニフェストの roots 情報が不正または不足しています。 原因: 必須フィールド roots が存在しません。 対処方法: --full オプションを指定してフル取得を実行してください。"
            )
        roots = ManifestRoots.from_dict(roots_data)

        raw_pages = d.get("pages", {})
        if not isinstance(raw_pages, dict):
            raise ManifestCorruptedError(
                "現象: マニフェストの pages 情報が不正です。 原因: pages フィールドがオブジェクト形式ではありません。 対処方法: --full オプションを指定してフル取得を実行してください。"
            )

        pages = {}
        for k, v in raw_pages.items():
            if isinstance(v, dict):
                pages[str(k)] = PageManifestEntry.from_dict(v)

        return cls(
            schema_version=int(schema_v),
            base_url=base_url,
            roots=roots,
            completed=bool(d.get("completed", False)),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            pages=pages,
        )


def save_manifest(manifest: Manifest, output_dir: str, manifest_name: str = DEFAULT_MANIFEST_NAME) -> str:
    """マニフェストを原子的に（一時ファイル作成後に置換）保存する.

    Args:
        manifest: 保存対象のマニフェストオブジェクト
        output_dir: 出力先ディレクトリ
        manifest_name: マニフェストのファイル名

    Returns:
        保存されたマニフェストファイルの絶対パス
    """
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, manifest_name)
    tmp_path = file_path + ".tmp"

    data = manifest.to_dict()
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        logger.error(
            f"現象: マニフェストの保存に失敗しました。 原因: {e} 対処方法: 出力先ディレクトリ ({output_dir}) のアクセス権限と空き容量を確認してください。"
        )
        raise ManifestError(f"マニフェスト保存失敗: {e}") from e

    return file_path


def load_manifest(output_dir: str, manifest_name: str = DEFAULT_MANIFEST_NAME) -> Optional[Manifest]:
    """マニフェストファイルを読み込む.

    Args:
        output_dir: 出力先ディレクトリ
        manifest_name: マニフェストのファイル名

    Returns:
        読み込んだ Manifest オブジェクト。ファイルが存在しない場合は None。

    Raises:
        ManifestCorruptedError: ファイル読み込みまたはデータ構造解析に失敗した場合。
    """
    file_path = os.path.join(output_dir, manifest_name)
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(
            f"現象: マニフェストファイルの読み込みに失敗しました。 原因: {e} 対処方法: --full オプションを指定して全件フル取得を実行するか、破損したマニフェストファイルを削除してください。"
        )
        raise ManifestCorruptedError(
            f"現象: マニフェストファイル ({file_path}) が破損しています。 原因: {e} 対処方法: --full オプションを指定して全件フル取得を実行してください。"
        ) from e

    if not isinstance(data, dict):
        raise ManifestCorruptedError(
            f"現象: マニフェストファイル ({file_path}) の形式が不正です。 原因: JSON ルートがオブジェクトではありません。 対処方法: --full オプションを指定して全件フル取得を実行してください。"
        )

    return Manifest.from_dict(data)


def verify_scope(
    manifest: Manifest,
    current_base_url: str,
    current_root_page_ids: List[str],
    current_space_keys: List[str],
) -> None:
    """既存マニフェストと今回の実行指定（base_url, root_page_ids, space_keys）の整合性をチェックする.

    Args:
        manifest: 既存のマニフェストオブジェクト
        current_base_url: 今回実行時の base_url
        current_root_page_ids: 今回実行時の root_page_ids
        current_space_keys: 今回実行時の space_keys

    Raises:
        ManifestScopeMismatchError: base_url または roots が一致しない場合
    """
    # base_url の正規化（末尾スラッシュの除去）で比較
    norm_manifest_url = manifest.base_url.rstrip("/")
    norm_current_url = current_base_url.rstrip("/")

    if norm_manifest_url != norm_current_url:
        logger.error(
            f"現象: マニフェストの Confluence サーバ URL が一致しません。 原因: 記録値='{manifest.base_url}', 今回指定='{current_base_url}'。 対処方法: 別の出力先ディレクトリを使用するか、--full オプションで再取得してください。"
        )
        raise ManifestScopeMismatchError(
            f"現象: 対象 Confluence サーバの不一致を検出しました。 原因: マニフェストURL({manifest.base_url}) != 指定URL({current_base_url})。 対処方法: 別の出力先ディレクトリを指定するか、--full オプションを使用して初期化を行ってください。"
        )

    manifest_r_ids = set(manifest.roots.root_page_ids)
    current_r_ids = set(current_root_page_ids)
    manifest_s_keys = set(manifest.roots.space_keys)
    current_s_keys = set(current_space_keys)

    if manifest_r_ids != current_r_ids or manifest_s_keys != current_s_keys:
        logger.error(
            f"現象: マニフェストのエクスポート対象（root_page_ids / space_keys）が一致しません。 原因: 記録値=(roots:{manifest.roots.root_page_ids}, spaces:{manifest.roots.space_keys}), 今回指定=(roots:{current_root_page_ids}, spaces:{current_space_keys})。 対処方法: 別の出力先ディレクトリを使用するか、--full オプションで再取得してください。"
        )
        raise ManifestScopeMismatchError(
            "現象: エクスポート対象の不一致を検出しました。 原因: 対象ルートIDまたはSpaceキーの指定が前回と異なります。 対処方法: 前回と同じ対象を指定するか、対象変更時は別の出力先ディレクトリを指定するか --full オプションを使用してください。"
        )
