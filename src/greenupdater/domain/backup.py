"""快照 / 回滚（对应 docs/design/02-modules.md §2.7、总览 §3.5）。

- create_snapshot：完整拷贝 target_dir → backups/<uid>/（含用户数据），每软件仅 1 份
- rollback：用快照还原**程序文件**，但跳过 exclude_paths（保留当前用户数据）
- 快照放 GreenUpdater 自身便携目录（paths.backups_root），随软件一起迁移
"""
from __future__ import annotations

import shutil
from pathlib import Path

from greenupdater.infra import Paths
from greenupdater.models import App, UpdateStage

from ._fs import copy_tree_skip, dir_size, human_size
from .errors import SnapshotError
from .events import Progress, UpdateListener


class BackupManager:
    def __init__(self, paths: Paths) -> None:
        self._paths = paths

    # ---------- 查询 ----------
    def snapshot_dir(self, app: App) -> Path:
        return self._paths.backups(app.uid)

    def has_snapshot(self, app: App) -> bool:
        d = self.snapshot_dir(app)
        return d.is_dir() and any(d.iterdir())

    # ---------- 创建快照 ----------
    def create_snapshot(self, app: App, listener: UpdateListener | None = None) -> Path:
        target = Path(app.target_dir)
        dest = self.snapshot_dir(app)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # 每软件仅保留 1 份：先清旧
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

        if not target.is_dir():
            # 全新安装：目标目录尚不存在，无内容可快照（has_snapshot 将为 False）
            dest.mkdir(parents=True, exist_ok=True)
            return dest

        self._precheck_space(target, dest)

        if listener:
            listener.on_progress(
                Progress(
                    stage=UpdateStage.SNAPSHOT,
                    percent=-1,
                    message=f"创建完整快照 {human_size(dir_size(target))}",
                )
            )
        try:
            shutil.copytree(target, dest, symlinks=True)
        except OSError as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise SnapshotError(f"创建快照失败：{exc}") from exc

        if listener:
            listener.on_progress(
                Progress(stage=UpdateStage.SNAPSHOT, percent=100, message="快照完成")
            )
        return dest

    # ---------- 回滚 ----------
    def rollback(self, app: App, listener: UpdateListener | None = None) -> None:
        """用快照还原程序文件到 target_dir，跳过 exclude_paths（保留当前用户数据）。"""
        if not self.has_snapshot(app):
            raise SnapshotError("无可用快照，无法回滚")
        src = self.snapshot_dir(app)
        target = Path(app.target_dir)
        target.mkdir(parents=True, exist_ok=True)

        total = max(1, _count_files(src, app.exclude_paths))
        done = 0

        def on_file(rel, _n):
            nonlocal done
            done += 1
            if listener:
                listener.on_progress(
                    Progress(
                        stage=UpdateStage.OVERWRITE,
                        percent=int(done * 100 / total),
                        message=f"回滚 {rel}",
                    )
                )

        try:
            copy_tree_skip(src, target, app.exclude_paths, on_file=on_file)
        except OSError as exc:
            raise SnapshotError(f"回滚失败：{exc}") from exc

        if listener:
            listener.on_progress(
                Progress(stage=UpdateStage.OVERWRITE, percent=100, message="回滚完成")
            )

    # ---------- 删除 ----------
    def delete_snapshot(self, app: App) -> None:
        shutil.rmtree(self.snapshot_dir(app), ignore_errors=True)

    # ---------- 内部 ----------
    @staticmethod
    def _precheck_space(target: Path, dest_parent: Path) -> None:
        need = dir_size(target)
        if need == 0:
            return
        try:
            free = shutil.disk_usage(dest_parent.parent).free
        except OSError:
            return
        if free < need:
            raise SnapshotError(
                f"磁盘空间不足：快照需约 {human_size(need)}，可用 {human_size(free)}"
            )


def _count_files(root: Path, excludes: list[str]) -> int:
    from ._fs import is_excluded

    n = 0
    for f in root.rglob("*"):
        if f.is_file() and not is_excluded(f.relative_to(root), excludes):
            n += 1
    return n
