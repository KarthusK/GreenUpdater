"""infra.repository 测试：apps / history / settings 读写、级联删除、导入导出往返。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from greenupdater.infra import ConfigRepository
from greenupdater.models import (
    AppConfig,
    Settings,
    UpdateRecord,
    UpdateResult,
    UpdateStage,
    VersionDetectSource,
    VersionSource,
)


def make_cfg(**kw) -> AppConfig:
    base = dict(
        name="LibreWolf",
        repo_owner="librewolf",
        repo_name="browser",
        asset_pattern=r"librewolf-.*-windows-x86_64-portable\.zip",
        version_pattern=r"librewolf-([\d.]+)-",
        target_dir=Path("D:/apps/librewolf"),
        exe_relpath="librewolf.exe",
        process_names=["librewolf.exe"],
        exclude_paths=["config", "data"],
    )
    base.update(kw)
    return AppConfig(**base)


@pytest.fixture()
def repo(tmp_path: Path):
    r = ConfigRepository(tmp_path / "test.db")
    yield r
    r.close()


def test_upsert_then_get_roundtrip(repo):
    app = repo.upsert_app(make_cfg())
    assert app.id is not None
    got = repo.get_app(app.uid)
    assert got is not None
    assert got.name == "LibreWolf"
    assert got.version_source == VersionSource.TAG
    assert got.process_names == ["librewolf.exe"]
    assert got.exclude_paths == ["config", "data"]
    assert got.target_dir == Path("D:/apps/librewolf")
    assert got.backup_enabled is True


def test_upsert_update_preserves_id_and_state(repo):
    app = repo.upsert_app(make_cfg())
    app.latest_version = "1.2.3"
    repo.save_state(app)
    updated = repo.upsert_app(make_cfg(name="LibreWolf2"), uid=app.uid)
    assert updated.id == app.id
    assert updated.uid == app.uid
    assert updated.name == "LibreWolf2"
    # 运行态在配置 upsert 后保留
    assert updated.latest_version == "1.2.3"


def test_list_apps_sorted_case_insensitive(repo):
    repo.upsert_app(make_cfg(name="zulu"))
    repo.upsert_app(make_cfg(name="Alpha"))
    repo.upsert_app(make_cfg(name="mike"))
    names = [a.name for a in repo.list_apps()]
    assert names == ["Alpha", "mike", "zulu"]


def test_save_state_persists_runtime_columns(repo):
    app = repo.upsert_app(make_cfg())
    app.current_version = "1.0.0"
    app.current_version_src = VersionDetectSource.PE
    app.last_status = "failed"
    app.last_error_stage = UpdateStage.OVERWRITE
    app.last_error_message = "boom"
    app.rollback_available = True
    repo.save_state(app)
    got = repo.get_app(app.uid)
    assert got.current_version == "1.0.0"
    assert got.current_version_src == VersionDetectSource.PE
    assert got.last_error_stage == UpdateStage.OVERWRITE
    assert got.rollback_available is True


def test_history_add_and_list(repo):
    app = repo.upsert_app(make_cfg())
    now = datetime.now(timezone.utc)
    rec = UpdateRecord(
        app_id=app.id,
        from_version="1.0",
        to_version="1.1",
        asset_name="a.zip",
        asset_size=123,
        result=UpdateResult.SUCCESS,
        started_at=now,
        finished_at=now,
    )
    saved = repo.add_history(rec)
    assert saved.id is not None
    hist = repo.list_history(app.uid)
    assert len(hist) == 1
    assert hist[0].to_version == "1.1"
    assert hist[0].result == UpdateResult.SUCCESS


def test_delete_app_cascades_history(repo):
    app = repo.upsert_app(make_cfg())
    now = datetime.now(timezone.utc)
    repo.add_history(
        UpdateRecord(
            app_id=app.id,
            result=UpdateResult.SUCCESS,
            started_at=now,
        )
    )
    assert len(repo.list_history(app.uid)) == 1
    repo.delete_app(app.uid)
    assert repo.get_app(app.uid) is None
    # 级联删除后历史也应消失（按已删 uid 查为空）
    assert repo.list_history(app.uid) == []


def test_settings_roundtrip(repo):
    s = Settings(proxy_enabled=True, proxy_url="http://127.0.0.1:7890", log_level="DEBUG")
    repo.save_settings(s)
    got = repo.get_settings()
    assert got.proxy_enabled is True
    assert got.proxy_url == "http://127.0.0.1:7890"
    assert got.log_level == "DEBUG"


def test_export_import_roundtrip(tmp_path: Path):
    src = ConfigRepository(tmp_path / "src.db")
    app = src.upsert_app(make_cfg())
    app.current_version = "2.0"
    app.current_version_src = VersionDetectSource.PE
    src.save_state(app)
    src.save_settings(Settings(log_level="WARNING"))
    bundle = src.export_json()
    src.close()

    # 导出不得含 token
    import json as _json

    assert "token" not in _json.dumps(bundle).lower()

    dst = ConfigRepository(tmp_path / "dst.db")
    report = dst.import_json(bundle)
    assert report.created == 1
    assert report.errors == []
    imported = dst.get_app(app.uid)
    assert imported is not None
    assert imported.name == "LibreWolf"
    # 新建项恢复本地版本
    assert imported.current_version == "2.0"
    assert imported.current_version_src == VersionDetectSource.PE
    assert dst.get_settings().log_level == "WARNING"
    dst.close()


def test_import_rejects_higher_version(repo):
    bundle = repo.export_json()
    bundle["version"] = 999
    with pytest.raises(ValueError):
        repo.import_json(bundle)
