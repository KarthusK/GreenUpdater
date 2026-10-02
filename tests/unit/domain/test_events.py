"""domain.events 测试：CancelToken 与 NullListener。"""
from __future__ import annotations

from greenupdater.domain import CancelToken, NullListener, Progress, StageResult
from greenupdater.models import UpdateStage


def test_cancel_token_default_not_cancelled():
    t = CancelToken()
    assert t.cancelled is False


def test_cancel_token_cancel_sets_flag():
    t = CancelToken()
    t.cancel()
    assert t.cancelled is True


def test_null_listener_accepts_all_calls():
    l = NullListener()
    l.on_log("hi")
    l.on_progress(Progress(stage=UpdateStage.DOWNLOAD, percent=10, message="x"))
    l.on_stage(StageResult(stage=UpdateStage.CHECK, ok=True))
    l.on_cancelled()


def test_null_listener_satisfies_protocol():
    from greenupdater.domain import UpdateListener

    assert isinstance(NullListener(), UpdateListener)
