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

ACCENT = "#22c55e"  # 强调绿（品牌色）
ACCENT_HOVER = "#20e067"
ACCENT_PRESSED = "#1bb855"
ACCENT_TEXT = "#10231a"  # 实心绿按钮上的深色文字
ACCENT_TEXT_ON_DARK = "#4ade80"  # 深底上的绿色文字（卡片标题等）
SELECT_BG = "rgba(34, 197, 94, 0.20)"  # 选中行（表格 / 列表 / 下拉项）
SELECT_BG_MENU = "rgba(34, 197, 94, 0.22)"  # 菜单项高亮
SELECT_BG_INPUT = "rgba(34, 197, 94, 0.38)"  # 输入框 / 终端文本选中

# 状态色统一收拢到「对比度 6.0~7.5（相对窗口底）」区间；
STATUS_OK = ACCENT  # 已最新 / 更新成功：与品牌绿同色，不单独定值
STATUS_UPDATE = "#64b5f6"  # 可更新
STATUS_BUSY = "#e0a304"  # 更新中 / 提示
STATUS_FAIL = "#f87979"  # 失败
STATUS_NEUTRAL = "#9aa0a6"  # 未检查 / 跳过 / 取消
STATUS_DISABLED = "#6f7378"  # 停用行（刻意低对比，不参与亮度带校准）
DANGER = "#f87979"  # 警告文字（设置页等）

ICON = "#c3c7cc"  # 工具栏图标默认色
TERMINAL_TEXT = "#c9cdd2"  # 终端正文
TERMINAL_BG = "#17181b"

__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "ACCENT_TEXT",
    "ACCENT_TEXT_ON_DARK",
    "BORDER",
    "BORDER_SUBTLE",
    "DANGER",
    "FIELD_BG",
    "ICON",
    "PLACEHOLDER",
    "SELECT_BG",
    "SELECT_BG_INPUT",
    "SELECT_BG_MENU",
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
