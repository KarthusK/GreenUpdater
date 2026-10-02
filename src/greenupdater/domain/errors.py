"""统一异常类型（对应 docs/design/02-modules.md §5）。

编排层捕获这些异常并映射到对应 ``UpdateStage``，写入 ``app.last_error_stage`` /
``history.failed_stage``。基类 ``GreenUpdaterError`` 便于上层统一兜底。

注：``KeyringUnavailableError`` 属于基础设施层（infra.tokenstore），因分层依赖方向
（domain → infra，infra 不能反向 import domain）不在此重复定义。
"""
from __future__ import annotations


class GreenUpdaterError(Exception):
    """所有业务异常的基类。"""


class OperationCancelled(GreenUpdaterError):
    """用户协作式取消（worker 检测到 CancelToken.cancelled）。"""


class RateLimitError(GreenUpdaterError):
    """GitHub API 限流（匿名 60 次/小时耗尽）。"""


class NoAssetMatchedError(GreenUpdaterError):
    """正则未命中任何发布资产，或用户在多选弹框中取消。"""


class DownloadError(GreenUpdaterError):
    """下载失败（网络错误、重试耗尽、磁盘空间不足等）。"""


class ChecksumError(GreenUpdaterError):
    """SHA256 校验不符。"""


class ZipSlipError(GreenUpdaterError):
    """压缩包成员路径穿越（解压目标越出 dest）。"""


class ExtractError(GreenUpdaterError):
    """解压失败（格式不支持、文件损坏等）。"""


class ProcessKillError(GreenUpdaterError):
    """结束目标进程失败。"""


class SnapshotError(GreenUpdaterError):
    """创建完整快照失败（含磁盘空间不足）。"""


class OverwriteError(GreenUpdaterError):
    """覆盖目标目录失败——唯一会改动目标目录的阶段，故触发可回滚。"""
