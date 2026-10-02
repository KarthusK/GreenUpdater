"""深色主题（对应 docs/design/03-ui.md）。

颜色令牌集中在本模块，供表格状态色、终端着色等处引用，保证单一出处。
``apply_dark_theme`` = Fusion 风格 + 深色 QPalette（兜底未被 QSS 覆盖的原生绘制）
+ 全局 QSS；Windows 上另挂全局事件过滤器，把所有顶层窗口的系统标题栏切成深色。
图标为内嵌单色线性 SVG，用 PySide6 自带的 QtSvg 渲染，无新增依赖。
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEvent, QByteArray, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

# =====================================================================
# 设计令牌（颜色单一出处）
# =====================================================================
WINDOW_BG = "#1e1f22"  # 窗口底色
SURFACE = "#222428"  # 卡片 / 表头 / 终端标题栏
FIELD_BG = "#26282c"  # 输入框 / 下拉框 / 按钮
BORDER = "#3a3e44"  # 输入类控件边框
BORDER_SUBTLE = "#2e3136"  # 卡片边框 / 分隔线
TEXT = "#e8eaed"  # 主文字
TEXT_SECONDARY = "#9aa0a6"  # 次要文字
TEXT_DISABLED = "#5f6368"  # 禁用文字
PLACEHOLDER = "#6b7075"  # 输入框占位符

ACCENT = "#4ade80"  # 强调绿（品牌色）
ACCENT_HOVER = "#63e894"
ACCENT_PRESSED = "#35c96e"
ACCENT_TEXT = "#10231a"  # 实心绿按钮上的深色文字
SELECT_BG = "rgba(74, 222, 128, 0.16)"  # 选中行 / 菜单项高亮（半透明绿）

STATUS_OK = "#4ade80"  # 已最新 / 更新成功
STATUS_UPDATE = "#64b5f6"  # 可更新
STATUS_BUSY = "#fbbf24"  # 更新中 / 提示
STATUS_FAIL = "#f87171"  # 失败
STATUS_NEUTRAL = "#9aa0a6"  # 未检查 / 跳过 / 取消
STATUS_DISABLED = "#6f7378"  # 停用行
DANGER = "#f87171"  # 警告文字（设置页等）

ICON = "#c3c7cc"  # 工具栏图标默认色
TERMINAL_TEXT = "#c9cdd2"  # 终端正文
TERMINAL_BG = "#17181b"

# =====================================================================
# 内嵌 SVG 图标（Feather/Lucide 风格单色线性图标，24×24 viewBox）
# =====================================================================
_ICON_BODY: dict[str, str] = {
    "add": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "edit": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    "delete": (
        '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>'
    ),
    "refresh": '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    "undo": '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
    "import": (
        '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>'
        '<polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/>'
    ),
    "export": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0'
        'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2'
        'v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0'
        '-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2'
        '-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1'
        ' 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1'
        ' 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0'
        ' 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 '
        '0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
    ),
    "close": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_DPR = 2  # 图标按 2x 物理像素渲染，高分屏不糊
_icon_cache: dict[tuple[str, str, int], QIcon] = {}


def _render_icon(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size * _DPR, size * _DPR)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(_DPR)
    painter = QPainter(pm)
    # 显式目标矩形：否则按 SVG 原生 24×24 渲染，在高倍 pixmap 上只显示局部
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def icon(name: str, color: str = ICON, size: int = 18) -> QIcon:
    """按名称取单色线性图标；悬停变亮、禁用变灰。"""
    key = (name, color, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    body = _ICON_BODY[name]
    ic = QIcon()
    ic.addPixmap(_render_icon(_SVG_TEMPLATE.format(color=color, body=body), size), QIcon.Mode.Normal)
    hover = color if color != ICON else TEXT
    ic.addPixmap(_render_icon(_SVG_TEMPLATE.format(color=hover, body=body), size), QIcon.Mode.Active)
    ic.addPixmap(_render_icon(_SVG_TEMPLATE.format(color=TEXT_DISABLED, body=body), size), QIcon.Mode.Disabled)
    _icon_cache[key] = ic
    return ic


# =====================================================================
# 全局样式表
# =====================================================================
QSS = f"""
/* ===== 全局 ===== */
QWidget {{ color: {TEXT}; font-size: 12px; }}
QMainWindow, QDialog {{ background-color: {WINDOW_BG}; }}
QToolTip {{ background-color: {FIELD_BG}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 4px 8px; border-radius: 4px; }}
QLabel {{ background: transparent; }}
QLabel:disabled {{ color: {TEXT_DISABLED}; }}

/* ===== 工具栏 ===== */
QToolBar {{ background: transparent; border: none; padding: 3px 6px; spacing: 2px; }}
QToolBar::separator {{ background: #34373c; width: 1px; margin: 5px 5px; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 9px; }}
QToolButton:hover {{ background: #2c2f34; }}
QToolButton:pressed {{ background: #34383e; }}
QToolButton:disabled {{ color: {TEXT_DISABLED}; }}

/* ===== 按钮（默认键 = 实心绿主按钮）===== */
QPushButton {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
               padding: 5px 14px; min-height: 16px; }}
QPushButton:hover {{ background-color: #32363b; border-color: #464b52; }}
QPushButton:pressed {{ background-color: #26292d; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; background-color: #242628; border-color: #2f3236; }}
QPushButton:default {{ background-color: {ACCENT}; border-color: {ACCENT};
                       color: {ACCENT_TEXT}; font-weight: 600; }}
QPushButton:default:hover {{ background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton:default:pressed {{ background-color: {ACCENT_PRESSED}; border-color: {ACCENT_PRESSED}; }}
QPushButton:default:disabled {{ background-color: #2c3a32; border-color: #2c3a32;
                                color: #576b5f; }}

/* ===== 输入框 ===== */
QLineEdit {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
             padding: 4px 8px; selection-background-color: rgba(74, 222, 128, 0.32); }}
QLineEdit:hover {{ border-color: #464b52; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled {{ color: {TEXT_DISABLED}; background-color: #222427; border-color: #303336; }}
QLineEdit[readOnly="true"] {{ color: {TEXT_SECONDARY}; background-color: #222427; }}
QTextEdit, QPlainTextEdit {{ background-color: {FIELD_BG}; border: 1px solid {BORDER};
                             border-radius: 6px; selection-background-color: rgba(74, 222, 128, 0.32); }}

/* ===== 下拉框 ===== */
QComboBox {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
             padding: 3px 8px 3px 10px; min-width: 64px; }}
QComboBox:hover {{ border-color: #464b52; }}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox:disabled {{ color: {TEXT_DISABLED}; background-color: #222427; }}
QComboBox::drop-down {{ background: transparent; border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background-color: {FIELD_BG}; border: 1px solid {BORDER};
                               border-radius: 6px; padding: 4px; outline: 0;
                               selection-background-color: rgba(74, 222, 128, 0.2);
                               selection-color: {TEXT}; }}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 2px 6px; border-radius: 4px; }}

/* ===== 复选 / 单选（深色下自绘指示器，Fusion 原生的边框太淡）===== */
QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {TEXT_DISABLED}; }}
QCheckBox::indicator, QGroupBox::indicator {{ width: 16px; height: 16px;
    border: 1px solid #4a4f57; border-radius: 4px; background-color: {FIELD_BG}; }}
QCheckBox::indicator:hover {{ border-color: #5c626b; }}
QCheckBox::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ border-color: #33363b; background-color: #222427; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid #4a4f57;
    border-radius: 8px; background-color: {FIELD_BG}; }}
QRadioButton::indicator:hover {{ border-color: #5c626b; }}
QRadioButton::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator:disabled {{ border-color: #33363b; background-color: #222427; }}

/* ===== 表格 ===== */
QTableView {{ outline: 0; background-color: {WINDOW_BG}; alternate-background-color: #232529;
              border: 1px solid {BORDER_SUBTLE}; gridline-color: transparent;
              selection-background-color: {SELECT_BG}; selection-color: {TEXT}; }}
QTableView::item {{ padding: 5px 8px; border: none; }}
QTableView::item:selected {{ background-color: {SELECT_BG}; }}
QTableCornerButton::section {{ background-color: {SURFACE}; border: none; }}
QHeaderView {{ background-color: transparent; }}
QHeaderView::section {{ background-color: {SURFACE}; color: {TEXT_SECONDARY}; padding: 6px 8px;
                        border: none; border-bottom: 1px solid {BORDER_SUBTLE}; font-weight: 600; }}
QHeaderView::section:hover {{ background-color: #26282c; color: #c9cdd2; }}

/* ===== 列表 ===== */
QListWidget {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
               padding: 2px; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 4px; }}
QListWidget::item:hover {{ background: #2f3338; }}
QListWidget::item:selected {{ background: rgba(74, 222, 128, 0.2); color: {TEXT}; }}

/* ===== 分组框（卡片 + 悬浮标题）===== */
QGroupBox {{ background-color: {SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;
             margin-top: 18px; padding: 10px 8px 6px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px;
                    top: 1px; padding: 0 4px; color: #86e7ae; }}

/* ===== 菜单 ===== */
QMenu {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
         padding: 5px 2px; }}
QMenu::item {{ padding: 5px 24px 5px 14px; border-radius: 4px; margin: 1px 4px; background: transparent; }}
QMenu::item:selected {{ background-color: rgba(74, 222, 128, 0.18); }}
QMenu::item:disabled {{ color: {TEXT_DISABLED}; }}
QMenu::separator {{ height: 1px; background: #34373c; margin: 5px 10px; }}

/* ===== 进度条 ===== */
QProgressBar {{ background-color: {FIELD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
                text-align: center; color: {TEXT}; min-height: 14px; }}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 5px; }}

/* ===== 滚动条（细圆角）===== */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3e44; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4f57; }}
QScrollBar::handle:vertical:pressed {{ background: #565c66; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3a3e44; border-radius: 3px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: #4a4f57; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ===== 分割器 / 状态栏 ===== */
QSplitter::handle {{ background: {WINDOW_BG}; }}
QSplitter::handle:vertical {{ height: 6px; }}
QSplitter::handle:hover {{ background: #34373c; }}
QStatusBar {{ background: #1b1c1f; border-top: 1px solid #2a2d31; color: {TEXT_SECONDARY}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {TEXT_SECONDARY}; }}

/* ===== 终端卡片（标题栏 + 终端一体）===== */
#terminalBar {{ background-color: {SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;
                border-bottom-left-radius: 0; border-bottom-right-radius: 0; }}
#terminalBar QLabel {{ color: {TEXT_SECONDARY}; font-weight: 600; }}
QPlainTextEdit#terminal {{ background-color: {TERMINAL_BG}; border: 1px solid {BORDER_SUBTLE};
                           border-top: none; border-radius: 8px; border-top-left-radius: 0;
                           border-top-right-radius: 0; color: {TERMINAL_TEXT};
                           font-family: "Cascadia Mono", "Consolas";
                           selection-background-color: rgba(74, 222, 128, 0.3); }}

/* ===== 进度卡片 ===== */
#progressBox {{ background-color: {SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; }}
"""


# =====================================================================
# Windows 系统标题栏深色（DWM）
# =====================================================================
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Win10 18985+ / Win11
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # 更早的 Win10 值
_DWMWA_CAPTION_COLOR = 35  # Win11：标题栏精确取主题色


def _colorref(hex_color: str) -> int:
    """转 DWM 需要的 COLORREF（0x00BBGGRR）。"""
    c = QColor(hex_color)
    return c.red() | (c.green() << 8) | (c.blue() << 16)


def _set_dark_title_bar(widget: QWidget) -> bool:
    """把顶层窗口的系统标题栏切成深色。非 Windows / 无原生句柄时静默跳过。"""
    if sys.platform != "win32":
        return False
    try:
        dwm = ctypes.windll.dwmapi
        hwnd = int(widget.winId())
    except Exception:  # noqa: BLE001 - 无 dwmapi / 句柄未就绪
        return False
    ok = False
    for attr in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
        value = ctypes.c_int(1)
        if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            ok = True
            break
    # Win11 可让标题栏颜色与主题完全一致；老系统返回失败码，忽略即可
    caption = ctypes.c_uint(_colorref(WINDOW_BG))
    dwm.DwmSetWindowAttribute(
        hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption)
    )
    return ok


class _DarkTitleBarFilter(QObject):
    """应用级事件过滤器：顶层窗口（主窗口/对话框）创建或显示时应用深色标题栏。"""

    _TYPES = (Qt.WindowType.Window, Qt.WindowType.Dialog)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange):
            if (
                isinstance(obj, QWidget)
                and obj.isWindow()
                and obj.windowType() in self._TYPES
            ):
                _set_dark_title_bar(obj)
        return False


_titlebar_filter: _DarkTitleBarFilter | None = None


def apply_dark_theme(app: QApplication) -> None:
    """切换到深色主题：Fusion + 深色调色板 + 全局 QSS。须在创建窗口前调用。"""
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(WINDOW_BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(FIELD_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(FIELD_BG))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(FIELD_BG))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(PLACEHOLDER))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_DISABLED))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#222427"))
    app.setPalette(pal)

    app.setStyleSheet(QSS)

    global _titlebar_filter
    if _titlebar_filter is None:
        _titlebar_filter = _DarkTitleBarFilter(app)
        app.installEventFilter(_titlebar_filter)
