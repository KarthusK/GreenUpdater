"""ui.models.app_table_model 测试（pytest-qt）。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from greenupdater.models import App, AppConfig, AppStatus, UpdateStage
from greenupdater.ui.models.app_table_model import (
    COL_CHECK,
    COL_CURRENT,
    COL_LATEST,
    COL_NAME,
    COL_STATUS,
    AppTableModel,
    status_text,
)


def make_app(**kw) -> App:
    base = dict(
        id=1,
        name="App",
        repo_owner="o",
        repo_name="r",
        asset_pattern=r".*\.zip",
        target_dir=Path("D:/x"),
    )
    base.update(kw)
    return App(**base)


@pytest.fixture()
def model(qtbot):
    return AppTableModel()


def test_set_apps_defaults_all_checked(model):
    model.set_apps([make_app(name="A"), make_app(name="B")])
    assert model.rowCount() == 2
    assert len(model.checked_apps()) == 2


def test_disabled_app_not_checked_nor_checkable(model):
    a = make_app(name="A")
    b = make_app(name="B", enabled=False)
    model.set_apps([a, b])
    assert model.is_checked(a.uid) is True
    assert model.is_checked(b.uid) is False
    assert b.uid not in [x.uid for x in model.checked_apps()]
    # 不可勾选
    idx = model.index(1, COL_CHECK)
    assert not (model.flags(idx) & Qt.ItemIsUserCheckable)
    assert model.data(idx, Qt.CheckStateRole) is None


def test_setdata_toggles_and_emits(model, qtbot):
    a = make_app(name="A")
    model.set_apps([a])
    idx = model.index(0, COL_CHECK)
    with qtbot.waitSignal(model.checkStateChanged, timeout=1000):
        assert model.setData(idx, Qt.Unchecked, Qt.CheckStateRole) is True
    assert model.is_checked(a.uid) is False
    assert model.checked_apps() == []


def test_toggle_all(model):
    model.set_apps([make_app(name="A"), make_app(name="B")])
    model.toggle_all()  # 全勾选 → 全不选
    assert model.checked_apps() == []
    model.toggle_all()  # → 全选
    assert len(model.checked_apps()) == 2


def test_display_roles(model):
    a = make_app(name="LibreWolf", current_version=None, latest_version="2.0")
    model.set_apps([a])
    assert model.data(model.index(0, COL_NAME), Qt.DisplayRole) == "LibreWolf"
    assert model.data(model.index(0, COL_CURRENT), Qt.DisplayRole) == "—"
    assert model.data(model.index(0, COL_LATEST), Qt.DisplayRole) == "2.0"


def test_disabled_name_suffix(model):
    a = make_app(name="X", enabled=False)
    model.set_apps([a])
    assert model.data(model.index(0, COL_NAME), Qt.DisplayRole) == "X（已停用）"


def test_update_app_preserves_check(model):
    a = make_app(name="A")
    model.set_apps([a])
    model.set_checked(a.uid, False)
    a2 = a.model_copy(update={"latest_version": "9.9", "last_status": AppStatus.UPDATE_AVAILABLE})
    model.update_app(a2)
    assert model.is_checked(a.uid) is False  # 勾选保留
    assert model.data(model.index(0, COL_LATEST), Qt.DisplayRole) == "9.9"


@pytest.mark.parametrize(
    "status,stage,rollback,expected",
    [
        (AppStatus.UNKNOWN, None, False, "未检查"),
        (AppStatus.UP_TO_DATE, None, False, "已最新"),
        (AppStatus.UPDATE_AVAILABLE, None, False, "可更新"),
        (AppStatus.FAILED, UpdateStage.OVERWRITE, False, "失败(覆盖)"),
        (AppStatus.FAILED, UpdateStage.OVERWRITE, True, "失败(覆盖) · 可回滚"),
        (AppStatus.SUCCESS, None, True, "更新成功 · 可回滚"),
    ],
)
def test_status_text(status, stage, rollback, expected):
    app = make_app(last_status=status, last_error_stage=stage, rollback_available=rollback)
    assert status_text(app) == expected


def test_status_decoration_and_tooltip(model):
    a = make_app(
        last_status=AppStatus.FAILED,
        last_error_stage=UpdateStage.DOWNLOAD,
        last_error_message="网络错误",
    )
    model.set_apps([a])
    idx = model.index(0, COL_STATUS)
    assert model.data(idx, Qt.DecorationRole) is not None  # 颜色圆点
    assert model.data(idx, Qt.ToolTipRole) == "网络错误"
