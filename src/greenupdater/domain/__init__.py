"""领域核心：纯业务逻辑，不依赖 PySide6（对应 docs/design/02-modules.md §2）。

依赖方向单向向下：service → domain → infra。domain 只通过 events 里的回调对外通信，
因此可脱离 GUI 单测。
"""
from __future__ import annotations

from .backup import BackupManager
from .detect import LocalVersionDetector
from .download import Downloader
from .errors import (
    ChecksumError,
    DownloadError,
    ExtractError,
    GreenUpdaterError,
    NoAssetMatchedError,
    OperationCancelled,
    OverwriteError,
    ProcessKillError,
    RateLimitError,
    SnapshotError,
    ZipSlipError,
)
from .events import CancelToken, NullListener, Progress, StageResult, UpdateListener
from .extract import Extractor
from .overwrite import Overwriter
from .process import ProcessManager
from .provider import Asset, AssetMatcher, GitHubProvider, Release, SourceProvider
from .version import VersionResolver

__all__ = [
    # errors
    "GreenUpdaterError",
    "OperationCancelled",
    "RateLimitError",
    "NoAssetMatchedError",
    "DownloadError",
    "ChecksumError",
    "ZipSlipError",
    "ExtractError",
    "ProcessKillError",
    "SnapshotError",
    "OverwriteError",
    # events
    "Progress",
    "StageResult",
    "UpdateListener",
    "CancelToken",
    "NullListener",
    # provider
    "Asset",
    "Release",
    "SourceProvider",
    "GitHubProvider",
    "AssetMatcher",
    # version / detect
    "VersionResolver",
    "LocalVersionDetector",
    # download / extract
    "Downloader",
    "Extractor",
    # process / backup / overwrite
    "ProcessManager",
    "BackupManager",
    "Overwriter",
]
