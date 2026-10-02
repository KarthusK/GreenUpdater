"""domain.extract 测试：zip / tar.gz / 7z 解压、Zip Slip 防护、locate_root。"""
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

from greenupdater.domain import Extractor
from greenupdater.domain.errors import ExtractError, ZipSlipError


@pytest.fixture()
def ex():
    return Extractor()


def make_zip(path: Path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


def test_extract_zip(ex, tmp_path: Path):
    z = make_zip(tmp_path / "a.zip", {"app.exe": "x", "sub/readme.txt": "hi"})
    dest = tmp_path / "out"
    root = ex.extract(z, dest)
    assert root == dest
    assert (dest / "app.exe").read_text() == "x"
    assert (dest / "sub" / "readme.txt").read_text() == "hi"


def test_extract_tar_gz(ex, tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.exe").write_text("data")
    z = tmp_path / "a.tar.gz"
    with tarfile.open(z, "w:gz") as tf:
        tf.add(src / "app.exe", arcname="app.exe")
    dest = tmp_path / "out"
    ex.extract(z, dest)
    assert (dest / "app.exe").read_text() == "data"


def test_extract_7z(ex, tmp_path: Path):
    py7zr = pytest.importorskip("py7zr")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.exe").write_text("7zdata")
    z = tmp_path / "a.7z"
    with py7zr.SevenZipFile(z, "w") as sz:
        sz.write(src / "app.exe", arcname="app.exe")
    dest = tmp_path / "out"
    ex.extract(z, dest)
    assert (dest / "app.exe").read_text() == "7zdata"


def test_zip_slip_blocked(ex, tmp_path: Path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escaped.txt", "pwned")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ZipSlipError):
        ex.extract(z, dest)
    assert not (tmp_path / "escaped.txt").exists()


def test_unsupported_format(ex, tmp_path: Path):
    f = tmp_path / "a.rar"
    f.write_bytes(b"x")
    with pytest.raises(ExtractError):
        ex.extract(f, tmp_path / "out")


def test_locate_root_descends_single_wrapper(ex, tmp_path: Path):
    base = tmp_path / "ex"
    (base / "AppFolder").mkdir(parents=True)
    (base / "AppFolder" / "app.exe").write_text("x")
    assert ex.locate_root(base) == base / "AppFolder"


def test_locate_root_stops_at_multiple_entries(ex, tmp_path: Path):
    base = tmp_path / "ex"
    base.mkdir()
    (base / "a.txt").write_text("1")
    (base / "b.txt").write_text("2")
    assert ex.locate_root(base) == base


def test_locate_root_uses_exe_relpath(ex, tmp_path: Path):
    base = tmp_path / "ex"
    (base / "Wrap" / "bin").mkdir(parents=True)
    (base / "Wrap" / "bin" / "app.exe").write_text("x")
    (base / "other.txt").write_text("noise")  # 顶层不止一个条目
    assert ex.locate_root(base, "bin/app.exe") == base / "Wrap"


def test_locate_root_exe_relpath_at_base(ex, tmp_path: Path):
    base = tmp_path / "ex"
    base.mkdir()
    (base / "app.exe").write_text("x")
    (base / "noise.txt").write_text("y")
    assert ex.locate_root(base, "app.exe") == base
