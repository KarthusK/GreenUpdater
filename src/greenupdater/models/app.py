"""软件条目模型：``AppConfig``（可编辑配置）与 ``App``（持久化实体）。

对应 docs/design/01-data-model.md §4。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import AppStatus, SourceType, UpdateStage, VersionDetectSource, VersionSource


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppConfig(BaseModel):
    """一个被管理软件的配置。用于编辑对话框与 JSON 导入导出。"""

    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(min_length=1)
    source_type: SourceType = SourceType.GITHUB
    repo_owner: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)

    asset_pattern: str = Field(min_length=1, description="资产文件名匹配正则")
    version_source: VersionSource = VersionSource.TAG
    version_pattern: str | None = Field(
        default=None, description="版本提取正则（含一个捕获组）；为空则用整体 tag/名"
    )
    include_prerelease: bool = False

    target_dir: Path
    exe_relpath: str | None = None

    process_names: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)

    backup_enabled: bool = True
    enabled: bool = True

    @field_validator("asset_pattern", "version_pattern")
    @classmethod
    def _validate_regex(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            re.compile(value)
        except re.error as exc:  # pragma: no cover - 由 pydantic 包装为 ValidationError
            raise ValueError(f"无效的正则表达式: {exc}") from exc
        return value

    @property
    def repo(self) -> str:
        """``owner/repo`` 形式，便于拼装 API 与展示。"""
        return f"{self.repo_owner}/{self.repo_name}"


class App(AppConfig):
    """持久化实体 = 配置 + 稳定标识 + 运行态。"""

    id: int
    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))

    current_version: str | None = None
    current_version_src: VersionDetectSource = VersionDetectSource.UNKNOWN
    latest_version: str | None = None

    last_status: AppStatus = AppStatus.UNKNOWN
    last_error_stage: UpdateStage | None = None
    last_error_message: str | None = None
    rollback_available: bool = False

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
