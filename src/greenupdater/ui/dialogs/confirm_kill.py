"""结束进程确认对话框（对应 docs/design/03-ui.md §6）。

更新到 kill_process 阶段、检测到目标运行中时弹出。"结束并继续" → 由 worker 调
ProcessManager.terminate；"取消" → 该 app 中止（记为 cancelled，不算失败）。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)


def _proc_label(p) -> str:
    """安全读取进程名（进程可能已退出）。"""
    try:
        name = p.name()
    except Exception:  # noqa: BLE001 - psutil 异常类型多
        name = "?"
    try:
        pid = p.pid
    except Exception:  # noqa: BLE001
        pid = "?"
    return f"{name} (PID {pid})"


class ConfirmKillDialog(QDialog):
    def __init__(self, app_name: str, procs: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("目标程序正在运行")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{app_name} 正在运行，更新前需要结束它。"))
        layout.addWidget(QLabel("将结束以下进程："))

        lst = QListWidget(self)
        for p in procs:
            lst.addItem(_proc_label(p))
        layout.addWidget(lst)

        layout.addWidget(QLabel("未保存的数据可能丢失。"))

        btns = QDialogButtonBox(self)
        btns.addButton("结束并继续", QDialogButtonBox.AcceptRole)
        btns.addButton("取消", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
