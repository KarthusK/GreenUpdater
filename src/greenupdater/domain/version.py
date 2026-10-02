"""版本提取与比较（对应 docs/design/02-modules.md §2.2）。

VersionResolver 是纯逻辑，不依赖网络 / GUI，可用假 Release/Asset 直接单测。
"""
from __future__ import annotations

import re

from loguru import logger

from greenupdater.models import AppConfig, VersionSource

from .provider.base import Asset, Release

#: 提取数值段用
_NUM_RE = re.compile(r"\d+")

#: 归一化时剥掉的前缀
_PREFIX = "vV"


class VersionResolver:
    def extract(self, release: Release, asset: Asset, cfg: AppConfig) -> str | None:
        """按 cfg.version_source 取原始串，再用 cfg.version_pattern 的捕获组提取。

        - version_source=tag → release.tag_name；=asset_name → asset.name
        - 有 pattern：命中则取 group(1)（有捕获组）或 group(0)；未命中返回 None
        - 无 pattern：返回整体（去空白）
        """
        raw = release.tag_name if cfg.version_source == VersionSource.TAG else asset.name
        if not raw:
            return None
        raw = raw.strip()
        if cfg.version_pattern:
            m = re.search(cfg.version_pattern, raw)
            if not m:
                return None
            return m.group(1) if m.groups() else m.group(0)
        return raw

    def normalize(self, raw: str) -> tuple[int, ...]:
        """归一化为可比较的整数元组：剥 'v' 前缀、抽取所有数字段。

        无数字时返回空元组，调用方据此回退到字符串比较。
        """
        s = raw.strip().lstrip(_PREFIX)
        return tuple(int(x) for x in _NUM_RE.findall(s))

    def is_update_available(self, local: str | None, remote: str) -> bool:
        """remote 是否比 local 新。

        - local 为 None/空/unknown → True（全新安装）
        - 双方都能数值化 → 补零对齐后比较（1.2 视为等于 1.2.0）
        - 无法数值化 → 保守判定：字符串不同即视为有更新，并告警
        """
        if not local or local.strip().lower() == "unknown":
            return True

        ln, rn = self.normalize(local), self.normalize(remote)
        if ln and rn:
            return self._pad(rn) > self._pad(ln)

        logger.warning(f"版本无法数值化，按字符串比较：local={local!r} remote={remote!r}")
        return local.strip() != remote.strip()

    @staticmethod
    def _pad(v: tuple[int, ...], width: int = 8) -> tuple[int, ...]:
        """补零到固定宽度，使 (1,2) 与 (1,2,0) 相等；超长则原样返回。"""
        if len(v) >= width:
            return v
        return v + (0,) * (width - len(v))
