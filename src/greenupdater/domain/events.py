"""事件 / 回调契约（对应 docs/design/02-modules.md §1）。

领域层与 UI 解耦的关键：耗时操作在 worker 线程执行，通过 ``UpdateListener`` 把
进度 / 日志 / 阶段结果推给上层；UI 再把回调转成 Qt 信号。领域层**不** import PySide6。

这些类型放在 domain 而非 service：domain 的 Downloader/Extractor 等要消费它们，
若放 service 会导致 domain 反向依赖 service，破坏单向分层。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from greenupdater.models import UpdateStage


@dataclass
class Progress:
    """一次进度回报。"""

    stage: UpdateStage
    percent: int  # 0..100；-1 表示不确定进度(indeterminate)
    message: str = ""  # 人类可读，如 "下载中 12.3 MB / 40 MB"


@dataclass
class StageResult:
    """某阶段结束的结果。"""

    stage: UpdateStage
    ok: bool
    error: str | None = None


@runtime_checkable
class UpdateListener(Protocol):
    """长任务对外汇报的回调集合（UI 侧实现并转 Qt 信号）。"""

    def on_log(self, line: str) -> None: ...  # 终端面板追加一行

    def on_progress(self, p: Progress) -> None: ...  # 进度条更新

    def on_stage(self, s: StageResult) -> None: ...  # 某阶段结束

    def on_cancelled(self) -> None: ...  # 用户取消


class CancelToken:
    """协作式取消：worker 周期性检查 ``.cancelled``。线程安全。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


class NullListener:
    """空实现：测试 / 无 UI 场景下的默认 listener。"""

    def on_log(self, line: str) -> None:  # noqa: D102
        pass

    def on_progress(self, p: Progress) -> None:  # noqa: D102
        pass

    def on_stage(self, s: StageResult) -> None:  # noqa: D102
        pass

    def on_cancelled(self) -> None:  # noqa: D102
        pass
