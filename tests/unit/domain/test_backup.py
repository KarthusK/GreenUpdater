"""domain.backup 测试：完整快照、仅 1 份、回滚跳过排除路径、无快照报错、删除。"""
from __future__ import annotations

from pathlib import Path

import pytest

from greenupdater.domain import BackupManager
from greenupdater.domain.errors import SnapshotError
from greenupdater.infra import Paths
from greenupdater.models import App


def make_app(tmp_path: Path, **kw) -> App:
    base = dict(
        id=1,
        name="X",
        repo_owner="o",
        repo_name="r",
        asset_pattern=r".*\.zip",
        target_dir=tmp_path / "target",
        exclude_paths=["config"],
    )
    base.update(kw)
    return App(**base)


@pytest.fixture()
def paths(tmp_path: Path) -> Paths:
    return Paths(tmp_path / "portable")


def seed_target(target: Path):
    (target / "bin").mkdir(parents=True)
    (target / "app.exe").write_text("v1-prog")
    (target / "bin" / "lib.dll").write_text("v1-lib")
    (target / "config").mkdir()
    (target / "config" / "user.cfg").write_text("v1-user")


def test_create_snapshot_copies_everything(paths, tmp_path: Path):
    app = make_app(tmp_path)
    seed_target(app.target_dir)
    bm = BackupManager(paths)
    dest = bm.create_snapshot(app)
    assert dest == paths.backups(app.uid)
    assert (dest / "app.exe").read_text() == "v1-prog"
    # 完整快照含用户数据
    assert (dest / "config" / "user.cfg").read_text() == "v1-user"
    assert bm.has_snapshot(app) is True


def test_snapshot_only_one_copy(paths, tmp_path: Path):
    app = make_app(tmp_path)
    seed_target(app.target_dir)
    bm = BackupManager(paths)
    bm.create_snapshot(app)
    (app.target_dir / "app.exe").write_text("v2-prog")
    bm.create_snapshot(app)  # 第二次应替换
    dest = paths.backups(app.uid)
    assert (dest / "app.exe").read_text() == "v2-prog"
    # 仅一份：不存在 .bak 之类额外目录
    assert list(dest.parent.iterdir()) == [dest]


def test_rollback_restores_program_keeps_user_data(paths, tmp_path: Path):
    app = make_app(tmp_path)
    seed_target(app.target_dir)
    bm = BackupManager(paths)
    bm.create_snapshot(app)

    # 模拟一次失败/损坏的更新：程序文件变坏，用户数据也被更新过
    (app.target_dir / "app.exe").write_text("BROKEN")
    (app.target_dir / "bin" / "lib.dll").write_text("BROKEN-LIB")
    (app.target_dir / "config" / "user.cfg").write_text("CURRENT-USER-DATA")

    bm.rollback(app)

    # 程序文件回滚到快照版本
    assert (app.target_dir / "app.exe").read_text() == "v1-prog"
    assert (app.target_dir / "bin" / "lib.dll").read_text() == "v1-lib"
    # 排除路径下的当前用户数据保留，不被快照覆盖
    assert (app.target_dir / "config" / "user.cfg").read_text() == "CURRENT-USER-DATA"


def test_rollback_without_snapshot_raises(paths, tmp_path: Path):
    app = make_app(tmp_path)
    app.target_dir.mkdir(parents=True)
    bm = BackupManager(paths)
    with pytest.raises(SnapshotError):
        bm.rollback(app)


def test_missing_target_creates_empty_snapshot(paths, tmp_path: Path):
    app = make_app(tmp_path)  # target_dir 不存在
    bm = BackupManager(paths)
    dest = bm.create_snapshot(app)
    assert dest.is_dir()
    # 空快照不算有可用快照
    assert bm.has_snapshot(app) is False


def test_delete_snapshot(paths, tmp_path: Path):
    app = make_app(tmp_path)
    seed_target(app.target_dir)
    bm = BackupManager(paths)
    bm.create_snapshot(app)
    assert bm.has_snapshot(app) is True
    bm.delete_snapshot(app)
    assert bm.has_snapshot(app) is False
