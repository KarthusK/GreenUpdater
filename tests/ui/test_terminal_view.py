"""ui.widgets.terminal_view 测试（pytest-qt）。"""
from __future__ import annotations

from greenupdater.ui.widgets import TerminalView


def test_read_only(qtbot):
    tv = TerminalView()
    qtbot.addWidget(tv)
    assert tv.isReadOnly() is True


def test_append_and_clear(qtbot):
    tv = TerminalView()
    qtbot.addWidget(tv)
    tv.append_line("hello")
    tv.append_line("world")
    text = tv.toPlainText()
    assert "hello" in text
    assert "world" in text
    tv.clear_log()
    assert tv.toPlainText() == ""


def test_append_lines_batch(qtbot):
    tv = TerminalView()
    qtbot.addWidget(tv)
    tv.append_lines(["a", "b", "c"])
    text = tv.toPlainText()
    assert "a" in text and "b" in text and "c" in text


def test_max_block_count(qtbot):
    tv = TerminalView(max_lines=10)
    qtbot.addWidget(tv)
    assert tv.maximumBlockCount() == 10
    for i in range(25):
        tv.append_line(f"line {i}")
    # 超过上限后旧行被丢弃
    assert tv.document().blockCount() <= 11
    assert "line 24" in tv.toPlainText()
    assert "line 0" not in tv.toPlainText()
