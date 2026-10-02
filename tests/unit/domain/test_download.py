"""domain.download 测试：用 httpx.MockTransport，不发真实网络请求。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from greenupdater.domain import CancelToken, Downloader, Progress
from greenupdater.domain.errors import ChecksumError, DownloadError, OperationCancelled

DATA = b"hello-greenupdater-" * 1000
SHA = hashlib.sha256(DATA).hexdigest()


def dl(handler, **kw) -> Downloader:
    kw.setdefault("retries", 0)
    kw.setdefault("backoff", 0)
    return Downloader(client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def ok_handler(content=DATA, status=200, headers=None):
    h = {"Content-Length": str(len(content))}
    if headers:
        h.update(headers)

    def handler(request):
        return httpx.Response(status, content=content, headers=h)

    return handler


def test_download_writes_file(tmp_path: Path):
    dest = tmp_path / "pkg.zip"
    with dl(ok_handler()) as d:
        out = d.download("https://x/pkg.zip", dest)
    assert out == dest
    assert dest.read_bytes() == DATA
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_progress_callbacks(tmp_path: Path):
    seen: list[Progress] = []

    class L:
        def on_log(self, line):
            pass

        def on_progress(self, p):
            seen.append(p)

        def on_stage(self, s):
            pass

        def on_cancelled(self):
            pass

    with dl(ok_handler()) as d:
        d.download("https://x/pkg.zip", tmp_path / "p.zip", listener=L())
    assert seen[-1].percent == 100


def test_sha256_ok(tmp_path: Path):
    with dl(ok_handler()) as d:
        d.download("https://x/p.zip", tmp_path / "p.zip", expected_sha256=SHA)
    assert (tmp_path / "p.zip").read_bytes() == DATA


def test_sha256_mismatch_raises_and_cleans(tmp_path: Path):
    dest = tmp_path / "p.zip"
    with dl(ok_handler()) as d:
        with pytest.raises(ChecksumError):
            d.download("https://x/p.zip", dest, expected_sha256="0" * 64)
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_http_error_raises_download_error(tmp_path: Path):
    with dl(ok_handler(status=404)) as d:
        with pytest.raises(DownloadError):
            d.download("https://x/p.zip", tmp_path / "p.zip")


def test_retry_then_success(tmp_path: Path):
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(500, content=b"err")
        return httpx.Response(200, content=DATA, headers={"Content-Length": str(len(DATA))})

    dest = tmp_path / "p.zip"
    with Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)), retries=3, backoff=0
    ) as d:
        d.download("https://x/p.zip", dest)
    assert dest.read_bytes() == DATA
    assert state["n"] == 3


def test_cancel_raises_operation_cancelled(tmp_path: Path):
    token = CancelToken()
    token.cancel()
    dest = tmp_path / "p.zip"
    with dl(ok_handler()) as d:
        with pytest.raises(OperationCancelled):
            d.download("https://x/p.zip", dest, cancel=token)
    assert not dest.exists()
