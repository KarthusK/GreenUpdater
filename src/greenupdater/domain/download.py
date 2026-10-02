"""下载器（对应 docs/design/02-modules.md §2.4）。

httpx 流式下载到临时目录：磁盘空间预检、进度回调、指数退避重试、协作式取消、
可选 SHA256 校验。进度节流由 UI 层负责，这里每写一块就回调一次。
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

import httpx

from greenupdater.models import UpdateStage

from ._fs import human_size
from .errors import ChecksumError, DownloadError, OperationCancelled
from .events import CancelToken, Progress, UpdateListener

_DEFAULT_UA = "GreenUpdater/0.1 (+https://github.com/)"
_CHUNK = 64 * 1024


class Downloader:
    def __init__(
        self,
        proxy: str | None = None,
        timeout: float = 30.0,
        *,
        client: httpx.Client | None = None,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self._owns_client = client is None
        self._client = client
        self._proxy = proxy
        self._timeout = timeout
        self._retries = max(0, retries)
        self._backoff = backoff

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

    def __enter__(self) -> "Downloader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- 下载 ----------
    def download(
        self,
        url: str,
        dest: Path,
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
        listener: UpdateListener | None = None,
        cancel: CancelToken | None = None,
        headers: dict | None = None,
    ) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        attempt = 0
        while True:
            try:
                return self._download_once(
                    url,
                    dest,
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                    listener=listener,
                    cancel=cancel,
                    headers=headers,
                )
            except (OperationCancelled, ChecksumError):
                raise  # 取消 / 校验失败不重试
            except (httpx.HTTPError, DownloadError) as exc:
                if attempt >= self._retries:
                    raise DownloadError(f"下载失败（重试 {attempt} 次后放弃）：{exc}") from exc
                delay = self._backoff * (2**attempt)
                attempt += 1
                if listener:
                    listener.on_log(f"下载中断，{delay:.1f}s 后第 {attempt} 次重试：{exc}")
                time.sleep(delay)

    def _download_once(
        self,
        url: str,
        dest: Path,
        *,
        expected_size: int | None,
        expected_sha256: str | None,
        listener: UpdateListener | None,
        cancel: CancelToken | None,
        headers: dict | None,
    ) -> Path:
        req_headers = {"User-Agent": _DEFAULT_UA}
        if headers:
            req_headers.update(headers)

        digest = hashlib.sha256()
        downloaded = 0
        tmp_dest = dest.with_suffix(dest.suffix + ".part")
        try:
            with self._get_client().stream("GET", url, headers=req_headers) as resp:
                if resp.status_code >= 400:
                    raise DownloadError(f"HTTP {resp.status_code}：{url}")
                total = expected_size
                cl = resp.headers.get("Content-Length")
                if total is None and cl and cl.isdigit():
                    total = int(cl)
                self._precheck_space(dest, total)

                with open(tmp_dest, "wb") as f:
                    for chunk in resp.iter_bytes(_CHUNK):
                        if cancel is not None and cancel.cancelled:
                            raise OperationCancelled("用户取消下载")
                        if not chunk:
                            continue
                        f.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if listener:
                            listener.on_progress(
                                Progress(
                                    stage=UpdateStage.DOWNLOAD,
                                    percent=self._percent(downloaded, total),
                                    message=self._msg(downloaded, total, dest.name),
                                )
                            )
        except (httpx.HTTPError, DownloadError, OperationCancelled):
            tmp_dest.unlink(missing_ok=True)
            raise
        except OSError as exc:
            tmp_dest.unlink(missing_ok=True)
            raise DownloadError(f"写文件失败：{exc}") from exc

        if expected_sha256:
            actual = digest.hexdigest()
            if actual.lower() != expected_sha256.lower():
                tmp_dest.unlink(missing_ok=True)
                raise ChecksumError(
                    f"SHA256 不符：期望 {expected_sha256[:12]}…，实际 {actual[:12]}…"
                )

        tmp_dest.replace(dest)
        if listener:
            listener.on_progress(
                Progress(
                    stage=UpdateStage.DOWNLOAD,
                    percent=100,
                    message=f"下载完成 {human_size(downloaded)}",
                )
            )
        return dest

    @staticmethod
    def _percent(done: int, total: int | None) -> int:
        if not total or total <= 0:
            return -1
        return max(0, min(100, int(done * 100 / total)))

    @staticmethod
    def _msg(done: int, total: int | None, name: str) -> str:
        if total:
            return f"下载中 {name} {human_size(done)} / {human_size(total)}"
        return f"下载中 {name} {human_size(done)}"

    @staticmethod
    def _precheck_space(dest: Path, total: int | None) -> None:
        """预检磁盘空间：约需 size*2（.part + 最终文件同时存在的余量）。"""
        if not total:
            return
        need = total * 2
        try:
            free = shutil.disk_usage(dest.parent).free
        except OSError:
            return  # 无法探测则跳过预检，交给实际写入时报错
        if free < need:
            raise DownloadError(
                f"磁盘空间不足：需约 {human_size(need)}，可用 {human_size(free)}"
            )
