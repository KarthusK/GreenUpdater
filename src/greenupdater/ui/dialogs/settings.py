"""设置对话框（对应 docs/design/03-ui.md §5）。

Token 走 keyring（系统凭据库），不落 SQLite / 导出 JSON；keyring 不可用时输入框禁用 + 红字提示，
降级匿名访问。代理 / 日志级别 / 默认预发布 写入 settings 表（确定时保存）。便携目录只读展示。
"""
from __future__ import annotations

import subprocess
import sys

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from greenupdater.infra import KeyringUnavailableError, Paths, TokenStore
from greenupdater.infra.repository import ConfigRepository
from greenupdater.models import Settings

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class SettingsDialog(QDialog):
    def __init__(
        self,
        repo: ConfigRepository,
        paths: Paths,
        tokens: TokenStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._paths = paths
        self._tokens = tokens

        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(560)

        settings = repo.get_settings()

        root = QVBoxLayout(self)
        root.addWidget(self._github_group())
        root.addWidget(self._network_group(settings))
        root.addWidget(self._log_group(settings))
        root.addWidget(self._default_group(settings))
        root.addWidget(self._dirs_group())

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.button(QDialogButtonBox.Ok).setText("确定")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ---------- 分区 ----------
    def _github_group(self) -> QWidget:
        g = QGroupBox("GitHub", self)
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        self.ed_token = QLineEdit(g)
        self.ed_token.setEchoMode(QLineEdit.Password)
        self.ed_token.setPlaceholderText("个人访问令牌 (PAT)")
        btn_save = QPushButton("保存", g)
        btn_clear = QPushButton("清除", g)
        btn_save.clicked.connect(self._on_token_save)
        btn_clear.clicked.connect(self._on_token_clear)
        row.addWidget(self.ed_token, 1)
        row.addWidget(btn_save)
        row.addWidget(btn_clear)
        lay.addLayout(row)

        if self._tokens.is_available():
            hint = QLabel(
                "ⓘ Token 写入【系统凭据库】(Windows 凭据管理器 / Linux Secret Service)，"
                "不随程序目录便携携带；换机器需重新设置。",
                g,
            )
            hint.setWordWrap(True)
            lay.addWidget(hint)
            current = self._tokens.get()
            self.ed_token.setText(current or "")
        else:
            self.ed_token.setEnabled(False)
            btn_save.setEnabled(False)
            btn_clear.setEnabled(False)
            warn = QLabel(
                "当前系统无可用凭据库，将以匿名访问，受限流约 60 次/小时。", g
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #c0392b;")
            lay.addWidget(warn)
        return g

    def _network_group(self, s: Settings) -> QWidget:
        g = QGroupBox("网络", self)
        lay = QVBoxLayout(g)
        self.chk_proxy = QCheckBox("启用代理", g)
        self.chk_proxy.setChecked(s.proxy_enabled)
        self.chk_proxy.toggled.connect(self._on_proxy_toggled)
        lay.addWidget(self.chk_proxy)

        row = QHBoxLayout()
        self.ed_proxy = QLineEdit(s.proxy_url or "", g)
        self.ed_proxy.setPlaceholderText("http://127.0.0.1:7890")
        self.ed_proxy.setEnabled(s.proxy_enabled)
        row.addWidget(QLabel("代理 URL", g))
        row.addWidget(self.ed_proxy, 1)
        lay.addLayout(row)
        return g

    def _log_group(self, s: Settings) -> QWidget:
        g = QGroupBox("日志", self)
        lay = QHBoxLayout(g)
        lay.addWidget(QLabel("级别", g))
        self.cb_level = QComboBox(g)
        self.cb_level.addItems(_LOG_LEVELS)
        level = s.log_level.upper() if s.log_level else "INFO"
        self.cb_level.setCurrentText(level if level in _LOG_LEVELS else "INFO")
        lay.addWidget(self.cb_level)
        lay.addStretch(1)
        btn_open = QPushButton("打开日志目录", g)
        btn_open.clicked.connect(lambda: _open_path(self._paths.logs_dir))
        lay.addWidget(btn_open)
        return g

    def _default_group(self, s: Settings) -> QWidget:
        g = QGroupBox("默认项", self)
        lay = QVBoxLayout(g)
        self.chk_prerelease = QCheckBox("新增软件默认包含预发布", g)
        self.chk_prerelease.setChecked(s.default_include_prerelease)
        lay.addWidget(self.chk_prerelease)
        return g

    def _dirs_group(self) -> QWidget:
        g = QGroupBox("便携目录（只读）", self)
        f = QFormLayout(g)
        # (显示标签, 展示路径, 打开的目录)
        for label, shown, open_dir in (
            ("数据库", self._paths.db_path, self._paths.db_path.parent),
            ("备份", self._paths.backups_root, self._paths.backups_root),
            ("临时", self._paths.tmp_root, self._paths.tmp_root),
        ):
            f.addRow(label, self._dir_row(str(shown), open_dir))
        return g

    def _dir_row(self, text: str, open_dir) -> QWidget:
        w = QWidget(self)
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(text, w)
        ed.setReadOnly(True)
        btn = QPushButton("打开", w)
        btn.clicked.connect(lambda: _open_path(open_dir))
        row.addWidget(ed, 1)
        row.addWidget(btn)
        return w

    # ---------- 交互 ----------
    def _on_proxy_toggled(self, checked: bool) -> None:
        self.ed_proxy.setEnabled(checked)

    def _on_token_save(self) -> None:
        token = self.ed_token.text().strip()
        if not token:
            QMessageBox.information(self, "Token", "请输入 Token。")
            return
        try:
            self._tokens.set(token)
        except KeyringUnavailableError:
            QMessageBox.critical(self, "Token", "当前系统无可用凭据库，无法保存 Token。")
            return
        QMessageBox.information(self, "Token", "已保存到系统凭据库。")

    def _on_token_clear(self) -> None:
        self._tokens.clear()
        self.ed_token.clear()
        QMessageBox.information(self, "Token", "已清除。")

    def _on_accept(self) -> None:
        proxy_url = self.ed_proxy.text().strip() or None
        if self.chk_proxy.isChecked() and not proxy_url:
            QMessageBox.information(self, "代理", "启用代理需填写代理 URL。")
            return
        settings = Settings(
            proxy_enabled=self.chk_proxy.isChecked(),
            proxy_url=proxy_url if self.chk_proxy.isChecked() else None,
            log_level=self.cb_level.currentText(),
            default_include_prerelease=self.chk_prerelease.isChecked(),
        )
        self._repo.save_settings(settings)
        self.accept()

    def get_settings(self) -> Settings:
        return self._repo.get_settings()


def _open_path(path) -> None:
    """用系统文件管理器打开目录（跨平台，best-effort）。"""
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", p])  # noqa: S603,S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", p])  # noqa: S603,S607
    except OSError:
        pass
