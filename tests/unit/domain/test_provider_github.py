"""domain.provider.github 测试：用 httpx.MockTransport，不发真实网络请求。"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from greenupdater.domain import GitHubProvider, RateLimitError
from greenupdater.domain.errors import GreenUpdaterError
from greenupdater.models import AppConfig


def make_app(**kw) -> AppConfig:
    base = dict(
        name="X",
        repo_owner="octo",
        repo_name="cat",
        asset_pattern=r".*\.zip",
        target_dir=Path("D:/apps/x"),
    )
    base.update(kw)
    return AppConfig(**base)


def provider_with(handler) -> GitHubProvider:
    return GitHubProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))


def _release(tag, *, prerelease=False, draft=False, assets=None, digest=None):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "published_at": "2026-01-01T00:00:00Z",
        "assets": assets
        if assets is not None
        else [
            {
                "name": f"app-{tag}.zip",
                "browser_download_url": f"https://dl/{tag}.zip",
                "size": 1024,
                "digest": digest,
            }
        ],
    }


def test_parses_releases_and_assets():
    payload = [_release("v1.1"), _release("v1.0")]

    def handler(request):
        return httpx.Response(200, json=payload)

    with provider_with(handler) as p:
        rels = p.fetch_releases(make_app(), token=None)
    assert [r.tag_name for r in rels] == ["v1.1", "v1.0"]
    assert rels[0].assets[0].name == "app-v1.1.zip"
    assert rels[0].assets[0].size == 1024
    assert rels[0].assets[0].download_url == "https://dl/v1.1.zip"


def test_filters_drafts_and_prerelease_by_default():
    payload = [
        _release("v2.0", prerelease=True),
        _release("v1.9", draft=True),
        _release("v1.8"),
    ]

    def handler(request):
        return httpx.Response(200, json=payload)

    with provider_with(handler) as p:
        rels = p.fetch_releases(make_app(), token=None)
    assert [r.tag_name for r in rels] == ["v1.8"]


def test_include_prerelease_keeps_pre():
    payload = [_release("v2.0", prerelease=True), _release("v1.8")]

    def handler(request):
        return httpx.Response(200, json=payload)

    with provider_with(handler) as p:
        rels = p.fetch_releases(make_app(include_prerelease=True), token=None)
    assert [r.tag_name for r in rels] == ["v2.0", "v1.8"]


def test_token_header_sent():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        seen["ua"] = request.headers.get("User-Agent")
        return httpx.Response(200, json=[])

    with provider_with(handler) as p:
        p.fetch_releases(make_app(), token="ghp_secret")
    assert seen["auth"] == "Bearer ghp_secret"
    assert seen["ua"]  # User-Agent 必须存在（GitHub 强制要求）


def test_per_page_param():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    with provider_with(handler) as p:
        p.fetch_releases(make_app(), token=None, limit=5)
    assert "per_page=5" in seen["url"]
    assert "/repos/octo/cat/releases" in seen["url"]


def test_sha256_parsed_from_digest():
    payload = [_release("v1.0", digest="sha256:abc123")]

    def handler(request):
        return httpx.Response(200, json=payload)

    with provider_with(handler) as p:
        rels = p.fetch_releases(make_app(), token=None)
    assert rels[0].assets[0].sha256 == "abc123"


def test_rate_limit_raises():
    def handler(request):
        return httpx.Response(
            403, json={"message": "rate limit"}, headers={"X-RateLimit-Remaining": "0"}
        )

    with provider_with(handler) as p:
        with pytest.raises(RateLimitError):
            p.fetch_releases(make_app(), token=None)


def test_404_raises_green_error():
    def handler(request):
        return httpx.Response(404, json={"message": "Not Found"})

    with provider_with(handler) as p:
        with pytest.raises(GreenUpdaterError):
            p.fetch_releases(make_app(), token=None)
