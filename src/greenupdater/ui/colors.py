"""颜色设计令牌（单一出处，对应 docs/design/03-ui.md）。

供表格状态色、终端着色、QSS 模板（theme.qss）等处引用；
``theme.py`` re-export 全部令牌，外部仍可 ``from greenupdater.ui.theme import X``。
纯常量模块，不依赖 Qt，保证可被任意层安全导入。
"""
from __future__ import annotations

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

__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "ACCENT_TEXT",
    "BORDER",
    "BORDER_SUBTLE",
    "DANGER",
    "FIELD_BG",
    "ICON",
    "PLACEHOLDER",
    "SELECT_BG",
    "STATUS_BUSY",
    "STATUS_DISABLED",
    "STATUS_FAIL",
    "STATUS_NEUTRAL",
    "STATUS_OK",
    "STATUS_UPDATE",
    "SURFACE",
    "TERMINAL_BG",
    "TERMINAL_TEXT",
    "TEXT",
    "TEXT_DISABLED",
    "TEXT_SECONDARY",
    "WINDOW_BG",
]
