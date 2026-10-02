"""程序入口：``python -m greenupdater``。

装配见 ``greenupdater.app``：构建 Paths / 日志 / ConfigRepository / UpdateOrchestrator，
启动 PySide6 主窗口并处理单实例守卫。
"""
from __future__ import annotations

from greenupdater.app import main

if __name__ == "__main__":
    raise SystemExit(main())
