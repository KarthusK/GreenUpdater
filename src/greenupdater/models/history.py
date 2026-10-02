"""更新历史模型 ``UpdateRecord``（对应 docs/design/01-data-model.md §4）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .enums import UpdateResult, UpdateStage


class UpdateRecord(BaseModel):
    """一次更新尝试的记录，成功或失败都写。"""

    id: int | None = None
    app_id: int

    from_version: str | None = None
    to_version: str | None = None

    asset_name: str | None = None
    asset_size: int | None = None
    sha256: str | None = None

    result: UpdateResult
    failed_stage: UpdateStage | None = None
    error_message: str | None = None
    rolled_back: bool = False

    started_at: datetime
    finished_at: datetime | None = None
