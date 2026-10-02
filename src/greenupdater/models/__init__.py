"""数据模型层：pydantic 模型与枚举。

对外统一从此包导入，例如::

    from greenupdater.models import App, AppConfig, AppStatus, Settings
"""
from __future__ import annotations

from .app import App, AppConfig
from .enums import (
    AppStatus,
    SourceType,
    UpdateResult,
    UpdateStage,
    VersionDetectSource,
    VersionSource,
)
from .history import UpdateRecord
from .settings import EXPORT_SCHEMA_VERSION, ExportApp, ExportBundle, Settings

__all__ = [
    "App",
    "AppConfig",
    "AppStatus",
    "SourceType",
    "UpdateResult",
    "UpdateStage",
    "VersionDetectSource",
    "VersionSource",
    "UpdateRecord",
    "Settings",
    "ExportApp",
    "ExportBundle",
    "EXPORT_SCHEMA_VERSION",
]
