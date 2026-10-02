"""只读终端面板（对应 docs/design/03-ui.md §10、§13）。

累积全部历史日志、自动滚到底、可清屏；限制最大行数防无限增长。
只接受 append/clear，不支持输入。
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit

from greenupdater.infra import TERMINAL_MAX_LINES


class TerminalView(QPlainTextEdit):
    def __init__(self, parent=None, max_lines: int = TERMINAL_MAX_LINES) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setMaximumBlockCount(max_lines)  # 超过上限自动丢弃最旧行
        self.setUndoRedoEnabled(False)
        font = self.font()
        font.setFamily("Consolas")
        self.setFont(font)

    def append_line(self, line: str) -> None:
        """追加一行并滚动到底。"""
        self.appendPlainText(line)
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        self.appendPlainText("\n".join(lines))
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self) -> None:
        self.clear()
