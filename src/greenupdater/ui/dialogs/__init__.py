"""UI 对话框（对应 docs/design/03-ui.md §4–§8）。"""
from __future__ import annotations

from .app_edit import AppEditDialog
from .choose_asset import ChooseAssetDialog
from .confirm_kill import ConfirmKillDialog
from .history import HistoryDialog
from .settings import SettingsDialog

__all__ = [
    "AppEditDialog",
    "ChooseAssetDialog",
    "ConfirmKillDialog",
    "HistoryDialog",
    "SettingsDialog",
]
