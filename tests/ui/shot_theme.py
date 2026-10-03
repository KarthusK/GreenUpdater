"""临时脚本：渲染深色主题各界面为 PNG，供视觉检查（不属于交付物）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")

ROOT = Path(__file__).resolve().parents[2]  # tests/ui/shot_theme.py → 仓库根
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from greenupdater.infra import ConfigRepository, Paths, TokenStore  # noqa: E402
from greenupdater.models import (  # noqa: E402
    AppConfig,
    AppStatus,
    UpdateStage,
    VersionDetectSource,
)
from greenupdater.ui.dialogs import (  # noqa: E402
    AppEditDialog,
    ChooseAssetDialog,
    ConfirmKillDialog,
    HistoryDialog,
    SettingsDialog,
)
from greenupdater.ui.main_window import MainWindow  # noqa: E402
from greenupdater.ui.theme import apply_dark_theme  # noqa: E402

OUT = ROOT / "tmp" / "themeshots"
OUT.mkdir(exist_ok=True, parents=True)

# 截图用的临时库固定放 tmp/：本环境下 tempfile 会退化为工作目录，
# 直接用 mkdtemp() 会在仓库根散落 tmpXXXX/ 目录（已实测）。
SCRATCH = ROOT / "tmp" / "themeshots" / "_scratch"
SCRATCH.mkdir(exist_ok=True, parents=True)


class FakeProc:
    name = lambda self: "clash-verge.exe"  # noqa: E731
    pid = 12345


def make_repo() -> ConfigRepository:
    db = SCRATCH / "shot.db"
    db.unlink(missing_ok=True)  # 每轮重建，避免沿用上次的样例数据
    repo = ConfigRepository(db)
    base = dict(
        repo_owner="arb",
        asset_pattern=r".*windows.*\.zip$",
        target_dir=Path(r"D:\Apps\Demo"),
    )
    samples = [
        ("Everything", "everything", "v1.4.1.1009", "v1.4.1.1024", AppStatus.UPDATE_AVAILABLE),
        ("7-Zip", "ip7z", "24.08", "24.08", AppStatus.UP_TO_DATE),
        ("Clash Verge", "clash-verge-rev", "v2.0.0", "v2.2.3", AppStatus.FAILED),
        ("Obsidian", "obsidianmd", "1.6.7", "1.7.2", AppStatus.SUCCESS),
    ]
    for i, (name, repo_name, cur, latest, status) in enumerate(samples):
        app = repo.upsert_app(AppConfig(name=name, repo_name=repo_name, **base))
        app.current_version = cur
        app.current_version_src = VersionDetectSource.PE
        app.latest_version = latest
        app.last_status = status
        app.rollback_available = i in (2, 3)
        if status == AppStatus.FAILED:
            app.last_error_stage = UpdateStage.OVERWRITE
            app.last_error_message = "覆盖文件失败：目标目录被占用"
        repo.save_state(app)
    return repo


def snap(widget, name: str) -> None:
    widget.show()
    QApplication.processEvents()
    pm = widget.grab()
    pm.save(str(OUT / f"{name}.png"))
    print(f"saved {name}: {pm.width()}x{pm.height()}")


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    repo = make_repo()

    win = MainWindow(repo)
    win.resize(1000, 700)
    snap(win, "01_main")

    # 忙碌态 + 终端着色
    win.set_busy(True)
    win.set_progress("下载中 12.3 MB / 40 MB", 45)
    win.append_logs([
        "[检查] Everything（arb/everything）",
        "[更新] Clash Verge 开始",
        "[下载] clash-verge-windows.zip   12.3 MB / 40 MB",
        "[快照] 创建完整备份",
        "[覆盖] → D:\\Apps\\ClashVerge",
        "[成功] Obsidian: 1.6.7 → 1.7.2",
        "[失败] Clash Verge @ overwrite: 覆盖文件失败：目标目录被占用",
        "[提示] Clash Verge 覆盖失败，可右键手动回滚",
        "[跳过] 已取消，剩余软件不再处理",
        "[完成] 更新 1 成功 / 1 失败",
    ])
    snap(win, "02_main_busy")
    win.set_busy(False)

    snap(AppEditDialog(None), "03_app_edit")
    paths = Paths()
    snap(SettingsDialog(repo, paths, TokenStore()), "04_settings")
    app0 = repo.list_apps()[2]
    snap(HistoryDialog(app0.name, repo.list_history(app0.uid), None), "05_history")
    from greenupdater.domain import Asset

    assets = [
        Asset(name="app-2.2.3-windows-x64.zip", download_url="https://example.com/a.zip", size=41_943_040),
        Asset(name="app-2.2.3-windows-arm64.zip", download_url="https://example.com/b.zip", size=39_845_888),
    ]
    snap(ChooseAssetDialog(assets), "06_choose_asset")
    snap(ConfirmKillDialog("Clash Verge", [FakeProc()], None), "07_confirm_kill")

    # 右键菜单
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    menu.addAction("编辑…")
    menu.addAction("删除")
    menu.addSeparator()
    menu.addAction("检查更新")
    menu.addAction("更新")
    a = menu.addAction("回滚到此版本")
    a.setEnabled(False)
    menu.addSeparator()
    menu.addAction("打开目标目录")
    menu.addAction("查看更新历史…")
    menu.show()
    QApplication.processEvents()
    menu.grab().save(str(OUT / "08_menu.png"))
    print("saved 08_menu")

    repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
