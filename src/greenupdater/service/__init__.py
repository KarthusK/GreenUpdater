"""应用服务层（对应 docs/design/02-modules.md §3）。

UI 只依赖此层：``UpdateOrchestrator`` 串起 domain 的完整流水线，
事件/回调契约（Progress/StageResult/UpdateListener/CancelToken）定义在 domain.events。
"""
from __future__ import annotations

from .orchestrator import CheckResult, UpdateOrchestrator, UpdateOutcome

__all__ = [
    "UpdateOrchestrator",
    "CheckResult",
    "UpdateOutcome",
]
