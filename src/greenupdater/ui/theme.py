"""深色主题（对应 docs/design/03-ui.md）。

颜色令牌集中在 ``colors.py``（单一出处），本模块 re-export 供表格状态色、
终端着色等处引用；全局 QSS 存于 ``theme.qss`` 模板文件（IDE 可按 CSS 高亮），
``$TOKEN`` 占位符在导入时用 ``string.Template`` 渲染成 ``QSS`` 常量。
``apply_dark_theme`` = Fusion 风格 + 深色 QPalette（兜底未被 QSS 覆盖的原生绘制）
+ 全局 QSS；Windows 上另挂全局事件过滤器，把所有顶层窗口的系统标题栏切成深色。
图标为 ``icons/`` 目录下的 Tabler SVG 文件（MIT），用 PySide6 自带的 QtSvg 渲染，
无新增依赖；加载时把文件里的 ``currentColor`` 替换为主题色，一份文件即可产出三态。
"""
from __future__ import annotations

import ctypes
import sys
from functools import cache
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
# 图标（icons/*.svg，取自 Tabler Icons，MIT——声明见 icons/LICENSE）
# =====================================================================
_ICONS_DIR = Path(__file__).with_name("icons")

#: 可用图标名（与 icons/*.svg 文件名一一对应，供测试与自检枚举）
ICON_NAMES: tuple[str, ...] = (
    "add",
    "edit",
    "delete",
    "refresh",
    "download",
    "undo",
    "import",
    "export",
    "settings",
    "close",
)

# Tabler 官方文件用 currentColor 占位描边色；加载时替换为实际颜色，
# 一份文件即可产出 normal / hover / disabled 三态。
_COLOR_PLACEHOLDER = "currentColor"


@cache
def _load_icon(name: str) -> str:
    """读取图标 SVG 原文；文件缺失时明确报错，而不是渲染成空白。"""
    path = _ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"图标文件缺失: {path}（可用: {', '.join(ICON_NAMES)}）")
    return path.read_text(encoding="utf-8")


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
    template = _load_icon(name)

    def render(fg: str) -> QPixmap:
        return _render_icon(template.replace(_COLOR_PLACEHOLDER, fg), size)

    ic = QIcon()
    ic.addPixmap(render(color), QIcon.Mode.Normal)
    ic.addPixmap(render(color if color != ICON else TEXT), QIcon.Mode.Active)
    ic.addPixmap(render(TEXT_DISABLED), QIcon.Mode.Disabled)
    _icon_cache[key] = ic
    return ic


@cache
def app_icon() -> QIcon:
    """应用图标（窗口 / 任务栏）。多尺寸 ico 由 Qt 按需挑选，高分屏不糊。"""
    path = Path(__file__).with_name("app.ico")
    if not path.is_file():
        raise FileNotFoundError(f"应用图标缺失: {path}")
    return QIcon(str(path))


# =====================================================================
# 全局样式表（模板见 theme.qss，占位符取自 colors.py）
# =====================================================================
_QSS_PATH = Path(__file__).with_name("theme.qss")


def _load_qss() -> str:
    """渲染 QSS 模板。用 substitute 而非 safe_substitute：
    占位符拼错时导入即抛 KeyError，避免静默把 $FOO 塞进样式表。"""
    tokens = {name: getattr(colors, name) for name in colors.__all__}
    # 图标路径必须注入绝对路径：QSS 的 url() 相对路径按进程 CWD 解析，
    # 打包后从别处启动会静默加载不到（勾/点消失）。
    tokens["ICONS_DIR"] = _ICONS_DIR.as_posix()
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
