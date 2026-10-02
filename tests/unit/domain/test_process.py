"""domain.process 测试：真实子进程验证按名+路径匹配与结束，仅操作本测试启动的 pid。"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from greenupdater.domain import ProcessManager


@pytest.fixture()
def pm():
    return ProcessManager()


@pytest.fixture()
def sleeper():
    """启动一个睡 60s 的子进程，测试结束确保清理。"""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    time.sleep(0.4)  # 等进程出现在 process_iter
    yield proc
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)


def test_find_running_no_match(pm, tmp_path: Path):
    assert pm.find_running(["__no_such_process__.exe"], tmp_path) == []


def test_find_running_empty_names(pm, tmp_path: Path):
    assert pm.find_running([], tmp_path) == []


def test_find_running_matches_by_name_and_path(pm, sleeper, tmp_path: Path):
    exe = Path(sys.executable)
    found = pm.find_running([exe.name], exe.parent)
    assert any(p.pid == sleeper.pid for p in found)


def test_find_running_excludes_other_dir(pm, sleeper, tmp_path: Path):
    exe = Path(sys.executable)
    # exe 不在 tmp_path 下 → 不应匹配（即便进程名相同）
    found = pm.find_running([exe.name], tmp_path)
    assert all(p.pid != sleeper.pid for p in found)


def test_terminate_kills_only_target(pm, sleeper):
    exe = Path(sys.executable)
    found = pm.find_running([exe.name], exe.parent)
    target = [p for p in found if p.pid == sleeper.pid]
    assert target, "应能找到本测试启动的子进程"
    assert pm.terminate(target, timeout=5.0) is True
    sleeper.wait(timeout=5)
    assert sleeper.poll() is not None


def test_terminate_empty_returns_true(pm):
    assert pm.terminate([]) is True
