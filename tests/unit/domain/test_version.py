"""domain.version 测试：提取、归一化、比较。"""
from __future__ import annotations

from pathlib import Path

import pytest

from greenupdater.domain import Asset, Release, VersionResolver
from greenupdater.models import AppConfig, VersionSource


def make_cfg(**kw) -> AppConfig:
    base = dict(
        name="X",
        repo_owner="o",
        repo_name="r",
        asset_pattern=r".*\.zip",
        target_dir=Path("D:/apps/x"),
    )
    base.update(kw)
    return AppConfig(**base)


@pytest.fixture()
def resolver():
    return VersionResolver()


def rel(tag="v1.2.3"):
    return Release(tag_name=tag, is_prerelease=False, assets=[])


def asset(name="app-1.2.3-win.zip"):
    return Asset(name=name, download_url="u")


def test_extract_tag_with_pattern(resolver):
    cfg = make_cfg(version_source=VersionSource.TAG, version_pattern=r"v?([\d.]+)")
    assert resolver.extract(rel("v1.2.3"), asset(), cfg) == "1.2.3"


def test_extract_asset_name_with_pattern(resolver):
    cfg = make_cfg(
        version_source=VersionSource.ASSET_NAME,
        version_pattern=r"app-([\d.]+)-win",
    )
    assert resolver.extract(rel(), asset("app-9.8.7-win.zip"), cfg) == "9.8.7"


def test_extract_no_pattern_returns_whole(resolver):
    cfg = make_cfg(version_source=VersionSource.TAG, version_pattern=None)
    assert resolver.extract(rel("v2.0"), asset(), cfg) == "v2.0"


def test_extract_pattern_no_group_uses_whole_match(resolver):
    cfg = make_cfg(version_source=VersionSource.TAG, version_pattern=r"\d+\.\d+")
    assert resolver.extract(rel("release-3.11-x"), asset(), cfg) == "3.11"


def test_extract_pattern_not_matching_returns_none(resolver):
    cfg = make_cfg(version_source=VersionSource.TAG, version_pattern=r"zzz([\d.]+)")
    assert resolver.extract(rel("v1.0"), asset(), cfg) is None


def test_normalize_strips_v_and_extracts_digits(resolver):
    assert resolver.normalize("v1.2.3") == (1, 2, 3)
    assert resolver.normalize("2026.01.02") == (2026, 1, 2)
    assert resolver.normalize("nightly") == ()


@pytest.mark.parametrize(
    "local,remote,expected",
    [
        (None, "1.0.0", True),
        ("", "1.0.0", True),
        ("unknown", "1.0.0", True),
        ("1.0.0", "1.0.1", True),
        ("1.0.1", "1.0.0", False),
        ("1.2.0", "1.2.0", False),
        ("1.2", "1.2.0", False),  # 补零对齐后相等
        ("v1.2", "1.3", True),
    ],
)
def test_is_update_available(resolver, local, remote, expected):
    assert resolver.is_update_available(local, remote) is expected


def test_non_numeric_fallback(resolver):
    # 无法数值化：字符串不同即视为有更新
    assert resolver.is_update_available("alpha", "beta") is True
    assert resolver.is_update_available("alpha", "alpha") is False
