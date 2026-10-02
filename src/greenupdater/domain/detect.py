"""本地版本探测（对应 docs/design/02-modules.md §2.3）。

Windows：用 ctypes 调 Win32 版本 API 读 exe 的 PE 版本资源（无额外依赖）。
探测不到 → (None, UNKNOWN)，由 UI 让用户手填(MANUAL)。非 Windows 无 PE → UNKNOWN。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from greenupdater.models import VersionDetectSource


class LocalVersionDetector:
    def detect(
        self, target_dir: Path, exe_relpath: str | None
    ) -> tuple[str | None, VersionDetectSource]:
        """返回 (版本字符串 | None, 来源)。"""
        if not exe_relpath:
            return (None, VersionDetectSource.UNKNOWN)
        exe = (Path(target_dir) / exe_relpath).resolve()
        if not exe.is_file():
            return (None, VersionDetectSource.UNKNOWN)
        if sys.platform != "win32":
            return (None, VersionDetectSource.UNKNOWN)
        ver = _read_pe_file_version(str(exe))
        if ver:
            return (ver, VersionDetectSource.PE)
        return (None, VersionDetectSource.UNKNOWN)


def _read_pe_file_version(exe_path: str) -> str | None:
    """读 PE 的 VS_FIXEDFILEINFO 数值版本；失败返回 None。仅 win32 调用。"""
    import ctypes
    from ctypes import POINTER, byref, cast, create_string_buffer, sizeof, wintypes

    try:
        v = ctypes.windll.version  # type: ignore[attr-defined]
        v.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, POINTER(wintypes.DWORD)]
        v.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        v.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        v.GetFileVersionInfoW.restype = wintypes.BOOL
        v.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            POINTER(wintypes.LPVOID),
            POINTER(wintypes.UINT),
        ]
        v.VerQueryValueW.restype = wintypes.BOOL

        handle = wintypes.DWORD(0)
        size = v.GetFileVersionInfoSizeW(exe_path, byref(handle))
        if size == 0:
            return None
        data = create_string_buffer(size)
        if not v.GetFileVersionInfoW(exe_path, handle.value, size, data):
            return None

        pinfo = wintypes.LPVOID()
        plen = wintypes.UINT()
        if not v.VerQueryValueW(data, "\\", byref(pinfo), byref(plen)):
            return None
        if plen.value < sizeof(wintypes.DWORD) * 6:
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD),
                ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD),
                ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD),
                ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            ]

        info = cast(pinfo, POINTER(VS_FIXEDFILEINFO)).contents
        if info.dwSignature != 0xFEEF04BD:
            return None

        ver = _fmt(info.dwFileVersionMS, info.dwFileVersionLS)
        if ver == "0.0.0.0":
            ver = _fmt(info.dwProductVersionMS, info.dwProductVersionLS)
        return None if ver == "0.0.0.0" else ver
    except (OSError, AttributeError, ValueError) as exc:
        logger.debug(f"读取 PE 版本失败 {exe_path}: {exc}")
        return None


def _fmt(ms: int, ls: int) -> str:
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
