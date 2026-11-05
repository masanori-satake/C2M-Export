"""分析 (analyze) CLI エントリーポイントモジュール (python -m c2m_export.analyze)."""

import json
import logging
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, NoReturn, Optional

from c2m_export.analysis import jobs as jobs_module
from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.estimate import estimate_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.response import (
    CODE_API_ERROR,
    CODE_AUTH_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_PARAM,
    CODE_PARTIAL,
    CODE_TARGET_NOT_FOUND,
    AnalysisResponse,
    ErrorObject,
)
from c2m_export.analysis.sanitize import sanitize_text
from c2m_export.config import AnalysisConfig

# エラーコード → 終了コード マッピングテーブル
EXIT_CODES: Dict[str, int] = {
    CODE_INVALID_PARAM: 2,
    CODE_AUTH_FAILED: 3,
    CODE_TARGET_NOT_FOUND: 4,
    CODE_API_ERROR: 5,
    CODE_PARTIAL: 6,
    CODE_INTERNAL_ERROR: 10,
}

_interrupted_event = threading.Event()


def _signal_handler(signum: int, frame: object) -> None:
    """SIGINT / SIGTERM シグナル受信時に協調的中断フラグを立てるハンドラ."""
    _interrupted_event.set()


def _print_json_and_exit(data: Dict[str, Any], exit_code: int = 0) -> NoReturn:
    """辞書を JSON として標準出力へ書き、指定コードで終了する."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    sys.exit(exit_code)


def _dispatch_job_commands(config: AnalysisConfig) -> None:
    """ジョブ操作コマンド (--job-status / --job-result / --job-cancel) を処理する.

    該当する指定がある場合のみ動作し、必ず SystemExit で終了する。
    ファイルだけを読むため、設定の検証 (base_url 等) より前に呼び出すこと。
    """
    job_id = config.job_status or config.job_result or config.job_cancel
    if not job_id:
        return
    if not jobs_module.is_valid_job_id(job_id):
        _print_json_and_exit(
            {
                "job_id": job_id,
                "state": "error",
                "error": {
                    "code": "INVALID_PARAM",
                    "message": "現象: ジョブ ID の形式が無効です。対処方法: --detach の開始時に返された job_id を指定してください。",
                },
            },
            exit_code=EXIT_CODES[CODE_INVALID_PARAM],
        )
    if config.job_status:
        status = jobs_module.build_status(config.job_dir, job_id)
        if status is None:
            _print_json_and_exit(
                {"job_id": job_id, "state": "not_found"},
                exit_code=EXIT_CODES[CODE_TARGET_NOT_FOUND],
            )
        _print_json_and_exit(status)
    elif config.job_result:
        summary = jobs_module.build_result_summary(config.job_dir, job_id)
        if summary is None:
            _print_json_and_exit(
                {"job_id": job_id, "state": "not_found"},
                exit_code=EXIT_CODES[CODE_TARGET_NOT_FOUND],
            )
        _print_json_and_exit(summary)
    elif config.job_cancel:
        if not jobs_module.request_cancel(config.job_dir, job_id):
            _print_json_and_exit(
                {"job_id": job_id, "state": "not_found"},
                exit_code=EXIT_CODES[CODE_TARGET_NOT_FOUND],
            )
        status = jobs_module.build_status(config.job_dir, job_id) or {}
        _print_json_and_exit(
            {
                "job_id": job_id,
                "cancel_requested": True,
                "state": status.get("state"),
                "note": "ワーカーが協調的に中断し、収集済み分は partial として残ります。再開は --resume を使用してください。",
            }
        )


def _prepare_worker(params: AnalysisParams, config: AnalysisConfig) -> Dict[str, Any]:
    """ワーカーモード (--async-worker) の進捗書き込みと中断判定を準備する.

    Returns:
        progress_sink / interrupt_checker / finalize を含む辞書。
        finalize は実行結果を受け取り、結果ファイルの書き出しと進捗の最終化を行う。
    """
    job_id = str(config.job_id)
    paths = jobs_module.job_file_paths(config.job_dir, job_id)
    # 開始側が作るジョブ記録が無い場合はワーカー自身が補う（単独起動でも status が引けるように）
    if jobs_module.read_json(paths["job"]) is None:
        jobs_module.create_job_record(
            config.job_dir,
            job_id,
            pid=None,
            root_page_ids=getattr(config, "root_page_ids", []) or [],
            space_keys=getattr(config, "space_keys", []) or [],
        )
    started_at = jobs_module.utc_now_iso()
    start_monotonic = time.monotonic()

    # 推定総ページ数（見積もりに失敗しても本実行は継続する）
    estimated_total: Optional[int] = None
    if not getattr(config, "estimate", False):
        try:
            est_resp = estimate_analysis(params, config)
            if est_resp.estimate:
                estimated_total = est_resp.estimate.get("target_pages")
        except Exception:
            estimated_total = None

    def _write_progress(state: str, phase: str, processed: Optional[int], finished_at: Optional[str] = None) -> None:
        jobs_module.write_json_atomic(
            paths["progress"],
            {
                "job_id": job_id,
                "state": state,
                "phase": phase,
                "elapsed_seconds": round(time.monotonic() - start_monotonic, 1),
                "processed": processed,
                "estimated_total": estimated_total,
                "last_collected_page_id": None,
                "last_update": jobs_module.utc_now_iso(),
                "last_update_epoch": time.time(),
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )

    _write_progress(jobs_module.STATE_RUNNING, "開始", None)

    def _progress_sink(phase: str, elapsed: float, count: Optional[int]) -> None:
        _write_progress(jobs_module.STATE_RUNNING, phase, count)

    def _interrupt_checker() -> bool:
        return _interrupted_event.is_set() or paths["cancel"].exists()

    def _finalize(response: AnalysisResponse, cfg: AnalysisConfig) -> None:
        state = {
            "ok": jobs_module.STATE_DONE,
            "partial": jobs_module.STATE_PARTIAL,
            "error": jobs_module.STATE_ERROR,
        }.get(response.status, jobs_module.STATE_ERROR)
        json_out = json.dumps(response.to_dict(), ensure_ascii=False, indent=2)
        sanitized = sanitize_text(json_out, secrets=[cfg.token])
        jobs_module.write_json_atomic(paths["result"], json.loads(sanitized))
        _write_progress(
            state,
            "完了",
            response.uncertainties.collected_page_count,
            finished_at=jobs_module.utc_now_iso(),
        )

    return {
        "progress_sink": _progress_sink,
        "interrupt_checker": _interrupt_checker,
        "finalize": _finalize,
    }


def main() -> None:
    """CLI メイン関数."""
    # ログ設定: 人間向けの進捗・警告・エラーログをすべて stderr へ出力する
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    _interrupted_event.clear()

    orig_sigint = None
    orig_sigterm = None
    try:
        try:
            orig_sigint = signal.signal(signal.SIGINT, _signal_handler)
        except (ValueError, OSError):
            pass

        if hasattr(signal, "SIGTERM"):
            try:
                orig_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
            except (ValueError, OSError):
                pass

        config = AnalysisConfig()

        try:
            # 設定の読込 (CLI引数, 環境変数, YAML)
            config.load()
            # ジョブ操作コマンドはファイルだけを読むため、検証より前に処理する
            _dispatch_job_commands(config)
            config.validate()
        except Exception as e:
            # 設定ロード・検証エラー時
            msg = str(e)
            err_msg = (
                msg
                if "現象:" in msg
                else f"現象: 設定エラー。原因: {msg}。対処方法: 引数または設定ファイルを確認してください。"
            )
            err_resp = AnalysisResponse(
                schema_version="1.2",
                status="error",
                error=ErrorObject(code=CODE_INVALID_PARAM, message=err_msg),
            )
            json_out = json.dumps(err_resp.to_dict(), ensure_ascii=False, indent=2)
            sanitized_json = sanitize_text(json_out, secrets=[config.token])
            sys.stdout.write(sanitized_json + "\n")

            stderr_msg = sanitize_text(f"エラー: {msg}", secrets=[config.token])
            sys.stderr.write(stderr_msg + "\n")
            sys.exit(EXIT_CODES[CODE_INVALID_PARAM])

        # AnalysisParams 構築
        params = AnalysisParams(
            usecases=config.usecases if config.usecases else AnalysisParams().usecases,
            mode=config.mode,
            limit=config.limit,
            stale_days=config.stale_days,
            min_body_bytes=config.min_body_bytes,
            archive_extensions=config.archive_extensions
            if config.archive_extensions is not None
            else AnalysisParams().archive_extensions,
            analyze_restrictions=config.analyze_restrictions,
            all_spaces=config.all_spaces,
            cql=config.cql,
            deep=config.deep,
            collect_history=config.collect_history,
            collect_labels=config.collect_labels,
            collect_comments=config.collect_comments,
            collect_watchers=config.collect_watchers,
            collect_effective_restrictions=config.collect_effective_restrictions,
            collect_extracted_text=config.collect_extracted_text,
            collect_space_permissions=config.collect_space_permissions,
            checkpoint_enabled=config.checkpoint_enabled,
            resume=config.resume,
            checkpoint_interval=config.checkpoint_interval,
            checkpoint_dir=config.checkpoint_dir,
            timeout_seconds=config.timeout_seconds,
            max_pages=config.max_pages,
            concurrency=config.concurrency,
        )

        # 非同期開始（--detach）: ワーカーを別プロセスで起動して即座に返す
        if getattr(config, "detach", False) and not getattr(config, "async_worker", False):
            new_job_id = jobs_module.generate_job_id()
            worker_args = [a for a in sys.argv[1:] if a != "--detach"]
            if not any(a == "--job-dir" or a.startswith("--job-dir=") for a in worker_args):
                worker_args += ["--job-dir", config.job_dir]
            worker_args += ["--async-worker", "--job-id", new_job_id]
            start_info = jobs_module.start_job(
                config.job_dir,
                new_job_id,
                worker_args,
                root_page_ids=config.root_page_ids,
                space_keys=config.space_keys,
            )
            sys.stdout.write(json.dumps(start_info, ensure_ascii=False, indent=2) + "\n")
            sys.exit(0)

        # ワーカーモードの準備（進捗ファイル書き込み・キャンセルフラグ監視）
        worker_ctx: Optional[Dict[str, Any]] = None
        if getattr(config, "async_worker", False) and getattr(config, "job_id", None):
            worker_ctx = _prepare_worker(params, config)
        run_interrupt_checker: Callable[[], bool] = _interrupted_event.is_set
        progress_sink = None
        if worker_ctx is not None:
            run_interrupt_checker = worker_ctx["interrupt_checker"]
            progress_sink = worker_ctx["progress_sink"]

        # 実行（--estimate 指定時は事前見積もりのみを行い、本走査は行わない）
        if getattr(config, "estimate", False):
            response = estimate_analysis(params, config, interrupt_checker=run_interrupt_checker)
        elif progress_sink is not None:
            response = run_analysis(
                params,
                config,
                interrupt_checker=run_interrupt_checker,
                progress_sink=progress_sink,
            )
        else:
            response = run_analysis(params, config, interrupt_checker=run_interrupt_checker)

        # ワーカーは結果ファイルへ書き出し、進捗を最終状態にする
        if worker_ctx is not None:
            worker_ctx["finalize"](response, config)

        # 出力文字列のサニタイズ（全出力に対して1回のみ適用）
        json_out = json.dumps(response.to_dict(), ensure_ascii=False, indent=2)
        sanitized_json = sanitize_text(json_out, secrets=[config.token])

        sys.stdout.write(sanitized_json + "\n")

        if response.status == "partial":
            if config.checkpoint_enabled:
                partial_msg = "部分成功結果 (partial) を出力しました。--resume オプションを指定することで未収集ページから再開できます。"
            else:
                partial_msg = "部分成功結果 (partial) を出力しました。--no-checkpoint が指定されているため、チェックポイントからの再開はできません。"
            stderr_msg = sanitize_text(partial_msg, secrets=[config.token])
            sys.stderr.write(stderr_msg + "\n")
            sys.exit(EXIT_CODES.get(CODE_PARTIAL, 6))
    finally:
        if orig_sigint is not None:
            try:
                signal.signal(signal.SIGINT, orig_sigint)
            except (ValueError, OSError):
                pass
        if orig_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, orig_sigterm)
            except (ValueError, OSError):
                pass

    if response.status != "ok":
        err_code = response.error.code if response.error else CODE_INTERNAL_ERROR
        err_msg = response.error.message if response.error else "不明なエラーが発生しました"
        stderr_msg = sanitize_text(f"エラー: {err_msg}", secrets=[config.token])
        sys.stderr.write(stderr_msg + "\n")
        exit_code = EXIT_CODES.get(err_code, 1)
        sys.exit(exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main()
