"""单实例守卫（对应 docs/design/03-ui.md §11）。

用 QLocalServer/QLocalSocket 命名管道：首个实例启动服务端；后续实例连上发一条激活消息后自行退出，
首个实例收到消息则把主窗口 show/raise/activate。避免两个手动更新流程互相踩。
"""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

_SERVER_NAME = "GreenUpdater.SingleInstance"
_MSG_ACTIVATE = b"activate"


class SingleInstance(QObject):
    """若已有实例在运行，``is_primary`` 为 False（调用方应退出）。"""

    def __init__(self, name: str = _SERVER_NAME, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None
        self.is_primary = True
        self.on_activate = None  # 可调用：收到激活消息时触发

        if self._connect_existing():
            # 已有实例：发消息请求激活，本实例随后应退出
            self.is_primary = False
            return

        # 清理可能残留的同名服务端（上次异常退出遗留）后自建
        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        server.newConnection.connect(self._on_new_connection)
        if server.listen(self._name):
            self._server = server
        else:
            # 监听失败也当作非主实例，避免双开
            self.is_primary = False

    def _connect_existing(self) -> bool:
        """尝试连接已存在的服务端；成功即发消息并返回 True。"""
        socket = QLocalSocket(self)
        socket.connectToServer(self._name)
        if not socket.waitForConnected(300):
            socket.abort()
            socket.deleteLater()
            return False
        socket.write(_MSG_ACTIVATE)
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        socket.deleteLater()
        return True

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._on_ready_read(conn))

    def _on_ready_read(self, conn: QLocalSocket) -> None:
        data = conn.readAll()
        conn.deleteLater()
        if bytes(data).startswith(_MSG_ACTIVATE) and callable(self.on_activate):
            self.on_activate()

    def cleanup(self) -> None:
        if self._server is not None:
            self._server.close()
            QLocalServer.removeServer(self._name)
            self._server = None


def activate_main_window(window) -> None:
    """把主窗口拉到前台（供 on_activate 使用）。"""
    window.show()
    if window.isMinimized():
        window.showNormal()
    window.raise_()
    window.activateWindow()
    app = QApplication.instance()
    if app is not None:
        app.setQuitOnLastWindowClosed(True)
