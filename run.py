#!/usr/bin/env python3
"""开发态一键启动脚本（跨平台）。

用法::

    python run.py
    python run.py --reinstall

流程：确保 ``.venv`` 存在 → 检查项目变更指纹，若 ``pyproject.toml`` 哈希未变则跳过安装、直接启动；否则以 editable 方式重新安装本项目 →
运行 ``python -m greenupdater``。

本脚本用**系统 Python** 运行，内部直接调用 venv 里的解释器（``subprocess``），
因此无需在 shell 中手动“激活”虚拟环境，Windows / Linux / macOS 通用。
"""
from __future__ import annotations

import hashlib
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
    print(f"[run] 创建虚拟环境：{VENV_DIR}")
    venv.create(str(VENV_DIR), with_pip=True)


def _run(cmd: list[str]) -> int:
    print("[run] " + " ".join(cmd))
    return subprocess.call(cmd)


def _dist_info_exists() -> bool:
    """快速检测绿色更新器是否已安装：查找 site-packages 下的 dist-info 目录。"""
    site_packages = VENV_DIR / "Lib" / "site-packages"
    for p in site_packages.glob("greenupdater-*.dist-info"):
        return True
    return False


def _needs_reinstall() -> bool:
    """判断是否需要重装：pyproject.toml 哈希 vs 缓存指纹，或 dist-info 缺失。"""
    # 先检查 dist-info（最轻）
    if not _dist_info_exists():
        return True
    # 再比较 pyproject.toml 的哈希
    stamp = ROOT / "tmp" / ".run_install_stamp"
    new_hash = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    return stamp.read_text(encoding="utf-8") != new_hash if stamp.exists() else True


def main() -> None:
    ensure_venv()
    py = str(venv_python())

    # 解析命令行参数：--reinstall 强制重装
    reinstall = "--reinstall" in sys.argv
    sys.argv.remove("--reinstall")

    if reinstall or _needs_reinstall():
        code = _run([py, "-m", "pip", "install", "-e", str(ROOT)])
        if code != 0:
            print("[run] 依赖安装失败，请检查网络或 pyproject.toml", file=sys.stderr)
            sys.exit(code)
        # 写入指纹（确保 tmp/ 目录存在）
        TMP_DIR = ROOT / "tmp"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        new_hash = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
        (TMP_DIR / ".run_install_stamp").write_text(new_hash, encoding="utf-8")

    # 启动应用
    _run([py, "-m", "greenupdater"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)