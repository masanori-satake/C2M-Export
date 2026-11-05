"""非同期ジョブ CLI (spec 0013) の統合テスト.

ワーカーの起動は Popen をモックして検証し、ワーカーモード自体は
同一プロセスで --async-worker を直接実行して検証する。
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.analyze import main


def _base_args(tmp_path):
    return [
        "analyze",
        "--base-url",
        "https://example.com/wiki",
        "--root-page-id",
        "100",
        "--token",
        "secret_token_123",
        "--config",
        str(tmp_path / "nonexistent.yaml"),
        "--job-dir",
        str(tmp_path / "jobs"),
    ]


def _mock_client():
    client = MagicMock()
    client.list_spaces.return_value = [{"key": "DEV"}]
    client.get_page.return_value = {
        "title": "Test Title",
        "space": {"key": "TEST"},
        "version": {"when": "2026-01-01T00:00:00Z"},
        "body": {"storage": {"value": "Test body"}},
    }
    client.get_descendant_page_count.return_value = {"count": 0}
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []
    return client


def test_detach_starts_worker_and_returns_job_id(monkeypatch, capsys, tmp_path):
    """--detach はワーカーを起動し、job_id を即座に返す。ジョブ記録にトークンを含めない."""
    monkeypatch.setattr(sys, "argv", _base_args(tmp_path) + ["--detach"])
    fake_process = MagicMock()
    fake_process.pid = 4242
    with patch("c2m_export.analysis.jobs.subprocess.Popen", return_value=fake_process) as popen_mock:
        with pytest.raises(SystemExit) as excinfo:
            main()
    assert excinfo.value.code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "running"
    job_id = out["job_id"]
    assert job_id.startswith("job-")

    cmd = popen_mock.call_args.args[0]
    assert "--async-worker" in cmd
    assert "--job-id" in cmd and job_id in cmd
    assert "--detach" not in cmd

    job_record = json.loads((tmp_path / "jobs" / job_id / "job.json").read_text(encoding="utf-8"))
    assert job_record["pid"] == 4242
    assert job_record["scope"]["root_page_ids"] == ["100"]
    assert "secret_token_123" not in (tmp_path / "jobs" / job_id / "job.json").read_text(encoding="utf-8")


def test_worker_writes_result_and_progress_then_status_and_result(monkeypatch, capsys, tmp_path):
    """ワーカーモードで実行すると結果と進捗が書かれ、status / result で取得できる."""
    job_id = "job-test-worker"
    args = _base_args(tmp_path) + ["--async-worker", "--job-id", job_id]
    monkeypatch.setattr(sys, "argv", args)
    mock_client = _mock_client()
    with patch("c2m_export.analysis.api.ConfluenceClient", return_value=mock_client), patch(
        "c2m_export.analysis.estimate.ConfluenceClient", return_value=mock_client
    ):
        with pytest.raises(SystemExit) as excinfo:
            main()
    assert excinfo.value.code == 0
    capsys.readouterr()

    job_dir = tmp_path / "jobs" / job_id
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert "secret_token_123" not in (job_dir / "result.json").read_text(encoding="utf-8")
    progress = json.loads((job_dir / "progress.json").read_text(encoding="utf-8"))
    assert progress["state"] == "done"
    assert progress["estimated_total"] == 1

    # status の取得（設定検証なしで即座に返る）
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze",
            "--job-status",
            job_id,
            "--job-dir",
            str(tmp_path / "jobs"),
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["state"] == "done"

    # result の取得（要約のみ）
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze",
            "--job-result",
            job_id,
            "--job-dir",
            str(tmp_path / "jobs"),
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    result_out = json.loads(capsys.readouterr().out)
    assert result_out["ready"] is True
    assert result_out["status"] == "ok"
    assert result_out["result_file"].endswith("result.json")


def test_job_status_unknown_and_invalid(monkeypatch, capsys, tmp_path):
    """存在しないジョブは not_found (終了コード4)、不正な ID はエラー (終了コード2)."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze",
            "--job-status",
            "job-missing",
            "--job-dir",
            str(tmp_path / "jobs"),
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 4
    assert json.loads(capsys.readouterr().out)["state"] == "not_found"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze",
            "--job-status",
            "../evil",
            "--job-dir",
            str(tmp_path / "jobs"),
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
