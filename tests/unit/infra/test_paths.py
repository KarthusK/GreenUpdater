"""infra.paths 测试：base_dir 解析优先级与目录派生。"""
from __future__ import annotations

from pathlib import Path

from greenupdater.infra import Paths
from greenupdater.infra.paths import ENV_HOME_OVERRIDE, default_base_dir


def test_env_override_wins(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(ENV_HOME_OVERRIDE, str(tmp_path / "custom"))
    assert default_base_dir() == (tmp_path / "custom").resolve()


def test_paths_derives_locations(tmp_path: Path):
    p = Paths(tmp_path)
    assert p.db_path == tmp_path / "greenupdater.db"
    assert p.log_file == tmp_path / "logs" / "greenupdater.log"
    assert p.backups("uid-1") == tmp_path / "backups" / "uid-1"
    assert p.tmp("uid-1") == tmp_path / "tmp" / "uid-1"


def test_ensure_dirs_is_idempotent(tmp_path: Path):
    p = Paths(tmp_path / "nested" / "base")
    p.ensure_dirs()
    p.ensure_dirs()  # 再次调用不报错
    assert p.logs_dir.is_dir()
    assert p.backups_root.is_dir()
    assert p.tmp_root.is_dir()
