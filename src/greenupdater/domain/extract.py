"""安全解压器（对应 docs/design/02-modules.md §2.5）。

按扩展名分派 zip / tar(.gz/.bz2/.xz) / 7z，逐个成员校验最终路径不越出 dest（防 Zip Slip）。
locate_root 自动定位真正的应用根目录（下钻单层包装目录 / 按 exe_relpath 定位）。
"""
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from greenupdater.models import UpdateStage

from .errors import ExtractError, ZipSlipError
from .events import Progress, UpdateListener

_ZIP_SUFFIXES = (".zip",)
_SEVENZ_SUFFIXES = (".7z",)
_TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


class Extractor:
    def extract(self, archive: Path, dest: Path, listener: UpdateListener | None = None) -> Path:
        """解压 archive 到 dest，返回 dest。按扩展名分派，全程防路径穿越。"""
        archive = Path(archive)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        name = archive.name.lower()

        if listener:
            listener.on_progress(
                Progress(stage=UpdateStage.EXTRACT, percent=-1, message=f"解压中 {archive.name}")
            )

        if name.endswith(_ZIP_SUFFIXES):
            self._extract_zip(archive, dest)
        elif name.endswith(_SEVENZ_SUFFIXES):
            self._extract_7z(archive, dest)
        elif name.endswith(_TAR_SUFFIXES):
            self._extract_tar(archive, dest)
        else:
            raise ExtractError(f"不支持的压缩格式：{archive.name}")

        if listener:
            listener.on_progress(
                Progress(stage=UpdateStage.EXTRACT, percent=100, message="解压完成")
            )
        return dest

    # ---------- zip ----------
    def _extract_zip(self, archive: Path, dest: Path) -> None:
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    self._guard(dest, info.filename)
                zf.extractall(dest)
        except zipfile.BadZipFile as exc:
            raise ExtractError(f"zip 损坏：{exc}") from exc
        except OSError as exc:
            raise ExtractError(f"解压失败：{exc}") from exc

    # ---------- tar ----------
    def _extract_tar(self, archive: Path, dest: Path) -> None:
        try:
            with tarfile.open(archive) as tf:
                for member in tf.getmembers():
                    self._guard(dest, member.name)
                # Py3.12+ 的 data 过滤器额外阻断危险成员；不支持时回退已手动校验
                try:
                    tf.extractall(dest, filter="data")
                except TypeError:
                    tf.extractall(dest)
        except tarfile.TarError as exc:
            raise ExtractError(f"tar 损坏：{exc}") from exc
        except OSError as exc:
            raise ExtractError(f"解压失败：{exc}") from exc

    # ---------- 7z ----------
    def _extract_7z(self, archive: Path, dest: Path) -> None:
        try:
            import py7zr
        except ImportError as exc:  # pragma: no cover - 依赖缺失
            raise ExtractError("未安装 py7zr，无法解压 .7z") from exc
        try:
            with py7zr.SevenZipFile(archive, mode="r") as sz:
                for n in sz.getnames():
                    self._guard(dest, n)
                sz.extractall(path=dest)
        except Exception as exc:  # noqa: BLE001 - py7zr 异常类型不统一
            raise ExtractError(f"7z 解压失败：{exc}") from exc

    # ---------- 路径穿越防护 ----------
    @staticmethod
    def _guard(dest: Path, member_name: str) -> Path:
        """校验成员解压后的绝对路径必须在 dest 内，否则抛 ZipSlipError。"""
        dest_r = dest.resolve()
        target = (dest / member_name).resolve()
        if not target.is_relative_to(dest_r):
            raise ZipSlipError(f"检测到路径穿越：{member_name}")
        return target

    # ---------- 定位根目录 ----------
    def locate_root(self, extracted: Path, exe_relpath: str | None = None) -> Path:
        """定位真正的应用根目录。

        - 有 exe_relpath：找到能解析出该相对文件的目录（extracted 本身或其单层子目录）
        - 否则：只要顶层恰好一个目录就持续下钻（剥离单层包装目录）
        """
        extracted = Path(extracted)
        if exe_relpath:
            found = self._find_dir_with_relpath(extracted, exe_relpath)
            if found is not None:
                return found
        root = extracted
        while True:
            entries = list(root.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                root = entries[0]
            else:
                break
        return root

    @staticmethod
    def _find_dir_with_relpath(base: Path, relpath: str) -> Path | None:
        rel = Path(relpath)
        if (base / rel).is_file():
            return base
        for child in base.iterdir():
            if child.is_dir() and (child / rel).is_file():
                return child
        return None
