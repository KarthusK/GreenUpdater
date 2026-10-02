"""资产匹配（对应 docs/design/02-modules.md §2.1、§8.1）。

命中规则：
- 正则命中 0 个 → NoAssetMatchedError（失败阶段 check）
- 命中 1 个 → 直接用
- 命中多个 → 先按架构关键字（x86_64/x64 等）过滤优先；过滤后仍 ≥2 → 调 choose 弹框让用户选
- 用户取消（choose 返回 None）→ NoAssetMatchedError（记为 failed@check）

choose 由 UI 注入，领域层不依赖 GUI。
"""
from __future__ import annotations

import re
from typing import Callable

from ..errors import NoAssetMatchedError
from .base import Asset, Release

#: 64 位架构关键字（命中任一即视为优先候选）
_ARCH_KEYWORDS = ("x86_64", "x64", "win64", "64bit", "amd64")

#: choose 回调：从候选列表选一个，取消返回 None
Chooser = Callable[[list[Asset]], "Asset | None"]


class AssetMatcher:
    def match(self, release: Release, pattern: str, choose: Chooser) -> Asset:
        matched = [a for a in release.assets if re.search(pattern, a.name)]
        if not matched:
            raise NoAssetMatchedError(
                f"发布 {release.tag_name} 中没有资产匹配正则 /{pattern}/"
            )
        if len(matched) == 1:
            return matched[0]

        arch = [a for a in matched if self._is_64bit(a.name)]
        candidates = arch or matched
        if len(candidates) == 1:
            return candidates[0]

        chosen = choose(candidates)
        if chosen is None:
            raise NoAssetMatchedError("用户在资产选择弹框中取消")
        return chosen

    @staticmethod
    def _is_64bit(name: str) -> bool:
        low = name.lower()
        return any(k in low for k in _ARCH_KEYWORDS)
