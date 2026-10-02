"""ui.main_window 测试（pytest-qt）：布局、勾选/选择语义、busy、进度、信号。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from greenupdater.infra import ConfigRepository
from greenupdater.models import AppConfig
from greenupdater.ui.main_window import MainWindow


@pytest.fixture()
def repo(tmp_path: Path):
    r = ConfigRepository(tmp_path / "t.db")
    r.upsert_app(
        AppConfig(
            name="Alpha",
            repo_owner="o",
            repo_name="r",
            asset_pattern=r".*\.zip",
            target_dir=tmp_path / "alpha",
        )
    )
    r.upsert_app(
        AppConfig(
            name="Beta",
            repo_owner="o",
            repo_name="r2",
            asset_pattern=r".*\.zip",
            target_dir=tmp_path / "beta",
        )
    )
    yield r
    r.close()


@pytest.fixture()
def win(qtbot, repo):
    w = MainWindow(repo)
    qtbot.addWidget(w)
    return w


def test_rows_loaded(win):
    assert win._model.rowCount() == 2
    assert win.table.model() is not None


def test_default_all_checked(win):
    assert len(win.checked_apps()) == 2


def test_current_app_after_select(win):
    win.table.selectRow(0)
    app = win.current_app()
    assert app is not None
    assert app.name in ("Alpha", "Beta")


def test_set_busy_toggles_progress_and_toolbar(win):
    win.set_busy(True)
    assert win.progress_box.isVisibleTo(win) is True
    assert win.act_add.isEnabled() is False
    assert win.act_check.isEnabled() is False
    assert win.btn_cancel.isEnabled() is True
    win.set_busy(False)
    assert win.progress_box.isVisibleTo(win) is False
    assert win.act_add.isEnabled() is True


def test_check_update_disabled_when_no_checked(win):
    win._model.set_all_checked(False)
    win._update_actions()
    assert win.act_check.isEnabled() is False
    assert win.act_update.isEnabled() is False
    win._model.set_all_checked(True)
    win._update_actions()
    assert win.act_check.isEnabled() is True


def test_set_progress_determinate(win):
    win.set_busy(True)
    win.set_progress("下载中", 45)
    assert win.progress_bar.value() == 45
    assert win.progress_label.text() == "下载中"


def test_set_progress_indeterminate(win):
    win.set_busy(True)
    win.set_progress("检查中", -1)
    assert win.progress_bar.maximum() == 0


def test_append_log(win):
    win.append_log("测试日志行")
    assert "测试日志行" in win.terminal.toPlainText()


def test_edit_signal_emits_uid(win, qtbot):
    win.table.selectRow(0)
    uid = win.current_app().uid
    with qtbot.waitSignal(win.editRequested, timeout=1000) as blocker:
        win._on_edit()
    assert blocker.args == [uid]


def test_rollback_disabled_without_flag(win):
    win.table.selectRow(0)
    win._update_actions()
    assert win.act_rollback.isEnabled() is False


def test_header_click_toggles_all(win):
    win._on_header_clicked(0)  # 点击勾选列表头
    assert win.checked_apps() == []
    win._on_header_clicked(0)
    assert len(win.checked_apps()) == 2


def test_statusbar_counts(win):
    win._update_statusbar()
    msg = win.statusBar().currentMessage()
    assert "共 2 项" in msg
    assert "勾选 2 项" in msg


def test_refresh_reloads(win, repo, tmp_path):
    repo.upsert_app(
        AppConfig(
            name="Gamma",
            repo_owner="o",
            repo_name="r3",
            asset_pattern=r".*\.zip",
            target_dir=tmp_path / "gamma",
        )
    )
    win.refresh()
    assert win._model.rowCount() == 3


def test_clear_log_button_empties_terminal(win, qtbot):
    win.append_log("hello")
    win.append_log("world")
    assert win.terminal.toPlainText() != ""
    qtbot.mouseClick(win.btn_clear_log, Qt.LeftButton)
    assert win.terminal.toPlainText() == ""
