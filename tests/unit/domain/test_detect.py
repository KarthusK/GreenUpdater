"""domain.detect 测试：无 exe / 缺文件 / 非 Windows → UNKNOWN；Windows 真实 PE → 版本号。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from greenupdater.domain import LocalVersionDetector
from greenupdater.models import VersionDetectSource


@pytest.fixture()
def detector():
    return LocalVersionDetector()


def test_no_exe_relpath_returns_unknown(detector, tmp_path: Path):
    assert detector.detect(tmp_path, None) == (None, VersionDetectSource.UNKNOWN)


def test_missing_exe_returns_unknown(detector, tmp_path: Path):
    ver, src = detector.detect(tmp_path, "does-not-exist.exe")
    assert ver is None
    assert src == VersionDetectSource.UNKNOWN


@pytest.mark.skipif(sys.platform != "win32", reason="PE 版本资源仅 Windows")
def test_reads_real_pe_version_on_windows(detector):
    exe = Path(sys.executable)
    ver, src = detector.detect(exe.parent, exe.name)
    assert src == VersionDetectSource.PE
    assert ver is not None
    # 形如 3.12.4150.1013 —— 至少两段数字
    parts = ver.split(".")
    assert len(parts) >= 2
    assert parts[0].isdigit()
