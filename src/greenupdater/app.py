"""装配根 / 控制器（对应 docs/design/03-ui.md §9/§10、04-structure.md）。

把各层拼起来并连接信号：
- 构建 Paths / 日志 / ConfigRepository / TokenStore / UpdateOrchestrator
- UpdateWorker 移入 QThread；MainWindow 的 intent 信号 → 控制器槽 → worker（队列）
- worker 的输出信号 → UI；ask_kill / ask_asset 用 BlockingQueuedConnection 弹模态框
- 单实例守卫；首次运行初始化便携目录

MainWindow 只做展示，一切写操作集中在此，避免视图层触碰业务。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from greenupdater.domain import (
    BackupManager,
    Downloader,
    Extractor,
    GitHubProvider,
    LocalVersionDetector,
    Overwriter,
    ProcessManager,
    VersionResolver,
)
from greenupdater.infra import (
    ConfigRepository,
    Paths,
    TokenStore,
    setup_logging,
)
from greenupdater.service import UpdateOrchestrator
from greenupdater.ui.dialogs import (
    AppEditDialog,
    ChooseAssetDialog,
    ConfirmKillDialog,
    HistoryDialog,
    SettingsDialog,
)
from greenupdater.ui.main_window import MainWindow
from greenupdater.ui.single_instance import SingleInstance, activate_main_window
from greenupdater.ui.theme import app_icon, apply_dark_theme
from greenupdater.ui.worker import BatchReport, UpdateWorker

#: 进度刷新最小间隔（秒），配合百分比变化节流，避免重绘抖动
_PROGRESS_MIN_INTERVAL = 0.1


class Controller(QObject):
    """连接 MainWindow ↔ UpdateWorker，承载所有业务动作。"""

    # 跨线程调用 worker 槽（自动队列连接）
    _invoke_check = Signal(list)
    _invoke_update = Signal(list)
    _invoke_rollback = Signal(object)

    def __init__(self, paths: Paths | None = None) -> None:
        super().__init__()
        self.paths = paths or Paths()
        self.paths.ensure_dirs()

        self.repo = ConfigRepository(self.paths.db_path)
        self.tokens = TokenStore()

        settings = self.repo.get_settings()
        setup_logging(self.paths.log_file, level=settings.log_level)

        self._proxy = settings.proxy_url if settings.proxy_enabled else None
        self._orchestrator = self._build_orchestrator(self._proxy)

        # 线程与 worker
        self._thread = QThread(self)
        self._worker = UpdateWorker(self._orchestrator)
        self._worker.moveToThread(self._thread)

        self.window = MainWindow(self.repo)

        self._last_progress_ts = 0.0
        self._last_progress_pct: int | None = None

        self._connect_worker()
        self._connect_window()

    # ---------- 构建 ----------
    def _build_orchestrator(self, proxy: str | None) -> UpdateOrchestrator:
        provider = GitHubProvider(proxy=proxy)
        downloader = Downloader(proxy=proxy)
        return UpdateOrchestrator(
            repo=self.repo,
            provider=provider,
            resolver=VersionResolver(),
            detector=LocalVersionDetector(),
            downloader=downloader,
            extractor=Extractor(),
            procmgr=ProcessManager(),
            backup=BackupManager(self.paths),
            overwriter=Overwriter(),
            tokens=self.tokens,
            paths=self.paths,
        )

    def _connect_worker(self) -> None:
        w = self._worker
        w.sig_log.connect(self.window.append_log)
        w.sig_progress.connect(self._on_progress)
        w.sig_app_changed.connect(self._on_app_changed)
        w.sig_finished.connect(self._on_finished)
        # 阻塞式用户决策：worker 在子线程，槽在主线程弹模态框
        w.ask_kill.connect(self._on_ask_kill, Qt.BlockingQueuedConnection)
        w.ask_asset.connect(self._on_ask_asset, Qt.BlockingQueuedConnection)

        self._invoke_check.connect(w.run_check)
        self._invoke_update.connect(w.run_update)
        self._invoke_rollback.connect(w.run_rollback)

    def _connect_window(self) -> None:
        win = self.window
        win.addRequested.connect(self._on_add)
        win.editRequested.connect(self._on_edit)
        win.deleteRequested.connect(self._on_delete)
        win.checkRequested.connect(self._on_check)
        win.updateRequested.connect(self._on_update)
        win.rollbackRequested.connect(self._on_rollback)
        win.importRequested.connect(self._on_import)
        win.exportRequested.connect(self._on_export)
        win.settingsRequested.connect(self._on_settings)
        win.historyRequested.connect(self._on_history)
        win.openDirRequested.connect(self._on_open_dir)
        win.cancelRequested.connect(self._worker.request_cancel)

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._thread.start()
        self.window.show()

    def shutdown(self) -> None:
        self._worker.request_cancel()
        self._thread.quit()
        self._thread.wait(3000)
        self.repo.close()

    # ---------- 批量动作 ----------
    def _on_check(self) -> None:
        apps = self.window.checked_apps()
        if not apps:
            return
        self._begin_batch("检查")
        self._invoke_check.emit(apps)

    def _on_update(self) -> None:
        apps = self.window.checked_apps()
        if not apps:
            return
        self._begin_batch("更新")
        self._invoke_update.emit(apps)

    def _on_rollback(self, uid: str) -> None:
        app = self.repo.get_app(uid)
        if app is None:
            return
        ok = QMessageBox.question(
            self.window,
            "回滚",
            f"确定将「{app.name}」回滚到更新前的快照？当前文件会被覆盖（保留排除路径）。",
        )
        if ok != QMessageBox.Yes:
            return
        self._begin_batch("回滚")
        self._invoke_rollback.emit(app)

    def _begin_batch(self, label: str) -> None:
        self._last_progress_pct = None
        self._last_progress_ts = 0.0
        self.window.set_busy(True)
        self.window.set_progress(f"{label}中…", -1)

    # ---------- worker 输出槽 ----------
    def _on_progress(self, uid: str, message: str, percent: int) -> None:
        now = time.monotonic()
        if (
            percent == self._last_progress_pct
            and now - self._last_progress_ts < _PROGRESS_MIN_INTERVAL
        ):
            return
        self._last_progress_pct = percent
        self._last_progress_ts = now
        self.window.set_progress(message, percent)

    def _on_app_changed(self, uid: str) -> None:
        app = self.repo.get_app(uid)  # 主线程重读，避免跨线程共享可变对象
        if app is not None:
            self.window.update_app(app)

    def _on_finished(self, report: BatchReport) -> None:
        self.window.set_busy(False)
        self._summarize(report)

    def _summarize(self, report: BatchReport) -> None:
        items = report.items
        if report.op == "check":
            avail = sum(1 for r in items if getattr(r, "update_available", False))
            failed = sum(1 for r in items if getattr(r, "error", None))
            self.window.append_log(f"[完成] 检查 {len(items)} 项，{avail} 项可更新，{failed} 项出错")
        elif report.op == "update":
            ok = sum(1 for o in items if str(getattr(o, "result", "")) == "success")
            failed = sum(1 for o in items if str(getattr(o, "result", "")) == "failed")
            cancelled = sum(1 for o in items if str(getattr(o, "result", "")) == "cancelled")
            msg = f"[完成] 更新 {ok} 成功 / {failed} 失败"
            if cancelled:
                msg += f" / {cancelled} 取消"
            self.window.append_log(msg)
        else:  # rollback
            self.window.append_log(f"[完成] 回滚 {len(items)} 项")

    def _on_ask_kill(self, app_name: str, procs: list, resp) -> None:
        dlg = ConfirmKillDialog(app_name, procs, self.window)
        resp.value = dlg.exec() == ConfirmKillDialog.Accepted

    def _on_ask_asset(self, assets: list, resp) -> None:
        dlg = ChooseAssetDialog(assets, self.window)
        if dlg.exec() == ChooseAssetDialog.Accepted:
            resp.value = dlg.selected_asset()
        else:
            resp.value = None

    # ---------- 单条 CRUD ----------
    def _on_add(self) -> None:
        dlg = AppEditDialog(None, self.window)
        if dlg.exec() != AppEditDialog.Accepted:
            return
        cfg = dlg.get_config()
        if cfg is None:
            return
        app = self.repo.upsert_app(cfg)
        self._apply_local_version(app, dlg)
        self.window.refresh()

    def _on_edit(self, uid: str) -> None:
        app = self.repo.get_app(uid)
        if app is None:
            return
        dlg = AppEditDialog(app, self.window)
        if dlg.exec() != AppEditDialog.Accepted:
            return
        cfg = dlg.get_config()
        if cfg is None:
            return
        updated = self.repo.upsert_app(cfg, uid=uid)
        self._apply_local_version(updated, dlg)
        self.window.refresh()

    def _apply_local_version(self, app, dlg: AppEditDialog) -> None:
        version, src = dlg.get_local_version()
        if version is None and app.current_version is None:
            return
        app.current_version = version
        app.current_version_src = src
        self.repo.save_state(app)

    def _on_delete(self, uid: str) -> None:
        app = self.repo.get_app(uid)
        if app is None:
            return
        ok = QMessageBox.question(
            self.window,
            "删除",
            f"从列表移除「{app.name}」？\n（不会删除目标目录中的文件）",
        )
        if ok != QMessageBox.Yes:
            return
        self.repo.delete_app(uid)
        self.window.refresh()

    def _on_history(self, uid: str) -> None:
        app = self.repo.get_app(uid)
        if app is None:
            return
        records = self.repo.list_history(uid)
        HistoryDialog(app.name, records, self.window).exec()

    def _on_open_dir(self, uid: str) -> None:
        app = self.repo.get_app(uid)
        if app is None:
            return
        _open_path(app.target_dir)

    # ---------- 导入 / 导出 / 设置 ----------
    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.window, "导出配置", "greenupdater-export.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = self.repo.export_json()
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self.window, "导出失败", str(exc))
            return
        self.window.append_log(f"[导出] 已写入 {path}")

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "导入配置", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self.window, "导入失败", str(exc))
            return
        report = self.repo.import_json(data)
        self.window.refresh()
        self.window.append_log(
            f"[导入] 新增 {report.created}，更新 {report.updated}，错误 {len(report.errors)}"
        )
        if report.errors:
            QMessageBox.warning(self.window, "导入完成（含错误）", "\n".join(report.errors[:10]))

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.repo, self.paths, self.tokens, self.window)
        if dlg.exec() != SettingsDialog.Accepted:
            return
        settings = self.repo.get_settings()
        # 日志级别即时生效
        setup_logging(self.paths.log_file, level=settings.log_level)
        # 代理变化 → 重建 orchestrator 与 worker
        new_proxy = settings.proxy_url if settings.proxy_enabled else None
        if new_proxy != self._proxy:
            self._proxy = new_proxy
            self._rebuild_worker(new_proxy)

    def _rebuild_worker(self, proxy: str | None) -> None:
        self._thread.quit()
        self._thread.wait(3000)
        self._orchestrator = self._build_orchestrator(proxy)
        self._worker = UpdateWorker(self._orchestrator)
        self._worker.moveToThread(self._thread)
        self._connect_worker()
        self._thread.start()


def _open_path(path) -> None:
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", p])  # noqa: S603,S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", p])  # noqa: S603,S607
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setApplicationName("GreenUpdater")
    app.setQuitOnLastWindowClosed(True)
    app.setWindowIcon(app_icon())
    apply_dark_theme(app)

    guard = SingleInstance()
    if not guard.is_primary:
        # 已有实例：请求激活后退出
        return 0

    controller = Controller()
    guard.on_activate = lambda: activate_main_window(controller.window)
    controller.start()

    try:
        code = app.exec()
    finally:
        controller.shutdown()
        guard.cleanup()
    return code
