"""models 层单元测试（不依赖 Qt）。"""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from greenupdater.models import (
    App,
    AppConfig,
    AppStatus,
    ExportBundle,
    Settings,
    VersionDetectSource,
    VersionSource,
)


def make_config(**overrides) -> AppConfig:
    base = dict(
        name="LibreWolf",
        repo_owner="librewolf-browser",
        repo_name="librewolf",
        asset_pattern=r"librewolf-.*-windows-x86_64-portable\.zip",
        target_dir="D:/Apps/LibreWolf",
    )
    base.update(overrides)
    return AppConfig(**base)


def test_appconfig_defaults_and_repo():
    cfg = make_config()
    assert cfg.repo == "librewolf-browser/librewolf"
    assert cfg.source_type.value == "github"
    assert cfg.version_source is VersionSource.TAG
    assert cfg.include_prerelease is False
    assert cfg.backup_enabled is True
    assert cfg.enabled is True
    assert cfg.process_names == []
    assert cfg.exclude_paths == []
    assert cfg.target_dir.name == "LibreWolf"  # 字符串被解析为 Path


def test_invalid_regex_rejected():
    with pytest.raises(ValidationError):
        make_config(asset_pattern="[unterminated(")
    with pytest.raises(ValidationError):
        make_config(version_pattern=r"librewolf-([\d.]+")  # 括号未闭合


def test_valid_version_pattern_ok():
    cfg = make_config(version_pattern=r"librewolf-([\d.]+)-")
    assert cfg.version_pattern == r"librewolf-([\d.]+)-"


def test_app_uid_and_timestamps_auto():
    app = App(id=1, **make_config().model_dump())
    assert app.uid
    assert isinstance(app.created_at, datetime)
    assert isinstance(app.updated_at, datetime)
    assert app.last_status is AppStatus.UNKNOWN
    assert app.rollback_available is False
    assert app.current_version_src is VersionDetectSource.UNKNOWN


def test_two_apps_have_distinct_uid():
    a = App(id=1, **make_config().model_dump())
    b = App(id=2, **make_config(name="Other").model_dump())
    assert a.uid != b.uid


def test_export_bundle_roundtrip():
    bundle = ExportBundle(
        apps=[
            {
                "uid": "fixed-uid-123",
                **make_config(
                    version_source=VersionSource.ASSET_NAME,
                    version_pattern=r"librewolf-([\d.]+)-",
                    process_names=["librewolf.exe"],
                    exclude_paths=["Profiles"],
                ).model_dump(),
                "current_version": "130.0",
                "current_version_src": VersionDetectSource.PE,
            }
        ],
        settings=Settings(
            log_level="DEBUG", proxy_enabled=True, proxy_url="http://127.0.0.1:7890"
        ),
    )
    raw = bundle.model_dump_json()
    parsed = ExportBundle.model_validate_json(raw)

    assert parsed.version == bundle.version
    assert len(parsed.apps) == 1
    app = parsed.apps[0]
    assert app.uid == "fixed-uid-123"
    assert app.name == "LibreWolf"
    assert app.version_source is VersionSource.ASSET_NAME
    assert app.process_names == ["librewolf.exe"]
    assert app.exclude_paths == ["Profiles"]
    assert app.current_version == "130.0"
    assert app.current_version_src is VersionDetectSource.PE
    assert parsed.settings.log_level == "DEBUG"
    assert parsed.settings.proxy_url == "http://127.0.0.1:7890"

    # 导出内容不含任何 token 字段
    assert "token" not in json.loads(raw).__str__().lower()


def test_settings_defaults():
    s = Settings()
    assert s.proxy_enabled is False
    assert s.proxy_url is None
    assert s.log_level == "INFO"
    assert s.default_include_prerelease is False
