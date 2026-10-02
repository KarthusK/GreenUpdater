"""便携目录布局（对应 docs/design/01-data-model.md §6、04-structure.md §2）。

所有可变数据都在 base_dir（exe 旁 / 开发态项目根）内，整目录拷贝即迁移。
base_dir 定位优先级：环境变量 ``GREENUPDATER_HOME`` > 打包态 exe 目录 > 开发态项目根。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: 覆盖 base_dir 的环境变量（测试 / 便携自定义用）
ENV_HOME_OVERRIDE = "GREENUPDATER_HOME"


def is_frozen() -> bool:
    """是否运行在打包产物中（Nuitka / PyInstaller）。"""
    # PyInstaller 设 sys.frozen；Nuitka 在编译模块注入 __compiled__
    return bool(getattr(sys, "frozen", False)) or ("__compiled__" in globals())


def default_base_dir() -> Path:
    override = os.environ.get(ENV_HOME_OVERRIDE)
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # 开发态：<root>/src/greenupdater/infra/paths.py → parents[3] == <root>
    return Path(__file__).resolve().parents[3]


class Paths:
    """集中解析所有运行时路径。"""

    def __init__(self, base: Path | str | None = None) -> None:
        self.base_dir = Path(base).expanduser().resolve() if base else default_base_dir()

    @property
    def db_path(self) -> Path:
        return self.base_dir / "greenupdater.db"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "greenupdater.log"

    @property
    def backups_root(self) -> Path:
        return self.base_dir / "backups"

    @property
    def tmp_root(self) -> Path:
        return self.base_dir / "tmp"

    def backups(self, uid: str) -> Path:
        """某软件的完整快照目录（按 uid，改名不受影响）。"""
        return self.backups_root / uid

    def tmp(self, uid: str) -> Path:
        """某软件的下载 / 解压临时工作区。"""
        return self.tmp_root / uid

    def ensure_dirs(self) -> None:
        """创建 base/logs/backups/tmp 目录（幂等）。"""
        for d in (self.base_dir, self.logs_dir, self.backups_root, self.tmp_root):
            d.mkdir(parents=True, exist_ok=True)
