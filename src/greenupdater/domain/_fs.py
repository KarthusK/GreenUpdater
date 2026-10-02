"""domain 内部文件系统工具：BackupManager.rollback 与 Overwriter 共用。

不对外导出（下划线模块），只服务 domain 内部，避免重复实现"跳过排除路径拷贝"。
"""
from __future__ import annotations

import shutil
from pathlib import Path, PurePath
from typing import Callable


def is_excluded(rel: PurePath, excludes: list[str]) -> bool:
    """rel 是否落在任一排除路径下（如 config、data）。"""
    parts = rel.parts
    for e in excludes:
        ep = PurePath(e).parts
        if ep and parts[: len(ep)] == ep:
            return True
    return False


def copy_tree_skip(
    src_root: Path,
    dst_root: Path,
    excludes: list[str],
    *,
    on_file: Callable[[PurePath, int], None] | None = None,
) -> int:
    """把 src_root 内文件拷到 dst_root，跳过 excludes。只新增/覆盖，不删除。

    返回实际拷贝的文件数。on_file(rel, 累计数) 用于进度回调。
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)
    count = 0
    for f in src_root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src_root)
        if is_excluded(rel, excludes):
            continue
        target = dst_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        count += 1
        if on_file is not None:
            on_file(rel, count)
    return count


def dir_size(path: Path) -> int:
    """目录内所有文件的总字节数（不含无法访问项）。"""
    total = 0
    p = Path(path)
    if not p.exists():
        return 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def human_size(n: float) -> str:
    """字节数转人类可读（下载/覆盖进度消息共用）。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"
