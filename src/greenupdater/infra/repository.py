"""ConfigRepository：SQLite 仓库，负责 apps / update_history / settings 的读写与导入导出。

对应 docs/design/02-modules.md §4.1。负责 SQLite 行 ↔ pydantic 模型转换：
JSON 数组文本 ↔ list、0/1 ↔ bool、枚举 ↔ str、ISO 文本 ↔ datetime、str ↔ Path。
Token 不在此处（见 tokenstore.py）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from greenupdater.models import (
    EXPORT_SCHEMA_VERSION,
    App,
    AppConfig,
    ExportApp,
    ExportBundle,
    Settings,
    UpdateRecord,
    UpdateResult,
    UpdateStage,
)

from .db import connect, init_db


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# AppConfig 中需要落库的“配置列”（顺序无关）
_CONFIG_COLUMNS = (
    "name",
    "source_type",
    "repo_owner",
    "repo_name",
    "asset_pattern",
    "version_source",
    "version_pattern",
    "include_prerelease",
    "target_dir",
    "exe_relpath",
    "process_names",
    "exclude_paths",
    "backup_enabled",
    "enabled",
)


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


class ConfigRepository:
    def __init__(self, db_path: Path | str) -> None:
        self._conn = connect(db_path)
        init_db(self._conn)
        self._lock = threading.RLock()

    # ---------- 生命周期 ----------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "ConfigRepository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- apps ----------
    def list_apps(self) -> list[App]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM apps ORDER BY name COLLATE NOCASE").fetchall()
        return [self._row_to_app(r) for r in rows]

    def get_app(self, uid: str) -> App | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM apps WHERE uid=?", (uid,)).fetchone()
        return self._row_to_app(row) if row else None

    def get_app_by_id(self, app_id: int) -> App | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
        return self._row_to_app(row) if row else None

    def upsert_app(self, cfg: AppConfig, uid: str | None = None) -> App:
        """新增或按 uid 更新配置。更新时保留 id / 运行态 / created_at。"""
        now = _utcnow_iso()
        uid = uid or str(uuid.uuid4())
        params = self._config_params(cfg)
        with self._lock:
            existing = self._conn.execute("SELECT id FROM apps WHERE uid=?", (uid,)).fetchone()
            if existing:
                assignments = ", ".join(f"{col}=?" for col in params)
                self._conn.execute(
                    f"UPDATE apps SET {assignments}, updated_at=? WHERE uid=?",
                    (*params.values(), now, uid),
                )
                self._conn.commit()
                app_id = existing["id"]
            else:
                cols = ("uid", *_CONFIG_COLUMNS, "created_at", "updated_at")
                values = (uid, *params.values(), now, now)
                placeholders = ",".join("?" for _ in cols)
                cur = self._conn.execute(
                    f"INSERT INTO apps({','.join(cols)}) VALUES({placeholders})", values
                )
                self._conn.commit()
                app_id = cur.lastrowid
        return self.get_app_by_id(app_id)  # type: ignore[arg-type]

    def save_state(self, app: App) -> None:
        """持久化运行态列（版本 / 状态 / 错误 / 可回滚标记）。"""
        with self._lock:
            self._conn.execute(
                """UPDATE apps SET
                       current_version=?, current_version_src=?, latest_version=?,
                       last_status=?, last_error_stage=?, last_error_message=?,
                       rollback_available=?, updated_at=?
                   WHERE uid=?""",
                (
                    app.current_version,
                    app.current_version_src.value,
                    app.latest_version,
                    app.last_status.value,
                    app.last_error_stage.value if app.last_error_stage else None,
                    app.last_error_message,
                    int(app.rollback_available),
                    _utcnow_iso(),
                    app.uid,
                ),
            )
            self._conn.commit()

    def delete_app(self, uid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM apps WHERE uid=?", (uid,))
            self._conn.commit()

    # ---------- history ----------
    def add_history(self, rec: UpdateRecord) -> UpdateRecord:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO update_history(
                       app_id, from_version, to_version, asset_name, asset_size, sha256,
                       result, failed_stage, error_message, rolled_back, started_at, finished_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.app_id,
                    rec.from_version,
                    rec.to_version,
                    rec.asset_name,
                    rec.asset_size,
                    rec.sha256,
                    rec.result.value,
                    rec.failed_stage.value if rec.failed_stage else None,
                    rec.error_message,
                    int(rec.rolled_back),
                    rec.started_at.isoformat(),
                    rec.finished_at.isoformat() if rec.finished_at else None,
                ),
            )
            self._conn.commit()
            return rec.model_copy(update={"id": cur.lastrowid})

    def list_history(self, app_uid: str, limit: int = 50) -> list[UpdateRecord]:
        app = self.get_app(app_uid)
        if app is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM update_history WHERE app_id=? ORDER BY started_at DESC LIMIT ?",
                (app.id, limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def mark_rolled_back(self, app_uid: str) -> None:
        """把该软件最近一条历史记录标记为已回滚。"""
        app = self.get_app(app_uid)
        if app is None:
            return
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM update_history WHERE app_id=? ORDER BY started_at DESC LIMIT 1",
                (app.id,),
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE update_history SET rolled_back=1 WHERE id=?", (row["id"],)
                )
                self._conn.commit()

    # ---------- settings ----------
    def get_settings(self) -> Settings:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        data = {}
        for r in rows:
            try:
                data[r["key"]] = json.loads(r["value"])
            except json.JSONDecodeError:
                data[r["key"]] = r["value"]
        known = {k: v for k, v in data.items() if k in Settings.model_fields}
        return Settings(**known)

    def save_settings(self, settings: Settings) -> None:
        with self._lock:
            for key, value in settings.model_dump().items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                    (key, json.dumps(value)),
                )
            self._conn.commit()

    # ---------- 导入 / 导出 ----------
    def export_json(self) -> dict:
        """导出为 JSON-safe dict（含 apps 配置 + 本地版本 + settings；不含 token / 历史）。"""
        export_fields = set(ExportApp.model_fields)
        apps = [
            ExportApp(**{k: v for k, v in a.model_dump().items() if k in export_fields})
            for a in self.list_apps()
        ]
        bundle = ExportBundle(apps=apps, settings=self.get_settings())
        return bundle.model_dump(mode="json")

    def import_json(self, bundle_dict: dict) -> ImportReport:
        """按 uid upsert；新建项恢复本地版本；已存在项仅更新配置（不覆盖运行态）。"""
        bundle = ExportBundle.model_validate(bundle_dict)
        if bundle.version > EXPORT_SCHEMA_VERSION:
            raise ValueError(
                f"导入文件版本 {bundle.version} 高于当前支持的 {EXPORT_SCHEMA_VERSION}"
            )
        # bundle.version < EXPORT_SCHEMA_VERSION 时的字段迁移在此处按需补充

        report = ImportReport()
        cfg_fields = set(AppConfig.model_fields)
        for ea in bundle.apps:
            try:
                cfg = AppConfig(**{k: v for k, v in ea.model_dump().items() if k in cfg_fields})
                existing = self.get_app(ea.uid)
                app = self.upsert_app(cfg, uid=ea.uid)
                if existing is None:
                    self.save_state(
                        app.model_copy(
                            update={
                                "current_version": ea.current_version,
                                "current_version_src": ea.current_version_src,
                            }
                        )
                    )
                    report.created += 1
                else:
                    report.updated += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整体导入
                report.errors.append(f"{ea.name}: {exc}")

        try:
            self.save_settings(bundle.settings)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"settings: {exc}")
        return report

    # ---------- 行 ↔ 模型 ----------
    @staticmethod
    def _config_params(cfg: AppConfig) -> dict:
        return {
            "name": cfg.name,
            "source_type": cfg.source_type.value,
            "repo_owner": cfg.repo_owner,
            "repo_name": cfg.repo_name,
            "asset_pattern": cfg.asset_pattern,
            "version_source": cfg.version_source.value,
            "version_pattern": cfg.version_pattern,
            "include_prerelease": int(cfg.include_prerelease),
            "target_dir": str(cfg.target_dir),
            "exe_relpath": cfg.exe_relpath,
            "process_names": json.dumps(cfg.process_names, ensure_ascii=False),
            "exclude_paths": json.dumps(cfg.exclude_paths, ensure_ascii=False),
            "backup_enabled": int(cfg.backup_enabled),
            "enabled": int(cfg.enabled),
        }

    @staticmethod
    def _row_to_app(row: sqlite3.Row) -> App:
        return App(
            id=row["id"],
            uid=row["uid"],
            name=row["name"],
            source_type=row["source_type"],
            repo_owner=row["repo_owner"],
            repo_name=row["repo_name"],
            asset_pattern=row["asset_pattern"],
            version_source=row["version_source"],
            version_pattern=row["version_pattern"],
            include_prerelease=bool(row["include_prerelease"]),
            target_dir=Path(row["target_dir"]),
            exe_relpath=row["exe_relpath"],
            process_names=json.loads(row["process_names"]),
            exclude_paths=json.loads(row["exclude_paths"]),
            backup_enabled=bool(row["backup_enabled"]),
            enabled=bool(row["enabled"]),
            current_version=row["current_version"],
            current_version_src=row["current_version_src"],
            latest_version=row["latest_version"],
            last_status=row["last_status"],
            last_error_stage=UpdateStage(row["last_error_stage"]) if row["last_error_stage"] else None,
            last_error_message=row["last_error_message"],
            rollback_available=bool(row["rollback_available"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> UpdateRecord:
        return UpdateRecord(
            id=row["id"],
            app_id=row["app_id"],
            from_version=row["from_version"],
            to_version=row["to_version"],
            asset_name=row["asset_name"],
            asset_size=row["asset_size"],
            sha256=row["sha256"],
            result=UpdateResult(row["result"]),
            failed_stage=UpdateStage(row["failed_stage"]) if row["failed_stage"] else None,
            error_message=row["error_message"],
            rolled_back=bool(row["rolled_back"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        )
