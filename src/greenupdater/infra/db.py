"""SQLite 连接、建表与 schema 迁移（对应 docs/design/01-data-model.md §3/§7）。

- ``connect()`` 打开连接（``foreign_keys=ON``、``Row`` 工厂、允许跨线程）。
- ``init_db()`` 幂等建表并把 schema 迁移到 ``SCHEMA_VERSION``。
- 迁移策略：全新库直接建最新表并写版本号；已有库按 ``_MIGRATIONS`` 逐级升级。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

#: 当前 schema 版本；表结构变更时递增，并在 _MIGRATIONS 补升级脚本。
SCHEMA_VERSION = 1

#: 幂等建表脚本（与 01-data-model.md §3 DDL 一致）
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    uid                 TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    source_type         TEXT    NOT NULL DEFAULT 'github',
    repo_owner          TEXT    NOT NULL,
    repo_name           TEXT    NOT NULL,
    asset_pattern       TEXT    NOT NULL,
    version_source      TEXT    NOT NULL DEFAULT 'tag',
    version_pattern     TEXT,
    include_prerelease  INTEGER NOT NULL DEFAULT 0,
    target_dir          TEXT    NOT NULL,
    exe_relpath         TEXT,
    process_names       TEXT    NOT NULL DEFAULT '[]',
    exclude_paths       TEXT    NOT NULL DEFAULT '[]',
    backup_enabled      INTEGER NOT NULL DEFAULT 1,
    enabled             INTEGER NOT NULL DEFAULT 1,
    current_version     TEXT,
    current_version_src TEXT    NOT NULL DEFAULT 'unknown',
    latest_version      TEXT,
    last_status         TEXT    NOT NULL DEFAULT 'unknown',
    last_error_stage    TEXT,
    last_error_message  TEXT,
    rollback_available  INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS update_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id         INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    from_version   TEXT,
    to_version     TEXT,
    asset_name     TEXT,
    asset_size     INTEGER,
    sha256         TEXT,
    result         TEXT    NOT NULL,
    failed_stage   TEXT,
    error_message  TEXT,
    rolled_back    INTEGER NOT NULL DEFAULT 0,
    started_at     TEXT    NOT NULL,
    finished_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_app
    ON update_history(app_id, started_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

#: from_version -> 升级到 from_version+1 的 SQL 列表（当前无历史迁移）
_MIGRATIONS: dict[int, list[str]] = {}


def connect(db_path: Path | str) -> sqlite3.Connection:
    """打开（必要时创建）数据库连接。"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        return 0  # meta 表尚不存在
    return int(row["value"]) if row else 0


def init_db(conn: sqlite3.Connection) -> None:
    """幂等建表 + 迁移到最新 schema 版本。"""
    with conn:
        conn.executescript(_SCHEMA_SQL)

    version = get_schema_version(conn)
    if version == 0:
        # 全新库：建表脚本已是最新结构，直接落版本号
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        return

    while version < SCHEMA_VERSION:
        steps = _MIGRATIONS.get(version, [])
        with conn:
            for sql in steps:
                conn.executescript(sql)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(version + 1),),
            )
        version += 1
