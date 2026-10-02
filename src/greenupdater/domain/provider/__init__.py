"""源适配器包：Asset / Release / SourceProvider / GitHubProvider / AssetMatcher。"""
from __future__ import annotations

from .base import Asset, Release, SourceProvider
from .github import GitHubProvider
from .matcher import AssetMatcher

__all__ = [
    "Asset",
    "Release",
    "SourceProvider",
    "GitHubProvider",
    "AssetMatcher",
]
