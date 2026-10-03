#!/usr/bin/env python3
"""一键打包脚本（跨平台），调用 Nuitka 生成可执行文件。

用法::

    python build.py             # standalone（文件夹，杀软误报少，推荐）
    python build.py --onefile   # 单文件（分发方便，误报率较高）

产物输出到 ``build/``。可执行名固定为 ``GreenUpdater``（Windows 加 ``.exe``）。
平台差异（图标、控制台、产物后缀）在脚本内用 ``sys.platform`` 分支处理。

注意：Nuitka 的少量参数名在不同版本间可能微调；若某参数不被识别，
按当前 Nuitka 版本文档调整 ``build_cmd()`` 即可，其余逻辑不受影响。
"""
from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
ENTRY = ROOT / "src" / "greenupdater" / "__main__.py"
OUTPUT_DIR = ROOT / "build"
ICON = ROOT / "src" / "greenupdater" / "ui" / "app.ico"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_env() -> str:
    """确保 venv 存在，并安装本项目与 Nuitka；返回 venv 内 python 路径。"""
    py = venv_python()
    if not py.exists():
        print(f"[build] 创建虚拟环境: {VENV_DIR}")
        venv.create(str(VENV_DIR), with_pip=True)
    pys = str(py)
    subprocess.check_call([pys, "-m", "pip", "install", "-e", str(ROOT)])
    subprocess.check_call([pys, "-m", "pip", "install", "nuitka>=2.3"])
    return pys


def build_cmd(py: str, onefile: bool) -> list[str]:
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    cmd = [
        py, "-m", "nuitka",
        "--onefile" if onefile else "--standalone",
        "--enable-plugin=pyside6",
        "--include-package=greenupdater",
        "--include-package=keyring",
        "--include-package=keyring.backends",  # keyring 后端靠 entry points 发现，需显式包含
        "--include-package=py7zr",             # py7zr 依赖较多，显式包含
        "--include-package-data=greenupdater",  # 打入 ui/theme.qss、ui/icons/、ui/app.ico 等包数据
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename=GreenUpdater{exe_suffix}",
        "--assume-yes-for-downloads",
    ]
    if sys.platform == "win32":
        cmd.append("--windows-console-mode=disable")  # GUI 程序，应用内已有终端面板
        # 图标缺失必须显式失败：早前此处用 ICON.exists() 静默跳过，
        # 路径写错导致打包产物长期没有图标却无人察觉
        if not ICON.is_file():
            raise FileNotFoundError(f"缺少应用图标: {ICON}")
        cmd.append(f"--windows-icon-from-ico={ICON}")
    cmd.append(str(ENTRY))
    return cmd


def main(argv: list[str]) -> int:
    onefile = "--onefile" in argv
    py = ensure_env()
    cmd = build_cmd(py, onefile)
    print("[build] " + " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
