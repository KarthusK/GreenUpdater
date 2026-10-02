"""domain.overwrite 测试：覆盖跳过排除路径、新建目标、不删除多余文件。"""
from __future__ import annotations

from pathlib import Path

import pytest

from greenupdater.domain import Overwriter
from greenupdater.domain.errors import OverwriteError


@pytest.fixture()
def ow():
    return Overwriter()


def test_overwrite_copies_and_skips_excludes(ow, tmp_path: Path):
    src = tmp_path / "src"
    (src / "bin").mkdir(parents=True)
    (src / "app.exe").write_text("new-prog")
    (src / "bin" / "lib.dll").write_text("new-lib")
    (src / "config").mkdir()
    (src / "config" / "default.cfg").write_text("bundled-default")

    target = tmp_path / "target"
    target.mkdir()
    (target / "config").mkdir()
    (target / "config" / "user.cfg").write_text("KEEP-ME")

    ow.overwrite(src, target, exclude_paths=["config"])

    assert (target / "app.exe").read_text() == "new-prog"
    assert (target / "bin" / "lib.dll").read_text() == "new-lib"
    # 排除路径下的用户数据保留，且未被新版默认配置覆盖
    assert (target / "config" / "user.cfg").read_text() == "KEEP-ME"
    assert not (target / "config" / "default.cfg").exists()


def test_overwrite_creates_target_if_missing(ow, tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.exe").write_text("x")
    target = tmp_path / "brand-new"
    ow.overwrite(src, target, exclude_paths=[])
    assert (target / "app.exe").read_text() == "x"


def test_overwrite_does_not_delete_extra_files(ow, tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.exe").write_text("new")
    target = tmp_path / "target"
    target.mkdir()
    (target / "leftover.txt").write_text("old-residue")
    ow.overwrite(src, target, exclude_paths=[])
    # v1 语义：不删除新版已移除的旧文件
    assert (target / "leftover.txt").read_text() == "old-residue"
    assert (target / "app.exe").read_text() == "new"


def test_overwrite_missing_src_raises(ow, tmp_path: Path):
    with pytest.raises(OverwriteError):
        ow.overwrite(tmp_path / "nope", tmp_path / "target", exclude_paths=[])
