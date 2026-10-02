"""ui.worker 测试（pytest-qt）：批处理槽发信号、阻塞决策回传。

worker 方法在测试中同步调用（未 moveToThread），AutoConnection 退化为直连，
因此 ask_kill / ask_asset 的 emit 会同步执行已连接的槽，_Response 得以回填。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from greenupdater.domain import Asset
from greenupdater.models import App, UpdateResult
from greenupdater.ui.worker import BatchReport, UpdateWorker


def make_app(**kw) -> App:
    base = dict(
        id=1,
        uid="u1",
        name="App",
        repo_owner="o",
        repo_name="r",
        asset_pattern=r".*\.zip",
        target_dir=Path("D:/x"),
    )
    base.update(kw)
    return App(**base)


@dataclass
class _Res:
    app_uid: str
    result: UpdateResult = UpdateResult.SUCCESS
    update_available: bool = False
    error: str | None = None


class FakeOrchestrator:
    def __init__(self) -> None:
        self.check_calls = 0
        self.update_calls = 0
        self.rollback_calls = 0

    def check(self, app, listener):
        self.check_calls += 1
        listener.on_log(f"check {app.name}")
        return _Res(app.uid, update_available=True)

    def update(self, app, listener, cancel, confirm_kill, choose_asset):
        self.update_calls += 1
        listener.on_log(f"update {app.name}")
        return _Res(app.uid, result=UpdateResult.SUCCESS)

    def rollback(self, app, listener):
        self.rollback_calls += 1
        return _Res(app.uid, result=UpdateResult.SUCCESS)


@pytest.fixture()
def orch():
    return FakeOrchestrator()


@pytest.fixture()
def worker(qtbot, orch):
    return UpdateWorker(orch)


def test_run_check_emits_finished(worker, qtbot, orch):
    apps = [make_app(uid="a"), make_app(uid="b")]
    logs: list[str] = []
    finished: list[BatchReport] = []
    worker.sig_log.connect(logs.append)
    worker.sig_finished.connect(finished.append)

    worker.run_check(apps)

    assert orch.check_calls == 2
    assert any("check" in x for x in logs)
    assert len(finished) == 1
    assert finished[0].op == "check"
    assert len(finished[0].items) == 2


def test_run_update_emits_finished(worker, qtbot, orch):
    apps = [make_app(uid="a")]
    finished: list[BatchReport] = []
    worker.sig_finished.connect(finished.append)

    worker.run_update(apps)

    assert orch.update_calls == 1
    assert finished[0].op == "update"


def test_run_rollback_emits_finished(worker, qtbot, orch):
    finished: list[BatchReport] = []
    worker.sig_finished.connect(finished.append)

    worker.run_rollback(make_app(uid="a"))

    assert orch.rollback_calls == 1
    assert finished[0].op == "rollback"
    assert len(finished[0].items) == 1


def test_confirm_kill_returns_response(worker, qtbot):
    # 模拟 UI 槽：收到 ask_kill 后回填 True
    def ui(name, procs, resp):
        assert name == "Foo"
        resp.value = True

    worker.ask_kill.connect(ui)
    assert worker._confirm_kill("Foo", [object()]) is True


def test_confirm_kill_cancel(worker, qtbot):
    worker.ask_kill.connect(lambda name, procs, resp: setattr(resp, "value", False))
    assert worker._confirm_kill("Foo", []) is False


def test_choose_asset_returns_selection(worker, qtbot):
    asset = Asset(name="a.zip", download_url="http://x/a.zip", size=1, sha256=None)

    def ui(assets, resp):
        resp.value = assets[0]

    worker.ask_asset.connect(ui)
    assert worker._choose_asset([asset]) is asset


def test_choose_asset_cancel_returns_none(worker, qtbot):
    worker.ask_asset.connect(lambda assets, resp: setattr(resp, "value", None))
    assert worker._choose_asset([]) is None


def test_request_cancel_sets_token(worker):
    token = worker._fresh_cancel()
    assert not token.cancelled
    worker.request_cancel()
    assert token.cancelled
