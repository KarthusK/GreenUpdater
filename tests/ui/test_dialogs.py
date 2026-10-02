"""ui.dialogs 测试（pytest-qt）：构造、状态、非阻塞输出。

注意：凡会弹 QMessageBox（模态、阻塞）的分支在测试中一律避开，只验证控件状态与
无副作用的输出路径，防止自动化测试挂起等待用户点击。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as FailKeyring

from greenupdater.domain import Asset
from greenupdater.infra import ConfigRepository, Paths, TokenStore
from greenupdater.models import AppConfig, UpdateRecord, UpdateResult, UpdateStage
from greenupdater.ui.dialogs import (
    AppEditDialog,
    ChooseAssetDialog,
    ConfirmKillDialog,
    HistoryDialog,
    SettingsDialog,
)


class InMemoryBackend(KeyringBackend):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    @property
    def priority(self) -> int:  # type: ignore[override]
        return 1

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


class FakeProc:
    def __init__(self, name: str, pid: int) -> None:
        self._name = name
        self.pid = pid

    def name(self) -> str:
        return self._name


# ---------- ConfirmKillDialog ----------
def test_confirm_kill_lists_procs(qtbot):
    dlg = ConfirmKillDialog("LibreWolf", [FakeProc("librewolf.exe", 1234)])
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "目标程序正在运行"


# ---------- ChooseAssetDialog ----------
def test_choose_asset_selection(qtbot):
    assets = [
        Asset(name="a.zip", download_url="http://x/a.zip", size=10, sha256=None),
        Asset(name="b.zip", download_url="http://x/b.zip", size=20, sha256=None),
    ]
    dlg = ChooseAssetDialog(assets)
    qtbot.addWidget(dlg)
    dlg._list.setCurrentRow(1)
    assert dlg.selected_asset() is assets[1]


def test_choose_asset_none_when_no_selection(qtbot):
    dlg = ChooseAssetDialog([Asset(name="a.zip", download_url="u", size=1, sha256=None)])
    qtbot.addWidget(dlg)
    dlg._list.clearSelection()
    dlg._list.setCurrentRow(-1)
    assert dlg.selected_asset() is None


# ---------- HistoryDialog ----------
def test_history_dialog_rows(qtbot):
    records = [
        UpdateRecord(
            app_id=1,
            from_version="1.0",
            to_version="2.0",
            result=UpdateResult.SUCCESS,
            started_at=datetime.now(timezone.utc),
        ),
        UpdateRecord(
            app_id=1,
            from_version="2.0",
            to_version="3.0",
            result=UpdateResult.FAILED,
            failed_stage=UpdateStage.OVERWRITE,
            error_message="boom",
            started_at=datetime.now(timezone.utc),
        ),
    ]
    dlg = HistoryDialog("LibreWolf", records)
    qtbot.addWidget(dlg)
    from PySide6.QtWidgets import QTableWidget

    table = dlg.findChild(QTableWidget)
    assert table is not None
    assert table.rowCount() == 2


# ---------- SettingsDialog ----------
@pytest.fixture()
def env(tmp_path: Path):
    repo = ConfigRepository(tmp_path / "s.db")
    paths = Paths(tmp_path)
    paths.ensure_dirs()
    yield repo, paths
    repo.close()


def test_settings_token_available_enables_input(qtbot, env):
    repo, paths = env
    tokens = TokenStore(backend=InMemoryBackend())
    dlg = SettingsDialog(repo, paths, tokens)
    qtbot.addWidget(dlg)
    assert dlg.ed_token.isEnabled()


def test_settings_token_unavailable_disables_input(qtbot, env):
    repo, paths = env
    tokens = TokenStore(backend=FailKeyring())
    dlg = SettingsDialog(repo, paths, tokens)
    qtbot.addWidget(dlg)
    assert not dlg.ed_token.isEnabled()


def test_settings_accept_persists(qtbot, env):
    repo, paths = env
    tokens = TokenStore(backend=InMemoryBackend())
    dlg = SettingsDialog(repo, paths, tokens)
    qtbot.addWidget(dlg)

    dlg.chk_proxy.setChecked(True)
    dlg.ed_proxy.setText("http://127.0.0.1:7890")
    dlg.cb_level.setCurrentText("DEBUG")
    dlg.chk_prerelease.setChecked(True)
    dlg._on_accept()

    saved = repo.get_settings()
    assert saved.proxy_enabled is True
    assert saved.proxy_url == "http://127.0.0.1:7890"
    assert saved.log_level == "DEBUG"
    assert saved.default_include_prerelease is True


def test_settings_proxy_toggle_enables_url(qtbot, env):
    repo, paths = env
    tokens = TokenStore(backend=InMemoryBackend())
    dlg = SettingsDialog(repo, paths, tokens)
    qtbot.addWidget(dlg)
    assert not dlg.ed_proxy.isEnabled()
    dlg.chk_proxy.setChecked(True)
    assert dlg.ed_proxy.isEnabled()


# ---------- AppEditDialog ----------
def _fill(dlg: AppEditDialog) -> None:
    dlg.ed_name.setText("Foo")
    dlg.ed_owner.setText("owner")
    dlg.ed_repo.setText("repo")
    dlg.ed_asset_pattern.setText(r".*\.zip")
    dlg.ed_target.setText("D:/foo")


def test_app_edit_accept_builds_config(qtbot):
    dlg = AppEditDialog(None)
    qtbot.addWidget(dlg)
    _fill(dlg)
    dlg._on_accept()
    cfg = dlg.get_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.name == "Foo"
    assert cfg.repo == "owner/repo"


def test_app_edit_local_version_manual(qtbot):
    dlg = AppEditDialog(None)
    qtbot.addWidget(dlg)
    _fill(dlg)
    dlg.ed_local_version.setText("1.2.3")
    dlg._on_accept()
    version, src = dlg.get_local_version()
    assert version == "1.2.3"
