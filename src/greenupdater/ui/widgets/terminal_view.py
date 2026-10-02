"""只读终端面板（对应 docs/design/03-ui.md §10、§13）。

累积全部历史日志、自动滚到底、可清屏；限制最大行数防无限增长。
只接受 append/clear，不支持输入。按行前缀（如 ``[成功]`` / ``[失败]``）着色，
颜色令牌取自 theme，深色底上高亮关键结果。
"""
from __future__ import annotations

import html
import re

from PySide6.QtWidgets import QPlainTextEdit

from greenupdater.infra import TERMINAL_MAX_LINES
from greenupdater.ui.theme import (
    STATUS_BUSY,
    STATUS_FAIL,
    STATUS_NEUTRAL,
    STATUS_OK,
    TERMINAL_TEXT,
)

# 日志行前缀 → 颜色（未命中则用默认正文色）
_COLOR_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\[(成功|完成|回滚完成)\]"), STATUS_OK),
    (re.compile(r"^\[(失败|检查失败|回滚失败)\]"), STATUS_FAIL),
    (re.compile(r"^\[提示\]"), STATUS_BUSY),
    (re.compile(r"^\[(跳过|取消)\]"), STATUS_NEUTRAL),
)


def _line_color(line: str) -> str:
    for pattern, color in _COLOR_RULES:
        if pattern.match(line):
            return color
    return TERMINAL_TEXT


class TerminalView(QPlainTextEdit):
    def __init__(self, parent=None, max_lines: int = TERMINAL_MAX_LINES) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setMaximumBlockCount(max_lines)  # 超过上限自动丢弃最旧行
        self.setUndoRedoEnabled(False)

    def append_line(self, line: str) -> None:
        """追加一行（按前缀着色）并滚动到底。"""
        self.appendHtml(
            f'<span style="color:{_line_color(line)}; white-space:pre-wrap;">'
            f"{html.escape(line)}</span>"
        )
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        for line in lines:
            self.appendHtml(
                f'<span style="color:{_line_color(line)}; white-space:pre-wrap;">'
                f"{html.escape(line)}</span>"
            )
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self) -> None:
        self.clear()
