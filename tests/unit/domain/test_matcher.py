"""domain.provider.matcher 测试：命中 0/1/多、架构过滤、choose 注入。"""
from __future__ import annotations

import pytest

from greenupdater.domain import Asset, AssetMatcher, Release
from greenupdater.domain.errors import NoAssetMatchedError


def rel(*names) -> Release:
    return Release(
        tag_name="v1.0",
        is_prerelease=False,
        assets=[Asset(name=n, download_url=f"https://dl/{n}") for n in names],
    )


def test_no_match_raises():
    m = AssetMatcher()
    with pytest.raises(NoAssetMatchedError):
        m.match(rel("app-linux.tar.gz"), r".*windows.*\.zip", lambda c: None)


def test_single_match_returns_without_choose():
    m = AssetMatcher()
    called = []

    def choose(c):
        called.append(c)
        return c[0]

    got = m.match(rel("app-win.zip"), r".*\.zip", choose)
    assert got.name == "app-win.zip"
    assert called == []  # 唯一命中不应弹框


def test_multiple_narrowed_by_arch_without_choose():
    m = AssetMatcher()
    called = []
    got = m.match(
        rel("app-x86.zip", "app-x86_64.zip"),
        r".*\.zip",
        lambda c: called.append(c) or c[0],
    )
    assert got.name == "app-x86_64.zip"
    assert called == []  # 架构过滤后唯一，不弹框


def test_multiple_after_arch_uses_choose():
    m = AssetMatcher()
    seen = {}

    def choose(candidates):
        seen["cands"] = [a.name for a in candidates]
        return candidates[1]

    got = m.match(
        rel("a-x64-setup.zip", "a-x64-portable.zip"),
        r".*\.zip",
        choose,
    )
    assert got.name == "a-x64-portable.zip"
    assert seen["cands"] == ["a-x64-setup.zip", "a-x64-portable.zip"]


def test_choose_cancel_raises():
    m = AssetMatcher()
    with pytest.raises(NoAssetMatchedError):
        m.match(rel("a-x64.zip", "b-x64.zip"), r".*\.zip", lambda c: None)


def test_no_arch_keyword_falls_back_to_all():
    m = AssetMatcher()
    seen = {}

    def choose(c):
        seen["cands"] = [a.name for a in c]
        return c[0]

    m.match(rel("foo.zip", "bar.zip"), r".*\.zip", choose)
    assert seen["cands"] == ["foo.zip", "bar.zip"]
