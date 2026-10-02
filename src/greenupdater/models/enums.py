"""枚举定义（对应 docs/design/01-data-model.md §2）。

所有枚举继承 ``str`` 以便直接与 SQLite TEXT / JSON 字符串互转。
"""
from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """软件源类型；当前仅 GitHub，其余为适配器预留。"""

    GITHUB = "github"
    # 预留: GITLAB = "gitlab"; GITEE = "gitee"; CUSTOM = "custom"


class VersionSource(str, Enum):
    """版本号从哪里提取。"""

    TAG = "tag"
    ASSET_NAME = "asset_name"


class VersionDetectSource(str, Enum):
    """本地当前版本的探测来源。"""

    PE = "pe"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class AppStatus(str, Enum):
    """列表状态列取值。"""

    UNKNOWN = "unknown"
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    UPDATING = "updating"
    SUCCESS = "success"
    FAILED = "failed"


class UpdateStage(str, Enum):
    """更新流程阶段（也是失败阶段标记）。顺序即执行顺序。"""

    CHECK = "check"
    DOWNLOAD = "download"
    EXTRACT = "extract"
    KILL_PROCESS = "kill_process"
    SNAPSHOT = "snapshot"
    OVERWRITE = "overwrite"


class UpdateResult(str, Enum):
    """单次更新结果。"""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"  # 用户取消（不写 history，仅用于界面汇总）
