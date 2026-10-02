"""覆盖安装（对应 docs/design/02-modules.md §2.8）。

把解压后的 src_root 覆盖到 target_dir，跳过 exclude_paths（保留用户 config/data）。
覆盖是**唯一会改动目标目录**的阶段，故只有它失败才需要回滚。
v1 语义：只覆盖/新增，不删除新版已移除的旧文件（残留可接受）。
"""
from __future__ import annotations

from pathlib import Path

from greenupdater.models import UpdateStage

from ._fs import copy_tree_skip, dir_size, human_size, is_excluded
from .errors import OverwriteError
from .events import Progress, UpdateListener


class Overwriter:
    def overwrite(
        self,
        src_root: Path,
        target_dir: Path,
        exclude_paths: list[str],
        listener: UpdateListener | None = None,
    ) -> None:
        src_root = Path(src_root)
        target_dir = Path(target_dir)
        if not src_root.is_dir():
            raise OverwriteError(f"解压根目录不存在：{src_root}")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OverwriteError(f"无法创建目标目录：{exc}") from exc

        total = max(1, _count_files(src_root, exclude_paths))
        done = 0

        def on_file(rel, _count):
            nonlocal done
            done += 1
            if listener:
                listener.on_progress(
                    Progress(
                        stage=UpdateStage.OVERWRITE,
                        percent=int(done * 100 / total),
                        message=f"覆盖 {rel}",
                    )
                )

        try:
            copy_tree_skip(src_root, target_dir, exclude_paths, on_file=on_file)
        except OSError as exc:
            raise OverwriteError(f"覆盖文件失败：{exc}") from exc

        if listener:
            listener.on_progress(
                Progress(
                    stage=UpdateStage.OVERWRITE,
                    percent=100,
                    message=f"覆盖完成（{human_size(dir_size(target_dir))}）",
                )
            )


def _count_files(src_root: Path, excludes: list[str]) -> int:
    n = 0
    for f in src_root.rglob("*"):
        if f.is_file() and not is_excluded(f.relative_to(src_root), excludes):
            n += 1
    return n
