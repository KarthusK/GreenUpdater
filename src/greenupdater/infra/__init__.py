"""基础设施层：路径 / SQLite / 仓库 / Token / 日志（对应 docs/design/02-modules.md §4）。

对外统一从 ``greenupdater.infra`` 导入，隐藏子模块细节。domain / service / ui 只依赖此层，
不直接触碰 sqlite3 / keyring / loguru。
"""
from __future__ import annotations

from .db import SCHEMA_VERSION, connect, get_schema_version, init_db
from .logging import TERMINAL_MAX_LINES, TerminalBridge, setup_logging
from .paths import ENV_HOME_OVERRIDE, Paths, default_base_dir, is_frozen
from .repository import ConfigRepository, ImportReport
from .tokenstore import KeyringUnavailableError, TokenStore

__all__ = [
    # paths
    "Paths",
    "default_base_dir",
    "is_frozen",
    "ENV_HOME_OVERRIDE",
    # db
    "connect",
    "init_db",
    "get_schema_version",
    "SCHEMA_VERSION",
    # repository
    "ConfigRepository",
    "ImportReport",
    # tokenstore
    "TokenStore",
    "KeyringUnavailableError",
    # logging
    "setup_logging",
    "TerminalBridge",
    "TERMINAL_MAX_LINES",
]
