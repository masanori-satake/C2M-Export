"""非同期ジョブ基盤 (spec 0013) の単体テスト."""

import time

import pytest

from c2m_export.analysis import jobs


def test_job_id_validation():
    """安全なジョブ ID のみ許可し、パストラバーサル等を拒否する."""
    assert jobs.is_valid_job_id("job-20261106000000-abcdef")
    assert not jobs.is_valid_job_id("../etc/passwd")
    assert not jobs.is_valid_job_id("a/b")
    assert not jobs.is_valid_job_id("")
    assert not jobs.is_valid_job_id(None)
    with pytest.raises(ValueError):
        jobs.job_file_paths(".jobs", "../evil")


def test_generate_job_id_format():
    """生成されるジョブ ID は検証を通る形式である."""
    job_id = jobs.generate_job_id()
    assert job_id.startswith("job-")
    assert jobs.is_valid_job_id(job_id)


def test_status_and_result_flow(tmp_path):
    """ジョブ記録・進捗・結果から status と result 要約が構築される."""
    jobs_dir = str(tmp_path)
    job_id = "job-test-1"
    jobs.create_job_record(jobs_dir, job_id, pid=1234, root_page_ids=["100"], space_keys=[])
    paths = jobs.job_file_paths(jobs_dir, job_id)

    status = jobs.build_status(jobs_dir, job_id)
    assert status is not None
    assert status["state"] == "running"
    assert status["pid"] == 1234
    assert status["result_file"] is None

    running_result = jobs.build_result_summary(jobs_dir, job_id)
    assert running_result is not None
    assert running_result["ready"] is False

    jobs.write_json_atomic(
        paths["result"],
        {
            "status": "ok",
            "scope": {"root_page_ids": ["100"], "space_keys": [], "resolved_root_count": 1},
            "summary": {"total_pages": 3},
            "uncertainties": {
                "collected_page_count": 3,
                "interrupted": False,
                "interrupted_reason": None,
                "skipped_page_ids": ["9"],
                "empty_space_keys": [],
                "cql_failed": False,
                "resumed_from_checkpoint": False,
                "checkpoint_reused_count": 0,
            },
        },
    )
    jobs.write_json_atomic(
        paths["progress"],
        {
            "job_id": job_id,
            "state": "done",
            "phase": "完了",
            "elapsed_seconds": 12.3,
            "processed": 3,
            "estimated_total": 3,
            "last_update": jobs.utc_now_iso(),
            "last_update_epoch": time.time(),
            "started_at": jobs.utc_now_iso(),
            "finished_at": jobs.utc_now_iso(),
        },
    )

    status = jobs.build_status(jobs_dir, job_id)
    assert status["state"] == "done"
    assert status["result_file"] is not None

    summary = jobs.build_result_summary(jobs_dir, job_id)
    assert summary is not None
    assert summary["ready"] is True
    assert summary["status"] == "ok"
    assert summary["summary"] == {"total_pages": 3}
    assert summary["uncertainties"]["collected_page_count"] == 3
    assert summary["uncertainties"]["skipped_page_count"] == 1
    # 結果の全量ではなく要約のみを返す（detail が含まれない）
    assert "usecases" not in summary


def test_status_marks_stale_running_job(tmp_path):
    """実行中なのに進捗更新が古いジョブは stale になる."""
    jobs_dir = str(tmp_path)
    job_id = "job-test-stale"
    jobs.create_job_record(jobs_dir, job_id, pid=None, root_page_ids=[], space_keys=[])
    paths = jobs.job_file_paths(jobs_dir, job_id)
    jobs.write_json_atomic(
        paths["progress"],
        {
            "job_id": job_id,
            "state": "running",
            "phase": "ページ収集",
            "last_update_epoch": time.time() - (jobs.STALE_AFTER_SECONDS + 60),
        },
    )
    status = jobs.build_status(jobs_dir, job_id)
    assert status is not None
    assert status["stale"] is True


def test_unknown_job_returns_none(tmp_path):
    """存在しないジョブは None を返す."""
    assert jobs.build_status(str(tmp_path), "job-missing") is None
    assert jobs.build_result_summary(str(tmp_path), "job-missing") is None
    assert jobs.request_cancel(str(tmp_path), "job-missing") is False


def test_request_cancel_sets_flag(tmp_path):
    """キャンセルフラグが置かれ、status に反映される."""
    jobs_dir = str(tmp_path)
    job_id = "job-test-cancel"
    jobs.create_job_record(jobs_dir, job_id, pid=None, root_page_ids=[], space_keys=[])
    assert jobs.request_cancel(jobs_dir, job_id) is True
    status = jobs.build_status(jobs_dir, job_id)
    assert status is not None
    assert status["cancel_requested"] is True


def test_request_cancel_with_progress_only(tmp_path):
    """ジョブ記録が無く進捗だけあるジョブ（起動直後）も中断できる (spec 0019 F1)."""
    jobs_dir = str(tmp_path)
    job_id = "job-test-progress-only"
    paths = jobs.job_file_paths(jobs_dir, job_id)
    jobs.write_json_atomic(paths["progress"], {"job_id": job_id, "state": "running"})
    # status では見えるジョブであること
    assert jobs.build_status(jobs_dir, job_id) is not None
    assert jobs.request_cancel(jobs_dir, job_id) is True
    assert paths["cancel"].exists()
