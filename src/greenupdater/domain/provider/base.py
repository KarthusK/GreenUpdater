"""源适配器抽象（对应 docs/design/02-modules.md §2.1）。

抽象出"从哪拿版本与下载链接"，先实现 GitHub，预留 GitLab/Gitee/自定义 URL。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from greenupdater.models import AppConfig, SourceType


@dataclass
class Asset:
    """一个可下载的发布资产。"""

    name: str
    download_url: str
    size: int | None = None
    sha256: str | None = None  # GitHub API 通常不提供，见 02-modules §8.2


@dataclass
class Release:
    """一个发布版本。"""

    tag_name: str
    is_prerelease: bool
    published_at: str | None = None
    assets: list[Asset] = field(default_factory=list)


class SourceProvider(ABC):
    """版本源适配器基类。"""

    source_type: SourceType

    @abstractmethod
    def fetch_releases(
        self, app: AppConfig, token: str | None, limit: int = 10
    ) -> list[Release]:
        """拉取发布列表（按时间倒序）。已按 include_prerelease 过滤。"""
        raise NotImplementedError
