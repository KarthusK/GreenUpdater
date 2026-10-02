"""多资产选择对话框（对应 docs/design/03-ui.md §7）。

正则命中多个、架构关键字过滤后仍 ≥2 个时弹出。单选，显示资产名 + 大小。
取消 → 该 app 记为 failed@check（用户主动放弃）。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from greenupdater.domain import Asset


def _human(n: int | None) -> str:
    if not n:
        return ""
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.1f} {unit}" if unit != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.1f} GB"


class ChooseAssetDialog(QDialog):
    def __init__(self, assets: "list[Asset]", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("匹配到多个资产")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._assets = list(assets)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("该版本匹配到多个文件，请选择要下载的："))

        self._list = QListWidget(self)
        for a in self._assets:
            size = _human(a.size)
            text = f"{a.name}    {size}" if size else a.name
            self._list.addItem(QListWidgetItem(text))
        if self._assets:
            self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_asset(self) -> "Asset | None":
        """返回选中的资产；未选/取消返回 None。"""
        row = self._list.currentRow()
        if 0 <= row < len(self._assets):
            return self._assets[row]
        return None
