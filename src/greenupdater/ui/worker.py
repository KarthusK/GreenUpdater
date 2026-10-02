"""更新 worker 与回调桥（对应 docs/design/03-ui.md §10、§13）。

- ``UpdateWorker(QObject)``：moveToThread 后在 worker 线程跑 orchestrator，全部输出走信号
- ``_QtListener``：把领域 ``UpdateListener`` 回调转成 worker 的 Qt 信号（队列连接自动跨线程）
- ``confirm_kill`` / ``choose_asset``：worker 中是**同步**语义，用 ``BlockingQueuedConnection``
  发信号给 UI 弹模态框，UI 把结果写进 ``_Response``，emit 返回后 worker 读取——因此必须
  worker 与 UI 分处不同线程（本设计满足）。

线程安全：worker **不**把可变 ``App`` 跨线程传给 UI，只发 ``sig_app_changed(uid)``，
UI 侧在主线程用 ``repo.get_app(uid)`` 重新读取，避免读写竞态。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from greenupdater.domain import Asset, CancelToken, UpdateListener
from greenupdater.models import App
from greenupdater.service import UpdateOrchestrator


@dataclass
class BatchReport:
    """一批操作的结果，供 UI 汇总状态栏。"""

    op: str  # "check" | "update" | "rollback"
    items: list = field(default_factory=list)


class _Response:
    """跨 BlockingQueuedConnection 回传值的容器。"""

    def __init__(self) -> None:
        self.value = None


class _QtListener:
    """领域 UpdateListener → worker 信号。每个 app 一个实例（绑定 uid）。"""

    def __init__(self, worker: "UpdateWorker", uid: str) -> None:
        self._w = worker
        self._uid = uid

    def on_log(self, line: str) -> None:
        self._w.sig_log.emit(line)

    def on_progress(self, p) -> None:
        self._w.sig_progress.emit(self._uid, p.message, p.percent)

    def on_stage(self, s) -> None:
        # 阶段结束即让 UI 重新读取该行状态（orchestrator 已 save_state）
        self._w.sig_app_changed.emit(self._uid)

    def on_cancelled(self) -> None:
        self._w.sig_app_changed.emit(self._uid)


class UpdateWorker(QObject):
    # ---------- 输出信号（队列连接到 UI 线程）----------
    sig_log = Signal(str)
    sig_progress = Signal(str, str, int)  # uid, message, percent(-1=不定)
    sig_app_changed = Signal(str)  # uid：UI 应 repo.get_app(uid) 后刷新该行
    sig_finished = Signal(object)  # BatchReport

    # ---------- 阻塞式用户决策（BlockingQueuedConnection）----------
    ask_kill = Signal(str, object, object)  # app_name, procs, _Response
    ask_asset = Signal(object, object)  # assets, _Response

    def __init__(self, orchestrator: UpdateOrchestrator, parent=None) -> None:
        super().__init__(parent)
        self._orch = orchestrator
        self._cancel = CancelToken()

    # ---------- 取消（UI 线程可直接调用：仅设置线程安全 Event）----------
    def request_cancel(self) -> None:
        self._cancel.cancel()

    def _fresh_cancel(self) -> CancelToken:
        self._cancel = CancelToken()
        return self._cancel

    # ---------- 阻塞决策回调 ----------
    def _confirm_kill(self, app_name: str, procs: list) -> bool:
        resp = _Response()
        self.ask_kill.emit(app_name, procs, resp)  # 阻塞直到 UI 槽返回
        return bool(resp.value)

    def _choose_asset(self, assets: "list[Asset]") -> "Asset | None":
        resp = _Response()
        self.ask_asset.emit(assets, resp)
        return resp.value

    # ---------- 批处理槽（在 worker 线程执行）----------
    def run_check(self, apps: "list[App]") -> None:
        cancel = self._fresh_cancel()
        results = []
        for app in apps:
            if cancel.cancelled:
                break
            listener = _QtListener(self, app.uid)
            results.append(self._orch.check(app, listener))
            self.sig_app_changed.emit(app.uid)
        self.sig_finished.emit(BatchReport("check", results))

    def run_update(self, apps: "list[App]") -> None:
        cancel = self._fresh_cancel()
        outcomes = []
        for app in apps:
            if cancel.cancelled:
                self.sig_log.emit("[跳过] 已取消，剩余软件不再处理")
                break
            listener = _QtListener(self, app.uid)
            outcome = self._orch.update(
                app,
                listener,
                cancel,
                lambda procs, _name=app.name: self._confirm_kill(_name, procs),
                self._choose_asset,
            )
            self.sig_app_changed.emit(app.uid)
            outcomes.append(outcome)
        self.sig_finished.emit(BatchReport("update", outcomes))

    def run_rollback(self, app: "App") -> None:
        self._fresh_cancel()
        listener = _QtListener(self, app.uid)
        outcome = self._orch.rollback(app, listener)
        self.sig_app_changed.emit(app.uid)
        self.sig_finished.emit(BatchReport("rollback", [outcome]))
