"""日志与终端桥（对应 docs/design/02-modules.md §4.4、03-ui.md §10）。

- ``setup_logging``：loguru 文件 sink（轮转 + 保留 + UTF-8），可选追加终端桥 sink。
- ``TerminalBridge``：loguru sink → 线程安全队列，UI 侧 ``drain()`` 取行追加到只读终端。
  ``enqueue=True`` 让日志在独立线程处理，跨 worker/UI 线程安全。
"""
from __future__ import annotations

import threading
from collections import deque
from pathlib import Path

from loguru import logger

#: 终端面板保留的最大行数（防止无限增长）
TERMINAL_MAX_LINES = 5000

_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
_TERMINAL_FORMAT = "{time:HH:mm:ss} | {level: <7} | {message}"


class TerminalBridge:
    """把日志行缓存到内存队列，供 UI 只读终端面板消费。"""

    def __init__(self, maxlen: int = TERMINAL_MAX_LINES) -> None:
        self._lines: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def sink(self, message) -> None:  # loguru sink 签名
        line = str(message).rstrip("\n")
        with self._lock:
            self._lines.append(line)

    def drain(self) -> list[str]:
        """取出并清空当前缓冲的行（UI 定时调用后 append 到终端）。"""
        with self._lock:
            items = list(self._lines)
            self._lines.clear()
            return items

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


def setup_logging(
    log_file: Path | str,
    level: str = "INFO",
    bridge: TerminalBridge | None = None,
    also_stderr: bool = False,
):
    """配置 loguru，返回 logger。重复调用会先清空已有 sink。"""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        str(log_file),
        level=level,
        format=_FILE_FORMAT,
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
    )
    if bridge is not None:
        logger.add(
            bridge.sink,
            level=level,
            format=_TERMINAL_FORMAT,
            enqueue=True,
        )
    if also_stderr:
        import sys

        logger.add(sys.stderr, level=level, format=_TERMINAL_FORMAT)
    return logger
