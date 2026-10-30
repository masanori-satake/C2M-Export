"""分析モードのチェックポイント永続化・復元・スコープ照合モジュール."""

import dataclasses
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, TextIO, Tuple, Union

from c2m_export.assessment.models import AttachmentMeta, PageMeta, RestrictionMeta

logger = logging.getLogger(__name__)


class CollectInterrupted(Exception):
    """収集フェーズが協調的に中断されたことを示す内部例外."""

    pass


def compute_scope_hash(
    base_url: Optional[str],
    root_page_ids: List[str],
    space_keys: List[str],
    all_spaces: bool,
    cql: Optional[str],
    collect_flags: Dict[str, bool],
) -> str:
    """分析スコープを正規化し安定した 16 桁の SHA-256 ハッシュ文字列を算出する（純粋関数）.

    トークンや表示系オプション（limit/sort/mode）は含めず、収集結果に影響するフラグのみを含める。

    Args:
        base_url: Confluence ベース URL
        root_page_ids: ルートページ ID リスト
        space_keys: Space キーリスト
        all_spaces: 全 Space 対象フラグ
        cql: CQL 検索クエリ
        collect_flags: 収集系フラグ辞書（キー順で正規化）

    Returns:
        str: 16 桁の 16 進行数ハッシュ文字列
    """
    normalized_url = (base_url or "").rstrip("/")
    sorted_root_ids = sorted(root_page_ids or [])
    sorted_space_keys = sorted(space_keys or [])
    sorted_flags = {k: bool(v) for k, v in sorted(collect_flags.items())}

    normalized_payload = {
        "base_url": normalized_url,
        "root_page_ids": sorted_root_ids,
        "space_keys": sorted_space_keys,
        "all_spaces": bool(all_spaces),
        "cql": cql or "",
        "collect_flags": sorted_flags,
    }

    json_bytes = json.dumps(normalized_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    full_hash = hashlib.sha256(json_bytes).hexdigest()
    return full_hash[:16]


def page_meta_to_record(page_meta: PageMeta) -> dict:
    """PageMeta インスタンスを JSONL 書込用の dict レコードへ変換する (純粋関数).

    Args:
        page_meta: ページメタデータオブジェクト

    Returns:
        dict: {"_type": "page", "page": {...}} 形式の辞書
    """
    return {
        "_type": "page",
        "page": dataclasses.asdict(page_meta),
    }


def record_to_page_meta(record: dict) -> PageMeta:
    """JSONL dict レコードから PageMeta インスタンスを再構築する (純粋関数).

    ネストした AttachmentMeta, RestrictionMeta を明示的に再構築し型を保持する。

    Args:
        record: JSONL から読み込んだ dict（{"_type": "page", "page": {...}} または "page" キー配下の dict）

    Returns:
        PageMeta: 再構築された PageMeta インスタンス
    """
    page_dict = record.get("page", record) if isinstance(record, dict) else {}
    data = dict(page_dict)

    # 1. 添付メタデータの再構築
    attachments_raw = data.get("attachments", [])
    attachments = []
    if isinstance(attachments_raw, list):
        for item in attachments_raw:
            if isinstance(item, dict):
                attachments.append(AttachmentMeta(**item))
    data["attachments"] = attachments

    # 2. アクセス制限メタデータの再構築
    restriction_raw = data.get("restriction")
    if isinstance(restriction_raw, dict):
        data["restriction"] = RestrictionMeta(**restriction_raw)
    else:
        data["restriction"] = None

    # 3. 実効アクセス制限メタデータの再構築
    eff_restriction_raw = data.get("effective_view_restrictions")
    if isinstance(eff_restriction_raw, dict):
        data["effective_view_restrictions"] = RestrictionMeta(**eff_restriction_raw)
    else:
        data["effective_view_restrictions"] = None

    return PageMeta(**data)


class CheckpointStore:
    """JSONL 形式の分析チェックポイントファイル追記・復元・管理を行うクラス."""

    def __init__(
        self,
        path: Union[str, Path],
        scope_hash: str,
        scope_meta: Optional[dict] = None,
        interval: int = 1,
    ):
        """CheckpointStore を初期化する.

        Args:
            path: チェックポイントファイルのパス
            scope_hash: スコープ識別ハッシュ文字列
            scope_meta: スコープメタ情報辞書
            interval: flush 実行間隔 (件数)
        """
        self.path = Path(path)
        self.scope_hash = scope_hash
        self.scope_meta = scope_meta or {}
        self.interval = max(1, interval)
        self._file: Optional[TextIO] = None
        self._pending_count = 0

    def open_for_write(self, append: bool = True) -> None:
        """チェックポイントファイルを追記または新規作成モードで開く."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            msg = (
                f"現象: チェックポイントディレクトリ '{self.path.parent}' の作成に失敗しました。"
                f"原因: {e}。"
                f"対処方法: 書き込み権限およびパスを確認してください。"
            )
            logger.error(msg)
            raise OSError(msg) from e

        file_exists = self.path.exists() and self.path.stat().st_size > 0

        try:
            if append and file_exists:
                self._file = open(self.path, "a", encoding="utf-8")
            else:
                self._file = open(self.path, "w", encoding="utf-8")
                header = {
                    "_type": "header",
                    "scope_hash": self.scope_hash,
                    "scope": self.scope_meta,
                    "schema_version": "1.2",
                }
                if self._file is not None:
                    self._file.write(json.dumps(header, ensure_ascii=False) + "\n")
                self.flush()
        except Exception as e:
            msg = (
                f"現象: チェックポイントファイル '{self.path}' のオープンまたはヘッダ書き込みに失敗しました。"
                f"原因: {e}。"
                f"対処方法: ディスク空き容量およびファイルアクセス権限を確認してください。"
            )
            logger.error(msg)
            raise OSError(msg) from e

    def append_page(self, page_meta: PageMeta) -> None:
        """1 ページ分の PageMeta を JSONL レコードとして追記する."""
        if self._file is None:
            self.open_for_write(append=True)

        record = page_meta_to_record(page_meta)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        if self._file is not None:
            self._file.write(line)
        self._pending_count += 1

        if self._pending_count >= self.interval:
            self.flush()

    def flush(self) -> None:
        """ファイルバッファをフラッシュし OS レベルでディスクに同期する."""
        if self._file is not None and not self._file.closed:
            self._file.flush()
            try:
                os.fsync(self._file.fileno())
            except Exception:
                pass
            self._pending_count = 0

    def scope_matches(self, scope_hash: str) -> bool:
        """既存チェックポイントファイルのヘッダから scope_hash を読み取り一致するか判定する."""
        if not self.path.exists():
            return False

        try:
            with open(self.path, encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line:
                    return False
                header = json.loads(first_line)
                if isinstance(header, dict) and header.get("_type") == "header":
                    return header.get("scope_hash") == scope_hash
        except Exception as e:
            logger.warning(f"チェックポイントヘッダの読み込みに失敗しました ({self.path}): {e}")

        return False

    def load_collected(self) -> Tuple[List[PageMeta], Set[str], List[str]]:
        """チェックポイントファイルから収集済み PageMeta を復元する.

        破損行（JSON パースエラーや不正行）はスキップし、破損行リストとして記録する。

        Returns:
            Tuple[List[PageMeta], Set[str], List[str]]:
                (復元 PageMeta リスト, 収集済み page_id 集合, 破損行リスト)
        """
        pages_map: Dict[str, PageMeta] = {}
        corrupted_lines: List[str] = []

        if not self.path.exists():
            return [], set(), corrupted_lines

        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue

                    try:
                        record = json.loads(line_str)
                    except Exception:
                        corrupted_lines.append(line_str)
                        continue

                    if not isinstance(record, dict):
                        corrupted_lines.append(line_str)
                        continue

                    if record.get("_type") == "header":
                        continue

                    if record.get("_type") == "page":
                        try:
                            pm = record_to_page_meta(record)
                            pages_map[pm.page_id] = pm
                        except Exception as e:
                            logger.warning(f"PageMeta 復元中にエラーが発生しました: {e}")
                            corrupted_lines.append(line_str)
                    else:
                        corrupted_lines.append(line_str)
        except Exception as e:
            logger.error(f"チェックポイントファイルの復元読み込み中にエラーが発生しました: {e}")

        pages = list(pages_map.values())
        collected_ids = set(pages_map.keys())
        return pages, collected_ids, corrupted_lines

    def close(self) -> None:
        """ファイルハンドルをフラッシュしてクローズする."""
        if self._file is not None:
            if not self._file.closed:
                try:
                    self.flush()
                except Exception:
                    pass
                self._file.close()
            self._file = None

    def finalize(self, success: bool) -> None:
        """実行完了時の後始末を行う. 成功時はチェックポイントファイルを削除する."""
        self.close()
        if success and self.path.exists():
            try:
                self.path.unlink()
            except Exception as e:
                logger.warning(f"チェックポイントファイルの削除に失敗しました ({self.path}): {e}")
