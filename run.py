#!/usr/bin/env python3
"""开发态一键启动脚本（跨平台）。

用法::

    python run.py

流程：确保 ``.venv`` 存在 → 用 venv 内的 python 以 editable 方式安装本项目 →
运行 ``python -m greenupdater``。

本脚本用**系统 Python** 运行，内部直接调用 venv 里的解释器（``subprocess``），
因此无需在 shell 中手动“激活”虚拟环境，Windows / Linux / macOS 通用。
"""
from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"


def venv_python() -> Path:
    """返回 venv 内解释器路径（按平台区分）。"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> None:
    py = venv_python()
    if py.exists():
        return
    print(f"[run] 创建虚拟环境: {VENV_DIR}")
    venv.create(str(VENV_DIR), with_pip=True)


def _run(cmd: list[str]) -> int:
    print("[run] " + " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    ensure_venv()
    py = str(venv_python())

    # 安装/更新本项目（editable）。依赖已满足时该步很快。
    code = _run([py, "-m", "pip", "install", "-e", str(ROOT)])
    if code != 0:
        print("[run] 依赖安装失败，请检查网络或 pyproject.toml", file=sys.stderr)
        return code

    # 启动应用
    return _run([py, "-m", "greenupdater"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
