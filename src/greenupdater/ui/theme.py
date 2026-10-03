"""深色主题（对应 docs/design/03-ui.md）。

颜色令牌集中在 ``colors.py``（单一出处），本模块 re-export 供表格状态色、
终端着色等处引用；全局 QSS 存于 ``theme.qss`` 模板文件（IDE 可按 CSS 高亮），
``$TOKEN`` 占位符在导入时用 ``string.Template`` 渲染成 ``QSS`` 常量。
``apply_dark_theme`` = Fusion 风格 + 深色 QPalette（兜底未被 QSS 覆盖的原生绘制）
+ 全局 QSS；Windows 上另挂全局事件过滤器，把所有顶层窗口的系统标题栏切成深色。
图标为内嵌单色线性 SVG，用 PySide6 自带的 QtSvg 渲染，无新增依赖。
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import QEvent, QByteArray, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from greenupdater.ui import colors

# re-export 全部令牌，保持既有 from theme import X / theme.X 引用零改动
from greenupdater.ui.colors import (  # noqa: F401
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    ACCENT_TEXT,
    BORDER,
    BORDER_SUBTLE,
    DANGER,
    FIELD_BG,
    ICON,
    PLACEHOLDER,
    SELECT_BG,
    STATUS_BUSY,
    STATUS_DISABLED,
    STATUS_FAIL,
    STATUS_NEUTRAL,
    STATUS_OK,
    STATUS_UPDATE,
    SURFACE,
    TERMINAL_BG,
    TERMINAL_TEXT,
    TEXT,
    TEXT_DISABLED,
    TEXT_SECONDARY,
    WINDOW_BG,
)

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
# 全局样式表（模板见 theme.qss，占位符取自 colors.py）
# =====================================================================
_QSS_PATH = Path(__file__).with_name("theme.qss")


def _load_qss() -> str:
    """渲染 QSS 模板。用 substitute 而非 safe_substitute：
    占位符拼错时导入即抛 KeyError，避免静默把 $FOO 塞进样式表。"""
    tokens = {name: getattr(colors, name) for name in colors.__all__}
    return Template(_QSS_PATH.read_text(encoding="utf-8")).substitute(tokens)


QSS = _load_qss()


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
