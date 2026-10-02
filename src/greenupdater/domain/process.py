"""进程管理（对应 docs/design/02-modules.md §2.6，psutil）。

find_running 按进程名匹配**且**校验 exe 路径位于 target_dir 下，避免误杀同名进程。
terminate 先优雅 terminate()，超时再 kill()；UI 在调用前弹框确认。
"""
from __future__ import annotations

import os
from pathlib import Path

import psutil


class ProcessManager:
    def find_running(
        self, process_names: list[str], target_dir: Path
    ) -> list[psutil.Process]:
        if not process_names:
            return []
        names = {n.lower() for n in process_names}
        td = _normcase(Path(target_dir).resolve())
        found: list[psutil.Process] = []
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pname = (p.info.get("name") or "").lower()
                if pname not in names:
                    continue
                exe = p.info.get("exe")
                if not exe:
                    continue
                if not _is_under(_normcase(Path(exe).resolve()), td):
                    continue
                found.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                continue
        return found

    def terminate(self, procs: list[psutil.Process], timeout: float = 5.0) -> bool:
        """结束给定进程；返回是否全部退出。失败不抛异常，由编排层映射到 kill_process 阶段。"""
        if not procs:
            return True
        for p in procs:
            try:
                p.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        _, alive = psutil.wait_procs(procs, timeout=timeout)
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        _, still_alive = psutil.wait_procs(alive, timeout=timeout)
        return not still_alive


def _normcase(p: Path) -> str:
    """Windows 大小写不敏感 + 分隔符归一；POSIX 原样。"""
    return os.path.normcase(str(p))


def _is_under(exe: str, target_dir: str) -> bool:
    return exe == target_dir or exe.startswith(target_dir + os.sep)
