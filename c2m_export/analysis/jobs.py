"""非同期ジョブの基盤 (spec 0013).

分析を別プロセス（ワーカー）で実行し、進捗と結果をジョブディレクトリ内の
ファイルで受け渡す。ジョブ記録・進捗・結果はいずれも JSON とし、進捗と結果は
「一時ファイルへ書いて rename」する原子書き込みで更新する。

セキュリティ上の配慮:
- ジョブ ID は英数字・ハイフン・アンダースコアのみ許可し、パスの要素として
  安全な形に限定する（--job-status 等の引数によるパストラバーサル防止）。
- ジョブ記録にはトークンや引数列を保存しない（スコープの要約のみ）。
"""

import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_JOBS_DIR = ".c2m_analyze_jobs"
STALE_AFTER_SECONDS = 90.0

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# 進捗の状態
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_PARTIAL = "partial"
STATE_ERROR = "error"


def is_valid_job_id(job_id: Any) -> bool:
    """ジョブ ID がパスの要素として安全な形式かどうかを返す."""
    return isinstance(job_id, str) and bool(_JOB_ID_PATTERN.match(job_id))


def generate_job_id() -> str:
    """新しいジョブ ID（時刻 + ランダムサフィックス）を生成する."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"job-{timestamp}-{secrets.token_hex(3)}"


def job_dir_path(jobs_dir: str, job_id: str) -> Path:
    """ジョブ ID に対応するディレクトリパスを返す（検証付き）."""
    if not is_valid_job_id(job_id):
        raise ValueError(f"無効なジョブ ID です: {job_id!r}")
    return Path(jobs_dir) / job_id


def job_file_paths(jobs_dir: str, job_id: str) -> Dict[str, Path]:
    """ジョブに属する各ファイルのパスを返す."""
    base = job_dir_path(jobs_dir, job_id)
    return {
        "dir": base,
        "job": base / "job.json",
        "progress": base / "progress.json",
        "result": base / "result.json",
        "cancel": base / "cancel.requested",
        "log": base / "worker.log",
    }


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """JSON を一時ファイルへ書いてから rename し、原子的に置き換える."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    """JSON ファイルを読み込む。存在しない・壊れている場合は None を返す."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def utc_now_iso() -> str:
    """現在時刻を ISO 8601 (UTC, Z 表記) で返す."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_job_record(
    jobs_dir: str,
    job_id: str,
    *,
    pid: Optional[int],
    root_page_ids: List[str],
    space_keys: List[str],
) -> Dict[str, Any]:
    """ジョブ記録 (job.json) を作成する。トークンや引数列は含めない."""
    paths = job_file_paths(jobs_dir, job_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    record = {
        "job_id": job_id,
        "pid": pid,
        "created_at": utc_now_iso(),
        "scope": {
            "root_page_ids": list(root_page_ids),
            "space_keys": list(space_keys),
        },
    }
    write_json_atomic(paths["job"], record)
    return record


def build_status(jobs_dir: str, job_id: str) -> Optional[Dict[str, Any]]:
    """ジョブの現在状態を小さい辞書で返す。ジョブが無ければ None.

    実行中なのに進捗の最終更新が古い場合は stale を立て、ワーカーが
    異常終了した可能性を利用者が判断できるようにする。
    """
    paths = job_file_paths(jobs_dir, job_id)
    record = read_json(paths["job"])
    progress = read_json(paths["progress"])
    if record is None and progress is None:
        return None
    record = record or {}
    progress = progress or {}
    status: Dict[str, Any] = {
        "job_id": job_id,
        "state": progress.get("state", STATE_RUNNING),
        "created_at": record.get("created_at"),
        "pid": record.get("pid"),
        "phase": progress.get("phase"),
        "elapsed_seconds": progress.get("elapsed_seconds"),
        "processed": progress.get("processed"),
        "estimated_total": progress.get("estimated_total"),
        "last_collected_page_id": progress.get("last_collected_page_id"),
        "last_update": progress.get("last_update"),
        "started_at": progress.get("started_at"),
        "finished_at": progress.get("finished_at"),
        "cancel_requested": paths["cancel"].exists(),
        "result_file": str(paths["result"]) if paths["result"].exists() else None,
        "log_file": str(paths["log"]),
    }
    if status["state"] == STATE_RUNNING and progress.get("last_update_epoch") is not None:
        age = datetime.now(timezone.utc).timestamp() - float(progress["last_update_epoch"])
        if age > STALE_AFTER_SECONDS:
            status["stale"] = True
            status["note"] = (
                f"進捗の最終更新から {age:.0f} 秒が経過しています。"
                "ワーカーが異常終了した可能性があります。worker.log を確認してください。"
            )
    return status


def build_result_summary(jobs_dir: str, job_id: str) -> Optional[Dict[str, Any]]:
    """完了済みジョブの結果要約を返す。ジョブが無ければ None.

    結果の全量は返さず、結果ファイルへのパスと要点のみを返す
    （エージェントのコンテキストに detail 全量を入れないため）。
    未完了の場合は ready=False と現在の状態を返す。
    """
    paths = job_file_paths(jobs_dir, job_id)
    status = build_status(jobs_dir, job_id)
    if status is None:
        return None
    if status["state"] == STATE_RUNNING or not paths["result"].exists():
        return {
            "job_id": job_id,
            "ready": False,
            "state": status["state"],
            "phase": status.get("phase"),
            "processed": status.get("processed"),
            "estimated_total": status.get("estimated_total"),
            "note": "ジョブはまだ完了していません。--job-status で進捗を確認してください。",
        }
    result = read_json(paths["result"]) or {}
    uncertainties = result.get("uncertainties") or {}
    summary: Dict[str, Any] = {
        "job_id": job_id,
        "ready": True,
        "state": status["state"],
        "status": result.get("status"),
        "result_file": str(paths["result"]),
        "scope": result.get("scope"),
        "summary": result.get("summary"),
        "uncertainties": {
            "collected_page_count": uncertainties.get("collected_page_count"),
            "interrupted": uncertainties.get("interrupted"),
            "interrupted_reason": uncertainties.get("interrupted_reason"),
            "skipped_page_count": len(uncertainties.get("skipped_page_ids") or []),
            "empty_space_keys": uncertainties.get("empty_space_keys"),
            "cql_failed": uncertainties.get("cql_failed"),
            "resumed_from_checkpoint": uncertainties.get("resumed_from_checkpoint"),
            "checkpoint_reused_count": uncertainties.get("checkpoint_reused_count"),
        },
    }
    if result.get("error"):
        summary["error"] = result["error"]
    return summary


def request_cancel(jobs_dir: str, job_id: str) -> bool:
    """キャンセルフラグを置く。ジョブが存在すれば True.

    存在判定は build_status と揃え、ジョブ記録と進捗のどちらかが
    読めれば存在するものとして扱う（起動直後などジョブ記録が
    まだ無い状態でも、状態確認で見えるジョブは中断できるように）。
    """
    paths = job_file_paths(jobs_dir, job_id)
    if read_json(paths["job"]) is None and read_json(paths["progress"]) is None:
        return False
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["cancel"].write_text(utc_now_iso(), encoding="utf-8")
    return True


def start_job(
    jobs_dir: str,
    job_id: str,
    worker_args: List[str],
    *,
    root_page_ids: List[str],
    space_keys: List[str],
) -> Dict[str, Any]:
    """ワーカープロセスを切り離して起動し、開始情報を返す.

    ワーカーは同じ CLI を `--async-worker` モードで実行する。標準出力・
    標準エラーはジョブディレクトリ内の worker.log へリダイレクトする。
    """
    paths = job_file_paths(jobs_dir, job_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-u", "-m", "c2m_export.analyze"] + worker_args
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    popen_kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "env": env,
        "cwd": os.getcwd(),
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    else:
        popen_kwargs["start_new_session"] = True

    with open(paths["log"], "ab") as log_file:
        popen_kwargs["stdout"] = log_file
        popen_kwargs["stderr"] = subprocess.STDOUT
        process = subprocess.Popen(cmd, **popen_kwargs)

    create_job_record(jobs_dir, job_id, pid=process.pid, root_page_ids=root_page_ids, space_keys=space_keys)
    write_json_atomic(
        paths["progress"],
        {
            "job_id": job_id,
            "state": STATE_RUNNING,
            "phase": "開始",
            "elapsed_seconds": 0,
            "processed": None,
            "estimated_total": None,
            "last_collected_page_id": None,
            "last_update": utc_now_iso(),
            "last_update_epoch": datetime.now(timezone.utc).timestamp(),
            "started_at": utc_now_iso(),
            "finished_at": None,
        },
    )
    return {
        "job_id": job_id,
        "state": STATE_RUNNING,
        "pid": process.pid,
        "jobs_dir": str(Path(jobs_dir)),
        "progress_file": str(paths["progress"]),
        "result_file": str(paths["result"]),
        "log_file": str(paths["log"]),
        "note": "--job-status <job_id> で進捗確認、--job-result <job_id> で結果取得、--job-cancel <job_id> で中断できます。",
    }
