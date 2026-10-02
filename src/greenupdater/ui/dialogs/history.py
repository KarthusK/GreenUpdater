"""更新历史对话框（对应 docs/design/03-ui.md §8）。只读展示 update_history。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from greenupdater.models import UpdateRecord, UpdateResult, UpdateStage

_STAGE_ZH = {
    UpdateStage.CHECK: "检查",
    UpdateStage.DOWNLOAD: "下载",
    UpdateStage.EXTRACT: "解压",
    UpdateStage.KILL_PROCESS: "结束进程",
    UpdateStage.SNAPSHOT: "快照",
    UpdateStage.OVERWRITE: "覆盖",
}

_RESULT_ZH = {
    UpdateResult.SUCCESS: "成功",
    UpdateResult.FAILED: "失败",
    UpdateResult.CANCELLED: "取消",
}

_HEADERS = ["时间", "从", "到", "结果", "阶段", "回滚"]


def _fmt_time(dt) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M") if dt else ""


class HistoryDialog(QDialog):
    def __init__(self, app_name: str, records: "list[UpdateRecord]", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{app_name} — 更新历史")
        self.setModal(True)
        self.resize(680, 360)

        layout = QVBoxLayout(self)
        table = QTableWidget(len(records), len(_HEADERS), self)
        table.setHorizontalHeaderLabels(_HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)

        for r, rec in enumerate(records):
            cells = [
                _fmt_time(rec.started_at),
                rec.from_version or "—",
                rec.to_version or "—",
                _RESULT_ZH.get(rec.result, rec.result.value),
                _STAGE_ZH.get(rec.failed_stage, "—") if rec.failed_stage else "—",
                "已回滚" if rec.rolled_back else "—",
            ]
            for c, text in enumerate(cells):
                table.setItem(r, c, QTableWidgetItem(text))
            if rec.error_message:
                table.item(r, 3).setToolTip(rec.error_message)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.Close, self)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.Close).setText("关闭")
        layout.addWidget(btns)
