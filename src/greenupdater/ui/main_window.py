"""主窗口（对应 docs/design/03-ui.md §1/§2/§3/§9/§10）。

纯视图层：负责布局、勾选/选择语义、状态呈现、终端与进度显示；所有业务动作以
**intent 信号**抛出，由 controller（worker + 对话框，后续步骤）连接执行并回调 refresh()。
MainWindow 只从 repo **读**数据用于展示，不做任何写操作。
"""
from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from greenupdater.infra import ConfigRepository
from greenupdater.models import App, AppStatus
from greenupdater.ui import theme
from greenupdater.ui.models import AppTableModel
from greenupdater.ui.models.app_table_model import COL_CHECK
from greenupdater.ui.widgets import TerminalView


class MainWindow(QMainWindow):
    # ---------- intent 信号（controller 连接）----------
    addRequested = Signal()
    editRequested = Signal(str)  # uid
    deleteRequested = Signal(str)  # uid
    checkRequested = Signal()  # 作用于勾选行
    updateRequested = Signal()  # 作用于勾选行
    rollbackRequested = Signal(str)  # uid
    importRequested = Signal()
    exportRequested = Signal()
    settingsRequested = Signal()
    historyRequested = Signal(str)  # uid
    openDirRequested = Signal(str)  # uid
    cancelRequested = Signal()

    def __init__(self, repo: ConfigRepository, parent=None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._busy = False

        self.setWindowTitle("GreenUpdater 绿色更新器")
        self.resize(1000, 700)

        self._model = AppTableModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.DisplayRole)

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._connect_signals()

        self.refresh()
        self._update_actions()

    # =====================================================================
    # 构建
    # =====================================================================
    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        def act(text, slot, shortcut=None, tip=None, icon_name=None, icon_color=None) -> QAction:
            a = QAction(text, self)
            if icon_name:
                a.setIcon(theme.icon(icon_name, color=icon_color or theme.ICON))
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setToolTip(tip)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        self.act_add = act("添加", self.addRequested.emit, "Ctrl+N", icon_name="add")
        self.act_edit = act("编辑", self._on_edit, "Ctrl+E", icon_name="edit")
        self.act_delete = act("删除", self._on_delete, "Del", icon_name="delete")
        tb.addSeparator()
        self.act_check = act(
            "检查", self._on_check, "F5", "检查勾选的软件", icon_name="refresh"
        )
        self.act_update = act(
            "更新", self._on_update, "Ctrl+U", "更新勾选的软件",
            icon_name="download", icon_color=theme.ACCENT,
        )
        self.act_rollback = act(
            "回滚", self._on_rollback, tip="回滚当前选中项", icon_name="undo"
        )
        tb.addSeparator()
        self.act_import = act("导入", self.importRequested.emit, icon_name="import")
        self.act_export = act("导出", self.exportRequested.emit, icon_name="export")
        tb.addSeparator()
        self.act_settings = act("设置", self.settingsRequested.emit, icon_name="settings")

    def _build_central(self) -> None:
        self.table = QTableView(self)
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        self.table.setColumnWidth(COL_CHECK, 36)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)

        # 进度区
        self.progress_box = QWidget(self)
        self.progress_box.setObjectName("progressBox")
        pl = QHBoxLayout(self.progress_box)
        pl.setContentsMargins(10, 6, 10, 6)
        self.progress_label = QLabel("就绪", self.progress_box)
        self.progress_bar = QProgressBar(self.progress_box)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.btn_cancel = QPushButton("取消", self.progress_box)
        self.btn_cancel.setIcon(theme.icon("close"))
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)
        pl.addWidget(self.progress_label, 1)
        pl.addWidget(self.progress_bar, 2)
        pl.addWidget(self.btn_cancel)
        self.progress_box.setVisible(False)

        self.terminal = TerminalView(self)
        self.terminal.setObjectName("terminal")

        # 终端标题栏（含清屏）
        self.terminal_bar = QWidget(self)
        self.terminal_bar.setObjectName("terminalBar")
        tbl = QHBoxLayout(self.terminal_bar)
        tbl.setContentsMargins(10, 5, 8, 5)
        tbl.addWidget(QLabel("终端", self.terminal_bar))
        tbl.addStretch(1)
        self.btn_clear_log = QPushButton("清屏", self.terminal_bar)
        self.btn_clear_log.clicked.connect(self.terminal.clear_log)
        tbl.addWidget(self.btn_clear_log)

        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.progress_box)
        rl.addWidget(self.terminal_bar)
        rl.addWidget(self.terminal, 1)

        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        central = QWidget(self)
        cl = QVBoxLayout(central)
        cl.setContentsMargins(10, 6, 10, 6)
        cl.setSpacing(0)
        cl.addWidget(self.splitter)
        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        self.statusBar().showMessage("就绪")

    def _connect_signals(self) -> None:
        self._model.checkStateChanged.connect(self._update_actions)
        self._model.checkStateChanged.connect(self._update_statusbar)
        sel = self.table.selectionModel()
        sel.currentRowChanged.connect(lambda *_: self._update_actions())
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        # 点击勾选列表头 = 全选/全不选
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    # =====================================================================
    # 对外接口（controller 调用）
    # =====================================================================
    def refresh(self) -> None:
        """从 repo 重新载入列表（保留当前勾选集合的并集语义：重载后默认全选）。"""
        self._model.set_apps(self._repo.list_apps())
        self._update_statusbar()
        self._update_actions()

    def update_app(self, app: App) -> None:
        """运行态变化时只刷新单行，避免整表重载丢失勾选。"""
        self._model.update_app(app)
        self._update_statusbar()
        self._update_actions()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress_box.setVisible(busy)
        self.btn_cancel.setEnabled(busy)
        if not busy:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_label.setText("就绪")
        self._update_actions()

    def set_progress(self, text: str, percent: int) -> None:
        self.progress_label.setText(text)
        if percent < 0:
            self.progress_bar.setRange(0, 0)  # indeterminate
        else:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, percent)))

    def append_log(self, line: str) -> None:
        self.terminal.append_line(line)

    def append_logs(self, lines: list[str]) -> None:
        self.terminal.append_lines(lines)

    def checked_apps(self) -> list[App]:
        return self._model.checked_apps()

    def current_app(self) -> App | None:
        idx = self.table.selectionModel().currentIndex()
        if not idx.isValid():
            return None
        return self._model.app_at(self._proxy.mapToSource(idx).row())

    # =====================================================================
    # 内部槽
    # =====================================================================
    def _on_header_clicked(self, section: int) -> None:
        if section == COL_CHECK:
            self._model.toggle_all()

    def _on_edit(self) -> None:
        app = self.current_app()
        if app:
            self.editRequested.emit(app.uid)

    def _on_delete(self) -> None:
        app = self.current_app()
        if app:
            self.deleteRequested.emit(app.uid)

    def _on_check(self) -> None:
        if self._model.checked_apps():
            self.checkRequested.emit()

    def _on_update(self) -> None:
        if self._model.checked_apps():
            self.updateRequested.emit()

    def _on_rollback(self) -> None:
        app = self.current_app()
        if app and app.rollback_available:
            self.rollbackRequested.emit(app.uid)

    def _on_history(self) -> None:
        app = self.current_app()
        if app:
            self.historyRequested.emit(app.uid)

    def _on_open_dir(self) -> None:
        app = self.current_app()
        if app:
            self.openDirRequested.emit(app.uid)

    def _show_context_menu(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        src_row = self._proxy.mapToSource(idx).row()
        app = self._model.app_at(src_row)
        if app is None:
            return
        menu = QMenu(self)
        a_edit = menu.addAction("编辑…")
        a_del = menu.addAction("删除")
        menu.addSeparator()
        a_check = menu.addAction("检查更新")
        a_upd = menu.addAction("更新")
        a_rb = menu.addAction("回滚到此版本")
        a_rb.setEnabled(app.rollback_available and not self._busy)
        menu.addSeparator()
        a_open = menu.addAction("打开目标目录")
        a_hist = menu.addAction("查看更新历史…")

        a_edit.setEnabled(not self._busy)
        a_del.setEnabled(not self._busy)
        a_check.setEnabled(not self._busy and app.enabled)
        a_upd.setEnabled(not self._busy and app.enabled)

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is a_edit:
            self.editRequested.emit(app.uid)
        elif chosen is a_del:
            self.deleteRequested.emit(app.uid)
        elif chosen is a_check:
            self.checkRequested.emit()
        elif chosen is a_upd:
            self.updateRequested.emit()
        elif chosen is a_rb:
            self.rollbackRequested.emit(app.uid)
        elif chosen is a_open:
            self.openDirRequested.emit(app.uid)
        elif chosen is a_hist:
            self.historyRequested.emit(app.uid)

    # ---------- 可用性 / 状态栏 ----------
    def _update_actions(self) -> None:
        has_cur = self.current_app() is not None
        cur = self.current_app()
        n_checked = len(self._model.checked_apps())
        idle = not self._busy

        self.act_add.setEnabled(idle)
        self.act_import.setEnabled(idle)
        self.act_export.setEnabled(idle)
        self.act_settings.setEnabled(idle)

        self.act_edit.setEnabled(idle and has_cur)
        self.act_delete.setEnabled(idle and has_cur)

        self.act_check.setEnabled(idle and n_checked > 0)
        self.act_update.setEnabled(idle and n_checked > 0)
        self.act_rollback.setEnabled(idle and has_cur and bool(cur and cur.rollback_available))

        self.btn_cancel.setEnabled(self._busy)

    def _update_statusbar(self) -> None:
        apps = self._model.all_apps()
        total = len(apps)
        checked = len(self._model.checked_apps())
        avail = sum(1 for a in apps if a.last_status == AppStatus.UPDATE_AVAILABLE)
        if total == 0:
            self.statusBar().showMessage("还没有软件，点击【添加】开始")
        else:
            self.statusBar().showMessage(
                f"共 {total} 项，勾选 {checked} 项，{avail} 项可更新"
            )
