"""更新编排（对应 docs/design/02-modules.md §3.1/§3.2）。

UI 唯一直接调用的业务入口。串起整条流水线，**顺序执行**，一次一个 app。
领域核心不依赖 GUI：``confirm_kill`` / ``choose_asset`` 由 UI 注入，listener 汇报进度。

阶段顺序（总览 §3.3）：
    check → download(tmp) → extract(tmp) → [运行中: confirm_kill→terminate]
    → [backup_enabled: create_snapshot] → overwrite
失败**不自动回滚**；仅覆盖阶段失败且有快照时置 rollback_available，由用户手动回滚。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from loguru import logger

from greenupdater.domain import (
    Asset,
    AssetMatcher,
    BackupManager,
    CancelToken,
    Downloader,
    Extractor,
    GreenUpdaterError,
    LocalVersionDetector,
    NoAssetMatchedError,
    OperationCancelled,
    Overwriter,
    ProcessKillError,
    ProcessManager,
    Release,
    SourceProvider,
    StageResult,
    UpdateListener,
    VersionResolver,
)
from greenupdater.infra import ConfigRepository, Paths, TokenStore
from greenupdater.models import (
    App,
    AppStatus,
    UpdateRecord,
    UpdateResult,
    UpdateStage,
)

#: check 时拉取的发布数量上限
_RELEASE_LIMIT = 10


@dataclass
class CheckResult:
    app_uid: str
    latest_version: str | None
    update_available: bool
    error: str | None = None


@dataclass
class UpdateOutcome:
    app_uid: str
    result: UpdateResult
    from_version: str | None
    to_version: str | None
    failed_stage: UpdateStage | None = None
    error: str | None = None
    rollback_available: bool = False


class UpdateOrchestrator:
    def __init__(
        self,
        repo: ConfigRepository,
        provider: SourceProvider,
        resolver: VersionResolver,
        detector: LocalVersionDetector,
        downloader: Downloader,
        extractor: Extractor,
        procmgr: ProcessManager,
        backup: BackupManager,
        overwriter: Overwriter,
        tokens: TokenStore,
        paths: Paths,
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._resolver = resolver
        self._detector = detector
        self._downloader = downloader
        self._extractor = extractor
        self._procmgr = procmgr
        self._backup = backup
        self._overwriter = overwriter
        self._tokens = tokens
        self._paths = paths
        self._matcher = AssetMatcher()

    # =====================================================================
    # 检查
    # =====================================================================
    def check(self, app: App, listener: UpdateListener) -> CheckResult:
        """只读检查，不改动任何文件。"""
        self._log(listener, f"[检查] {app.name}（{app.repo}）")
        stage = UpdateStage.CHECK
        try:
            resolved = self._resolve_latest(app, choose=lambda c: c[0])
            if resolved is None:
                raise NoAssetMatchedError(
                    f"没有匹配 /{app.asset_pattern}/ 的发布资产"
                )
            release, asset, remote_ver = resolved
        except GreenUpdaterError as exc:
            return self._check_failed(app, stage, exc, listener)

        app.latest_version = remote_ver
        avail = self._resolver.is_update_available(app.current_version, remote_ver)
        app.last_status = AppStatus.UPDATE_AVAILABLE if avail else AppStatus.UP_TO_DATE
        app.last_error_stage = None
        app.last_error_message = None
        self._repo.save_state(app)
        listener.on_stage(StageResult(stage, True))
        self._log(
            listener,
            f"[检查] {app.name}: 本地 {app.current_version or '未知'} → "
            f"最新 {remote_ver}（{'有更新' if avail else '已最新'}）",
        )
        return CheckResult(app.uid, remote_ver, avail)

    def check_all(self, apps: list[App], listener: UpdateListener) -> list[CheckResult]:
        results = []
        for app in apps:
            results.append(self.check(app, listener))
        return results

    def _check_failed(
        self, app: App, stage: UpdateStage, exc: GreenUpdaterError, listener: UpdateListener
    ) -> CheckResult:
        msg = str(exc)
        app.last_status = AppStatus.FAILED
        app.last_error_stage = stage
        app.last_error_message = msg
        self._repo.save_state(app)
        listener.on_stage(StageResult(stage, False, msg))
        self._log(listener, f"[检查失败] {app.name}: {msg}")
        logger.warning(f"check failed for {app.name}: {msg}")
        return CheckResult(app.uid, None, False, error=msg)

    # =====================================================================
    # 更新
    # =====================================================================
    def update(
        self,
        app: App,
        listener: UpdateListener,
        cancel: CancelToken,
        confirm_kill: Callable[[list], bool],
        choose_asset: Callable[[list[Asset]], "Asset | None"],
    ) -> UpdateOutcome:
        started = datetime.now(timezone.utc)
        from_version = app.current_version
        to_version: str | None = None
        stage = UpdateStage.CHECK

        app.last_status = AppStatus.UPDATING
        self._repo.save_state(app)
        tmp = self._paths.tmp(app.uid)

        try:
            # ---- CHECK ----
            self._raise_if_cancelled(cancel)
            self._log(listener, f"[更新] {app.name} 开始")
            resolved = self._resolve_latest(app, choose_asset)
            if resolved is None:
                raise NoAssetMatchedError(f"没有匹配 /{app.asset_pattern}/ 的发布资产")
            release, asset, to_version = resolved
            app.latest_version = to_version
            listener.on_stage(StageResult(UpdateStage.CHECK, True))

            if not self._resolver.is_update_available(from_version, to_version):
                app.last_status = AppStatus.UP_TO_DATE
                app.last_error_stage = None
                app.last_error_message = None
                self._repo.save_state(app)
                self._log(listener, f"[更新] {app.name} 已是最新（{to_version}），跳过")
                return UpdateOutcome(
                    app.uid, UpdateResult.SUCCESS, from_version, to_version
                )

            # ---- DOWNLOAD ----
            self._raise_if_cancelled(cancel)
            stage = UpdateStage.DOWNLOAD
            tmp.mkdir(parents=True, exist_ok=True)
            pkg = tmp / Path(asset.name).name
            self._log(listener, f"[下载] {asset.name}")
            self._downloader.download(
                asset.download_url,
                pkg,
                expected_size=asset.size,
                expected_sha256=asset.sha256,
                listener=listener,
                cancel=cancel,
            )
            listener.on_stage(StageResult(UpdateStage.DOWNLOAD, True))

            # ---- EXTRACT ----
            self._raise_if_cancelled(cancel)
            stage = UpdateStage.EXTRACT
            ex_dir = tmp / "extracted"
            self._extractor.extract(pkg, ex_dir, listener)
            root = self._extractor.locate_root(ex_dir, app.exe_relpath)
            listener.on_stage(StageResult(UpdateStage.EXTRACT, True))

            # ---- KILL PROCESS ----
            self._raise_if_cancelled(cancel)
            stage = UpdateStage.KILL_PROCESS
            procs = self._procmgr.find_running(app.process_names, app.target_dir)
            if procs:
                if not confirm_kill(procs):
                    raise OperationCancelled("用户拒绝结束进程")
                if not self._procmgr.terminate(procs):
                    raise ProcessKillError("部分进程无法结束")
            listener.on_stage(StageResult(UpdateStage.KILL_PROCESS, True))

            # ---- SNAPSHOT ----
            self._raise_if_cancelled(cancel)
            stage = UpdateStage.SNAPSHOT
            if app.backup_enabled:
                self._log(listener, "[快照] 创建完整备份")
                self._backup.create_snapshot(app, listener)
            listener.on_stage(StageResult(UpdateStage.SNAPSHOT, True))

            # ---- OVERWRITE ----
            self._raise_if_cancelled(cancel)
            stage = UpdateStage.OVERWRITE
            self._log(listener, f"[覆盖] → {app.target_dir}")
            self._overwriter.overwrite(
                root, Path(app.target_dir), app.exclude_paths, listener
            )
            listener.on_stage(StageResult(UpdateStage.OVERWRITE, True))

            # ---- SUCCESS ----
            return self._finish_success(
                app, listener, started, from_version, to_version, asset
            )

        except OperationCancelled as exc:
            self._cleanup(tmp)
            app.last_status = AppStatus.UNKNOWN
            self._repo.save_state(app)
            listener.on_cancelled()
            self._log(listener, f"[取消] {app.name}: {exc}")
            return UpdateOutcome(
                app.uid, UpdateResult.CANCELLED, from_version, to_version, error=str(exc)
            )
        except GreenUpdaterError as exc:
            self._cleanup(tmp)
            return self._finish_failure(
                app, listener, started, from_version, to_version, asset=None,
                stage=stage, exc=exc,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底，任何意外都归到当前阶段
            self._cleanup(tmp)
            logger.exception(f"update crashed for {app.name}")
            return self._finish_failure(
                app, listener, started, from_version, to_version, asset=None,
                stage=stage, exc=GreenUpdaterError(str(exc)),
            )

    def update_all(
        self,
        apps: list[App],
        listener: UpdateListener,
        cancel: CancelToken,
        confirm_kill: Callable[[list], bool],
        choose_asset: Callable[[list[Asset]], "Asset | None"],
    ) -> list[UpdateOutcome]:
        """逐个顺序执行；单个失败不阻断其余；用户取消则停止后续。"""
        outcomes: list[UpdateOutcome] = []
        for app in apps:
            if cancel.cancelled:
                self._log(listener, "[跳过] 已取消，剩余软件不再处理")
                break
            outcomes.append(
                self.update(app, listener, cancel, confirm_kill, choose_asset)
            )
        return outcomes

    # =====================================================================
    # 回滚（用户手动触发）
    # =====================================================================
    def rollback(self, app: App, listener: UpdateListener) -> UpdateOutcome:
        self._log(listener, f"[回滚] {app.name}")
        if not self._backup.has_snapshot(app):
            msg = "无可用快照，无法回滚"
            app.last_status = AppStatus.FAILED
            app.last_error_stage = UpdateStage.OVERWRITE
            app.last_error_message = msg
            app.rollback_available = False
            self._repo.save_state(app)
            listener.on_stage(StageResult(UpdateStage.OVERWRITE, False, msg))
            return UpdateOutcome(
                app.uid, UpdateResult.FAILED, app.current_version, None,
                UpdateStage.OVERWRITE, msg, False,
            )

        started = datetime.now(timezone.utc)
        try:
            procs = self._procmgr.find_running(app.process_names, app.target_dir)
            if procs:
                self._procmgr.terminate(procs)
            self._backup.rollback(app, listener)
        except GreenUpdaterError as exc:
            msg = str(exc)
            app.last_status = AppStatus.FAILED
            app.last_error_message = msg
            self._repo.save_state(app)
            listener.on_stage(StageResult(UpdateStage.OVERWRITE, False, msg))
            self._log(listener, f"[回滚失败] {app.name}: {msg}")
            return UpdateOutcome(
                app.uid, UpdateResult.FAILED, app.current_version, None,
                UpdateStage.OVERWRITE, msg, True,
            )

        # 回滚成功：重新探测本地版本
        detected, src = self._detector.detect(Path(app.target_dir), app.exe_relpath)
        if detected:
            app.current_version = detected
            app.current_version_src = src
        app.last_status = AppStatus.SUCCESS
        app.last_error_stage = None
        app.last_error_message = None
        app.rollback_available = False
        self._repo.save_state(app)
        self._repo.mark_rolled_back(app.uid)
        listener.on_stage(StageResult(UpdateStage.OVERWRITE, True))
        self._log(listener, f"[回滚完成] {app.name} → {app.current_version or '未知'}")
        return UpdateOutcome(
            app.uid, UpdateResult.SUCCESS, app.current_version, app.current_version
        )

    # =====================================================================
    # 内部
    # =====================================================================
    def _resolve_latest(
        self, app: App, choose: Callable[[list[Asset]], "Asset | None"]
    ) -> tuple[Release, Asset, str] | None:
        """按新到旧遍历发布，返回第一个能匹配资产且能提取版本的 (release, asset, version)。"""
        token = self._tokens.get()
        releases = self._provider.fetch_releases(app, token, limit=_RELEASE_LIMIT)
        for release in releases:
            try:
                asset = self._matcher.match(release, app.asset_pattern, choose)
            except NoAssetMatchedError:
                continue
            version = self._resolver.extract(release, asset, app) or release.tag_name
            if not version:
                continue
            return release, asset, version
        return None

    def _finish_success(
        self,
        app: App,
        listener: UpdateListener,
        started: datetime,
        from_version: str | None,
        to_version: str | None,
        asset: Asset,
    ) -> UpdateOutcome:
        self._cleanup(self._paths.tmp(app.uid))
        app.current_version = to_version
        app.last_status = AppStatus.SUCCESS
        app.last_error_stage = None
        app.last_error_message = None
        app.rollback_available = False  # 成功后不提供回滚（总览 §3.4）
        self._repo.save_state(app)
        self._write_history(
            app, started, from_version, to_version, asset,
            UpdateResult.SUCCESS, None, None,
        )
        self._log(listener, f"[成功] {app.name}: {from_version or '未知'} → {to_version}")
        return UpdateOutcome(app.uid, UpdateResult.SUCCESS, from_version, to_version)

    def _finish_failure(
        self,
        app: App,
        listener: UpdateListener,
        started: datetime,
        from_version: str | None,
        to_version: str | None,
        asset: Asset | None,
        stage: UpdateStage,
        exc: GreenUpdaterError,
    ) -> UpdateOutcome:
        msg = str(exc)
        rollback_available = stage == UpdateStage.OVERWRITE and self._backup.has_snapshot(app)
        app.last_status = AppStatus.FAILED
        app.last_error_stage = stage
        app.last_error_message = msg
        app.rollback_available = rollback_available
        self._repo.save_state(app)
        listener.on_stage(StageResult(stage, False, msg))
        self._write_history(
            app, started, from_version, to_version, asset,
            UpdateResult.FAILED, stage, msg,
        )
        self._log(listener, f"[失败] {app.name} @ {stage.value}: {msg}")
        if rollback_available:
            self._log(listener, f"[提示] {app.name} 覆盖失败，可右键手动回滚")
        logger.warning(f"update failed for {app.name} at {stage.value}: {msg}")
        return UpdateOutcome(
            app.uid, UpdateResult.FAILED, from_version, to_version,
            stage, msg, rollback_available,
        )

    def _write_history(
        self,
        app: App,
        started: datetime,
        from_version: str | None,
        to_version: str | None,
        asset: Asset | None,
        result: UpdateResult,
        failed_stage: UpdateStage | None,
        error: str | None,
    ) -> None:
        rec = UpdateRecord(
            app_id=app.id,
            from_version=from_version,
            to_version=to_version,
            asset_name=asset.name if asset else None,
            asset_size=asset.size if asset else None,
            sha256=asset.sha256 if asset else None,
            result=result,
            failed_stage=failed_stage,
            error_message=error,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
        self._repo.add_history(rec)

    def _cleanup(self, tmp: Path) -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _raise_if_cancelled(cancel: CancelToken) -> None:
        if cancel.cancelled:
            raise OperationCancelled("用户取消")

    @staticmethod
    def _log(listener: UpdateListener, line: str) -> None:
        listener.on_log(line)
        logger.info(line)
