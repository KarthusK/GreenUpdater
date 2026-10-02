"""软件列表表格模型（对应 docs/design/03-ui.md §2、§13）。

- 第 0 列为瞬时勾选复选框（不持久化），默认全选；``enabled=False`` 的行灰显、不可勾选
- 状态列带颜色圆点（DecorationRole）+ 文案；失败附阶段；rollback_available 加"可回滚"
- 纯视图数据，改动业务由 MainWindow 抛信号交给 controller
"""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from greenupdater.models import App, AppStatus, UpdateStage

# 列索引
COL_CHECK = 0
COL_NAME = 1
COL_CURRENT = 2
COL_LATEST = 3
COL_STATUS = 4
COLUMN_COUNT = 5

_HEADERS = ["", "名称", "当前版本", "最新版本", "状态"]

# 状态 → (中文文案, 颜色)
_STATUS_STYLE: dict[AppStatus, tuple[str, str]] = {
    AppStatus.UNKNOWN: ("未检查", "#9e9e9e"),
    AppStatus.UP_TO_DATE: ("已最新", "#2e7d32"),
    AppStatus.UPDATE_AVAILABLE: ("可更新", "#1565c0"),
    AppStatus.UPDATING: ("更新中…", "#f9a825"),
    AppStatus.SUCCESS: ("更新成功", "#2e7d32"),
    AppStatus.FAILED: ("失败", "#c62828"),
}

_STAGE_ZH: dict[UpdateStage, str] = {
    UpdateStage.CHECK: "检查",
    UpdateStage.DOWNLOAD: "下载",
    UpdateStage.EXTRACT: "解压",
    UpdateStage.KILL_PROCESS: "结束进程",
    UpdateStage.SNAPSHOT: "快照",
    UpdateStage.OVERWRITE: "覆盖",
}

_DISABLED_FG = QColor("#9e9e9e")


def _dot_icon(color: str) -> QIcon:
    pm = QPixmap(12, 12)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 10, 10)
    p.end()
    return QIcon(pm)


_icon_cache: dict[str, QIcon] = {}


def status_text(app: App) -> str:
    text, _ = _STATUS_STYLE.get(app.last_status, ("未检查", "#9e9e9e"))
    if app.last_status == AppStatus.FAILED and app.last_error_stage:
        text = f"失败({_STAGE_ZH.get(app.last_error_stage, app.last_error_stage.value)})"
    if app.rollback_available:
        text += " · 可回滚"
    return text


def status_color(app: App) -> str:
    return _STATUS_STYLE.get(app.last_status, ("", "#9e9e9e"))[1]


class AppTableModel(QAbstractTableModel):
    #: 勾选集合变化（供 MainWindow 刷新工具栏可用性）
    checkStateChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._apps: list[App] = []
        self._checked: dict[str, bool] = {}

    # ---------- 数据装载 ----------
    def set_apps(self, apps: Iterable[App]) -> None:
        """载入 apps 并重置勾选：enabled 的默认全选（勾选态不持久化）。"""
        self.beginResetModel()
        self._apps = list(apps)
        self._checked = {a.uid: bool(a.enabled) for a in self._apps}
        self.endResetModel()
        self.checkStateChanged.emit()

    def update_app(self, app: App) -> None:
        """就地刷新单个 app（运行态变化时），保留其勾选状态。"""
        for i, a in enumerate(self._apps):
            if a.uid == app.uid:
                self._apps[i] = app
                self._checked.setdefault(app.uid, bool(app.enabled))
                idx_tl = self.index(i, 0)
                idx_br = self.index(i, COLUMN_COUNT - 1)
                self.dataChanged.emit(idx_tl, idx_br)
                return

    def app_at(self, row: int) -> App | None:
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def all_apps(self) -> list[App]:
        return list(self._apps)

    # ---------- 勾选 ----------
    def is_checked(self, uid: str) -> bool:
        return self._checked.get(uid, False)

    def set_checked(self, uid: str, checked: bool) -> None:
        if uid in self._checked and self._checked[uid] != checked:
            self._checked[uid] = checked
            self.checkStateChanged.emit()

    def checked_apps(self) -> list[App]:
        return [a for a in self._apps if a.enabled and self._checked.get(a.uid)]

    def set_all_checked(self, checked: bool) -> None:
        changed = False
        for a in self._apps:
            if a.enabled and self._checked.get(a.uid) != checked:
                self._checked[a.uid] = checked
                changed = True
        if changed:
            top = self.index(0, COL_CHECK)
            bottom = self.index(max(0, len(self._apps) - 1), COL_CHECK)
            self.dataChanged.emit(top, bottom)
            self.checkStateChanged.emit()

    def toggle_all(self) -> None:
        # 只要还有未勾选的就全选，否则全不选
        self.set_all_checked(not self.all_enabled_checked())

    def all_enabled_checked(self) -> bool:
        enabled = [a for a in self._apps if a.enabled]
        return bool(enabled) and all(self._checked.get(a.uid) for a in enabled)

    # ---------- QAbstractTableModel ----------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._apps)

    def columnCount(self, parent=QModelIndex()) -> int:
        return COLUMN_COUNT

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        app = self._apps[index.row()]
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == COL_CHECK and app.enabled:
            base |= Qt.ItemIsUserCheckable
        return base

    def data(self, index: QModelIndex, role=Qt.ItemDataRole):
        if not index.isValid():
            return None
        app = self._apps[index.row()]
        col = index.column()

        if col == COL_CHECK:
            if role == Qt.CheckStateRole:
                if not app.enabled:
                    return None
                return Qt.Checked if self._checked.get(app.uid) else Qt.Unchecked
            return None

        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return app.name + ("" if app.enabled else "（已停用）")
            if col == COL_CURRENT:
                return app.current_version or "—"
            if col == COL_LATEST:
                return app.latest_version or "—"
            if col == COL_STATUS:
                return status_text(app)

        if col == COL_STATUS:
            if role == Qt.DecorationRole:
                color = status_color(app)
                if color not in _icon_cache:
                    _icon_cache[color] = _dot_icon(color)
                return _icon_cache[color]
            if role == Qt.ToolTipRole and app.last_error_message:
                return app.last_error_message

        if role == Qt.ForegroundRole and not app.enabled:
            return _DISABLED_FG

        if role == Qt.ToolTipRole and col == COL_STATUS and app.last_error_message:
            return app.last_error_message

        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole) -> bool:
        if (
            index.isValid()
            and index.column() == COL_CHECK
            and role == Qt.CheckStateRole
        ):
            app = self._apps[index.row()]
            if not app.enabled:
                return False
            self.set_checked(app.uid, value == Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        return False
