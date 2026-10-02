"""全局设置与 JSON 导入导出模型（对应 docs/design/01-data-model.md §4/§5）。

注意：GitHub Token **不在**这些模型里——它由 keyring 单独存系统凭据库，
既不入库也不进导入导出 JSON。
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .app import AppConfig
from .enums import VersionDetectSource

#: 当前导出 schema 版本；字段变更时递增并在导入侧做迁移。
EXPORT_SCHEMA_VERSION = 1


class Settings(BaseModel):
    """全局设置（存 settings 键值表）。"""

    proxy_enabled: bool = False
    proxy_url: str | None = None
    log_level: str = "INFO"
    default_include_prerelease: bool = False


class ExportApp(AppConfig):
    """导出/导入用的软件条目 = 配置 + 稳定标识 + 本地版本信息。"""

    uid: str
    current_version: str | None = None
    current_version_src: VersionDetectSource = VersionDetectSource.UNKNOWN


class ExportBundle(BaseModel):
    """整份导出文件的顶层结构。"""

    version: int = EXPORT_SCHEMA_VERSION
    exported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    apps: list[ExportApp] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)
