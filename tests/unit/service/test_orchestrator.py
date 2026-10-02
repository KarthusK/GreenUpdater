"""service.orchestrator 端到端测试：fake provider + MockTransport 下载 + 真实 domain 组件。"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from greenupdater.domain import (
    Asset,
    CancelToken,
    Downloader,
    Extractor,
    Overwriter,
    ProcessManager,
    Release,
    SourceProvider,
    VersionResolver,
    LocalVersionDetector,
)
from greenupdater.domain.backup import BackupManager
from greenupdater.domain.errors import OverwriteError
from greenupdater.infra import ConfigRepository, Paths
from greenupdater.models import (
    AppConfig,
    AppStatus,
    SourceType,
    UpdateResult,
    UpdateStage,
)
from greenupdater.service import UpdateOrchestrator

# ---------- 测试替身 ----------


class FakeProvider(SourceProvider):
    source_type = SourceType.GITHUB

    def __init__(self, releases: list[Release]):
        self._releases = releases

    def fetch_releases(self, app, token, limit=10):
        return self._releases


class FakeTokens:
    def get(self):
        return None


class RecordingListener:
    def __init__(self):
        self.logs: list[str] = []
        self.stages: list[tuple] = []
        self.cancelled = False

    def on_log(self, line):
        self.logs.append(line)

    def on_progress(self, p):
        pass

    def on_stage(self, s):
        self.stages.append((s.stage, s.ok, s.error))

    def on_cancelled(self):
        self.cancelled = True


class BreakingOverwriter:
    """写坏目标后抛 OverwriteError，用于验证覆盖失败 → 可回滚。"""

    def overwrite(self, src_root, target_dir, exclude_paths, listener=None):
        (Path(target_dir) / "app.exe").write_text("BROKEN")
        raise OverwriteError("模拟覆盖失败")


class FakeProcMgr:
    def __init__(self, procs):
        self._procs = procs

    def find_running(self, names, target_dir):
        return self._procs

    def terminate(self, procs, timeout=5.0):
        return True


# ---------- 构造 ----------


def build_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, c in files.items():
            zf.writestr(n, c)
    return buf.getvalue()


def make_release(tag="v2.0.0", asset_name="app-2.0.0-win.zip", size=None, sha=None):
    return Release(
        tag_name=tag,
        is_prerelease=False,
        published_at="2026-01-01T00:00:00Z",
        assets=[
            Asset(name=asset_name, download_url=f"https://dl/{asset_name}", size=size, sha256=sha)
        ],
    )


def make_orchestrator(
    tmp_path: Path,
    *,
    zip_bytes: bytes,
    releases=None,
    overwriter=None,
    procmgr=None,
    download_status=200,
    current_version="1.0.0",
    backup_enabled=True,
):
    paths = Paths(tmp_path / "portable")
    paths.ensure_dirs()
    repo = ConfigRepository(tmp_path / "test.db")

    target = tmp_path / "target"
    cfg = AppConfig(
        name="TestApp",
        repo_owner="o",
        repo_name="r",
        asset_pattern=r".*\.zip",
        version_pattern=r"v?([\d.]+)",
        target_dir=target,
        exe_relpath="app.exe",
        exclude_paths=["config"],
        backup_enabled=backup_enabled,
    )
    app = repo.upsert_app(cfg)
    app.current_version = current_version
    repo.save_state(app)

    def handler(request):
        return httpx.Response(
            download_status,
            content=zip_bytes,
            headers={"Content-Length": str(len(zip_bytes))},
        )

    downloader = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0, backoff=0
    )
    orch = UpdateOrchestrator(
        repo=repo,
        provider=FakeProvider(releases if releases is not None else [make_release()]),
        resolver=VersionResolver(),
        detector=LocalVersionDetector(),
        downloader=downloader,
        extractor=Extractor(),
        procmgr=procmgr or ProcessManager(),
        backup=BackupManager(paths),
        overwriter=overwriter or Overwriter(),
        tokens=FakeTokens(),
        paths=paths,
    )
    return orch, repo, paths, app, target


def seed_target(target: Path):
    (target / "config").mkdir(parents=True)
    (target / "app.exe").write_text("v1-prog")
    (target / "config" / "user.cfg").write_text("v1-user")


# ---------- 测试 ----------


def test_check_update_available(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(tmp_path, zip_bytes=build_zip({"app.exe": "v2"}))
    seed_target(target)
    res = orch.check(app, RecordingListener())
    assert res.update_available is True
    assert res.latest_version == "2.0.0"
    assert repo.get_app(app.uid).last_status == AppStatus.UPDATE_AVAILABLE


def test_update_success(tmp_path: Path):
    orch, repo, paths, app, target = make_orchestrator(
        tmp_path, zip_bytes=build_zip({"app.exe": "v2-prog"})
    )
    seed_target(target)
    listener = RecordingListener()
    outcome = orch.update(app, listener, CancelToken(), lambda p: True, lambda c: c[0])

    assert outcome.result == UpdateResult.SUCCESS
    assert outcome.to_version == "2.0.0"
    assert (target / "app.exe").read_text() == "v2-prog"
    # 排除路径下用户数据保留
    assert (target / "config" / "user.cfg").read_text() == "v1-user"
    got = repo.get_app(app.uid)
    assert got.last_status == AppStatus.SUCCESS
    assert got.current_version == "2.0.0"
    assert got.rollback_available is False
    # 历史写入
    hist = repo.list_history(app.uid)
    assert len(hist) == 1
    assert hist[0].result == UpdateResult.SUCCESS
    assert hist[0].to_version == "2.0.0"
    # 临时目录清理
    assert not paths.tmp(app.uid).exists()


def test_update_already_up_to_date(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(
        tmp_path, zip_bytes=build_zip({"app.exe": "v2"}), current_version="2.0.0"
    )
    seed_target(target)
    outcome = orch.update(app, RecordingListener(), CancelToken(), lambda p: True, lambda c: c[0])
    assert outcome.result == UpdateResult.SUCCESS
    # 未覆盖
    assert (target / "app.exe").read_text() == "v1-prog"
    assert repo.get_app(app.uid).last_status == AppStatus.UP_TO_DATE
    assert repo.list_history(app.uid) == []


def test_update_download_failure(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(
        tmp_path, zip_bytes=b"x", download_status=500
    )
    seed_target(target)
    outcome = orch.update(app, RecordingListener(), CancelToken(), lambda p: True, lambda c: c[0])
    assert outcome.result == UpdateResult.FAILED
    assert outcome.failed_stage == UpdateStage.DOWNLOAD
    assert outcome.rollback_available is False
    # 目标未被改动
    assert (target / "app.exe").read_text() == "v1-prog"
    got = repo.get_app(app.uid)
    assert got.last_status == AppStatus.FAILED
    assert got.last_error_stage == UpdateStage.DOWNLOAD
    assert repo.list_history(app.uid)[0].result == UpdateResult.FAILED


def test_update_overwrite_failure_enables_rollback(tmp_path: Path):
    orch, repo, paths, app, target = make_orchestrator(
        tmp_path,
        zip_bytes=build_zip({"app.exe": "v2"}),
        overwriter=BreakingOverwriter(),
    )
    seed_target(target)
    outcome = orch.update(app, RecordingListener(), CancelToken(), lambda p: True, lambda c: c[0])
    assert outcome.result == UpdateResult.FAILED
    assert outcome.failed_stage == UpdateStage.OVERWRITE
    assert outcome.rollback_available is True
    assert (target / "app.exe").read_text() == "BROKEN"
    assert repo.get_app(app.uid).rollback_available is True


def test_rollback_restores_previous(tmp_path: Path):
    orch, repo, paths, app, target = make_orchestrator(
        tmp_path,
        zip_bytes=build_zip({"app.exe": "v2"}),
        overwriter=BreakingOverwriter(),
    )
    seed_target(target)
    orch.update(app, RecordingListener(), CancelToken(), lambda p: True, lambda c: c[0])
    assert (target / "app.exe").read_text() == "BROKEN"

    app = repo.get_app(app.uid)  # 取回带 rollback_available 的状态
    outcome = orch.rollback(app, RecordingListener())
    assert outcome.result == UpdateResult.SUCCESS
    # 程序文件还原到快照版本
    assert (target / "app.exe").read_text() == "v1-prog"
    # 用户数据保留
    assert (target / "config" / "user.cfg").read_text() == "v1-user"
    got = repo.get_app(app.uid)
    assert got.rollback_available is False
    assert got.last_status == AppStatus.SUCCESS
    # 最近一条历史标记为已回滚
    assert repo.list_history(app.uid)[0].rolled_back is True


def test_rollback_without_snapshot_fails(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(
        tmp_path, zip_bytes=build_zip({"app.exe": "v2"}), backup_enabled=False
    )
    seed_target(target)
    outcome = orch.rollback(app, RecordingListener())
    assert outcome.result == UpdateResult.FAILED
    assert "无可用快照" in (outcome.error or "")


def test_cancel_before_start(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(
        tmp_path, zip_bytes=build_zip({"app.exe": "v2"})
    )
    seed_target(target)
    token = CancelToken()
    token.cancel()
    listener = RecordingListener()
    outcome = orch.update(app, listener, token, lambda p: True, lambda c: c[0])
    assert outcome.result == UpdateResult.CANCELLED
    assert listener.cancelled is True
    assert (target / "app.exe").read_text() == "v1-prog"
    assert repo.list_history(app.uid) == []


def test_confirm_kill_declined_cancels(tmp_path: Path):
    orch, repo, _, app, target = make_orchestrator(
        tmp_path,
        zip_bytes=build_zip({"app.exe": "v2"}),
        procmgr=FakeProcMgr(procs=["fake-proc"]),
    )
    seed_target(target)
    listener = RecordingListener()
    outcome = orch.update(
        app, listener, CancelToken(), confirm_kill=lambda p: False, choose_asset=lambda c: c[0]
    )
    assert outcome.result == UpdateResult.CANCELLED
    assert listener.cancelled is True
    # 未覆盖
    assert (target / "app.exe").read_text() == "v1-prog"


def test_update_all_continues_after_failure(tmp_path: Path):
    paths = Paths(tmp_path / "portable")
    paths.ensure_dirs()
    repo = ConfigRepository(tmp_path / "test.db")
    zip_bytes = build_zip({"app.exe": "v2"})

    t1 = tmp_path / "t1"
    t2 = tmp_path / "t2"
    a1 = repo.upsert_app(
        AppConfig(name="A1", repo_owner="o", repo_name="r", asset_pattern=r".*\.zip",
                  version_pattern=r"v?([\d.]+)", target_dir=t1, exe_relpath="app.exe")
    )
    a2 = repo.upsert_app(
        AppConfig(name="A2", repo_owner="o", repo_name="r", asset_pattern=r".*\.zip",
                  version_pattern=r"v?([\d.]+)", target_dir=t2, exe_relpath="app.exe")
    )
    for a, t in ((a1, t1), (a2, t2)):
        a.current_version = "1.0.0"
        repo.save_state(a)
        (t).mkdir(parents=True)
        (t / "app.exe").write_text("v1")

    def handler(request):
        return httpx.Response(200, content=zip_bytes, headers={"Content-Length": str(len(zip_bytes))})

    orch = UpdateOrchestrator(
        repo=repo,
        provider=FakeProvider([make_release()]),
        resolver=VersionResolver(),
        detector=LocalVersionDetector(),
        downloader=Downloader(client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0, backoff=0),
        extractor=Extractor(),
        procmgr=ProcessManager(),
        backup=BackupManager(paths),
        overwriter=Overwriter(),
        tokens=FakeTokens(),
        paths=paths,
    )
    outcomes = orch.update_all(
        [a1, a2], RecordingListener(), CancelToken(), lambda p: True, lambda c: c[0]
    )
    assert len(outcomes) == 2
    assert all(o.result == UpdateResult.SUCCESS for o in outcomes)
    assert (t1 / "app.exe").read_text() == "v2"
    assert (t2 / "app.exe").read_text() == "v2"
