"""run_analysis のチェックポイント・中断・レジュームのライフサイクルテスト."""

from unittest.mock import MagicMock

import pytest

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.checkpoint import CheckpointStore
from c2m_export.analysis.params import AnalysisParams
from c2m_export.assessment.models import PageMeta


class DummyConfig:
    def __init__(self, tmp_path):
        self.base_url = "https://confluence.example.com"
        self.token = "fake_token"
        self.proxy = None
        self.root_page_ids = ["101"]
        self.space_keys = []
        self.all_spaces = False
        self.cql = None
        self.deep = False
        self.collect_history = None
        self.collect_labels = None
        self.collect_comments = None
        self.collect_watchers = None
        self.collect_effective_restrictions = None
        self.collect_extracted_text = None
        self.collect_space_permissions = None
        self.checkpoint_enabled = True
        self.resume = False
        self.checkpoint_interval = 1
        self.checkpoint_dir = str(tmp_path / "checkpoints")


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.list_spaces.return_value = []

    def get_page_side_effect(page_id, **kwargs):
        return {
            "id": page_id,
            "title": f"Title_{page_id}",
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"when": "2025-01-01T00:00:00Z"},
        }

    client.get_page.side_effect = get_page_side_effect
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.side_effect = lambda pid: [{"id": "102"}] if pid == "101" else []
    return client


def test_run_analysis_checkpoint_normal_completion(tmp_path, mock_client):
    """正常完了時に status="ok" となりチェックポイントが削除されることを確認."""
    cfg = DummyConfig(tmp_path)
    params = AnalysisParams(usecases=["risk"])

    resp = run_analysis(params, cfg, client=mock_client)

    assert resp.status == "ok"
    assert resp.schema_version == "1.2"
    assert resp.uncertainties.interrupted is False
    assert resp.uncertainties.collected_page_count == 2

    # チェックポイントディレクトリ内にファイルが存在しないこと (finalize で削除)
    chk_files = list((tmp_path / "checkpoints").glob("*.jsonl"))
    assert len(chk_files) == 0


def test_run_analysis_checkpoint_interrupted(tmp_path, mock_client):
    """interrupt_checker により途中で中断した場合に status="partial" となりファイルが残置されることを確認."""
    cfg = DummyConfig(tmp_path)
    params = AnalysisParams(usecases=["risk"])

    call_count = 0

    def interrupt_checker():
        nonlocal call_count
        call_count += 1
        return call_count > 1

    resp = run_analysis(params, cfg, client=mock_client, interrupt_checker=interrupt_checker)

    assert resp.status == "partial"
    assert resp.schema_version == "1.2"
    assert resp.uncertainties.interrupted is True
    assert resp.uncertainties.interrupted_reason == "signal"
    assert resp.uncertainties.collected_page_count == 1

    # チェックポイントファイルが残置されていること
    chk_files = list((tmp_path / "checkpoints").glob("*.jsonl"))
    assert len(chk_files) == 1


def test_run_analysis_resume_from_checkpoint(tmp_path, mock_client):
    """--resume 指定時に既存チェックポイントから復元し、未収集分のみ実行されることを確認."""
    cfg = DummyConfig(tmp_path)
    cfg.resume = True

    # スコープハッシュを手動で算出して 101 の復元データをあらかじめファイルに作成
    from c2m_export.analysis.checkpoint import compute_scope_hash

    collect_flags = {
        "analyze_restrictions": True,
        "collect_macros": False,
        "collect_history": False,
        "collect_labels": False,
        "collect_comments": False,
        "collect_watchers": False,
        "collect_effective_restrictions": False,
        "collect_extracted_text": False,
        "collect_space_permissions": False,
    }
    scope_hash = compute_scope_hash(
        base_url=cfg.base_url,
        root_page_ids=cfg.root_page_ids,
        space_keys=cfg.space_keys,
        all_spaces=False,
        cql=None,
        collect_flags=collect_flags,
    )

    chk_dir = tmp_path / "checkpoints"
    chk_dir.mkdir(parents=True, exist_ok=True)
    chk_file = chk_dir / f"{scope_hash}.jsonl"

    pm_101 = PageMeta(
        page_id="101",
        title="Title_101",
        space_key="TEST",
        level=1,
        body_bytes=50,
        last_modified="2025-01-01T00:00:00Z",
        ancestors_titles=[],
    )

    store = CheckpointStore(chk_file, scope_hash=scope_hash, scope_meta={"root_page_ids": ["101"]})
    store.open_for_write(append=False)
    store.append_page(pm_101)
    store.close()

    params = AnalysisParams(usecases=["risk"])

    resp = run_analysis(params, cfg, client=mock_client)

    assert resp.status == "ok"
    assert resp.uncertainties.resumed_from_checkpoint is True
    assert resp.uncertainties.checkpoint_reused_count == 1
    assert resp.uncertainties.collected_page_count == 2
