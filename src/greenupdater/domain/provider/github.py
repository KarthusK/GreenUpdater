"""GitHub 源适配器（对应 docs/design/02-modules.md §2.1）。

直接调 GitHub REST（不引 PyGithub）：``GET /repos/{owner}/{repo}/releases``。
- include_prerelease=False 时过滤 prerelease，draft 始终过滤
- 支持 token（Authorization: Bearer）与代理
- 限流：命中 403/429 且 X-RateLimit-Remaining=0 → RateLimitError

设计里构造签名写的 ``Downloader | httpx.Client`` 从简为 ``httpx.Client``：Provider 只做
小 JSON 请求，Downloader 负责大文件流式下载，二者关注点不同，不共用。
"""
from __future__ import annotations

import httpx

from greenupdater.models import AppConfig, SourceType

from ..errors import GreenUpdaterError, RateLimitError
from .base import Asset, Release, SourceProvider

_API_BASE = "https://api.github.com"
_DEFAULT_UA = "GreenUpdater/0.1 (+https://github.com/)"


class GitHubProvider(SourceProvider):
    source_type = SourceType.GITHUB

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        proxy: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        # 注入 client 则不拥有它（不负责关闭）；否则自建并持有生命周期
        self._owns_client = client is None
        self._client = client
        self._proxy = proxy
        self._timeout = timeout

    # ---------- 生命周期 ----------
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                proxy=self._proxy, timeout=self._timeout, follow_redirects=True
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "GitHubProvider":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- 抓取 ----------
    def fetch_releases(
        self, app: AppConfig, token: str | None, limit: int = 10
    ) -> list[Release]:
        url = f"{_API_BASE}/repos/{app.repo_owner}/{app.repo_name}/releases"
        params = {"per_page": max(1, min(limit, 100))}
        resp = self._get(url, params, token)
        data = resp.json()
        if not isinstance(data, list):
            raise GreenUpdaterError(f"GitHub 返回非预期结构：{str(data)[:200]}")

        releases: list[Release] = []
        for item in data:
            if item.get("draft"):
                continue
            is_pre = bool(item.get("prerelease"))
            if is_pre and not app.include_prerelease:
                continue
            releases.append(self._to_release(item))
        return releases

    def _get(self, url: str, params: dict, token: str | None) -> httpx.Response:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": _DEFAULT_UA,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self._get_client().get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise GreenUpdaterError(f"请求 GitHub 失败：{exc}") from exc
        self._raise_for_status(resp)
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if resp.status_code == 429 or remaining == "0":
                reset = resp.headers.get("X-RateLimit-Reset", "?")
                raise RateLimitError(f"GitHub API 限流（reset={reset}）")
        if resp.status_code == 404:
            raise GreenUpdaterError("仓库不存在或无访问权限（404）")
        resp.raise_for_status()

    @staticmethod
    def _to_release(item: dict) -> Release:
        assets: list[Asset] = []
        for a in item.get("assets", []) or []:
            assets.append(
                Asset(
                    name=a.get("name", ""),
                    download_url=a.get("browser_download_url", ""),
                    size=a.get("size"),
                    sha256=_parse_digest(a.get("digest")),
                )
            )
        return Release(
            tag_name=item.get("tag_name", ""),
            is_prerelease=bool(item.get("prerelease")),
            published_at=item.get("published_at"),
            assets=assets,
        )


def _parse_digest(digest: str | None) -> str | None:
    """GitHub 的 digest 形如 ``sha256:abc...``；仅提取 sha256。"""
    if not digest:
        return None
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1]
    return None
