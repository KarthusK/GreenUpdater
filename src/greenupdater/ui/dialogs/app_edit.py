"""添加 / 编辑对话框（对应 docs/design/03-ui.md §4）。

分区表单，字段对应 AppConfig；另含"本地当前版本"（属 App 运行态，controller 用 save_state 存）。
确定前用 pydantic 校验（正则合法、必填非空）；关闭"更新前备份"时即时警告。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from pydantic import ValidationError

from greenupdater.domain import LocalVersionDetector, parse_repo_ref
from greenupdater.models import (
    App,
    AppConfig,
    SourceType,
    VersionDetectSource,
    VersionSource,
)


class AppEditDialog(QDialog):
    def __init__(self, app: App | None = None, parent=None) -> None:
        super().__init__(parent)
        self._editing = app is not None
        self._version_src = app.current_version_src if app else VersionDetectSource.UNKNOWN
        self._config: AppConfig | None = None
        self._local_version: str | None = None
        # 上次成功解析的 (owner, repo)；用于失焦时判断"解析结果是否变化"，避免重复提示
        self._last_parsed_repo: tuple[str, str] | None = (
            (app.repo_owner, app.repo_name) if app else None
        )

        self.setWindowTitle("编辑软件" if self._editing else "添加软件")
        self.setModal(True)
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(self._basic_group(app))
        root.addWidget(self._match_group(app))
        root.addWidget(self._install_group(app))
        root.addWidget(self._behavior_group(app))

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.button(QDialogButtonBox.Ok).setText("确定")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ---------- 分区构建 ----------
    def _basic_group(self, app: App | None) -> QWidget:
        g = QGroupBox("基本信息", self)
        f = QFormLayout(g)
        self.ed_name = QLineEdit(app.name if app else "", g)
        f.addRow("名称*", self.ed_name)

        # 仓库只用一个输入框：用户可直接粘贴 GitHub 的 HTTPS / SSH / gh CLI 克隆地址，
        # 失焦或确定时统一解析成 owner/repo（解析逻辑在 domain.repo，便于单测）。
        row = QHBoxLayout()
        self.ed_repo_ref = QLineEdit(f"{app.repo_owner}/{app.repo_name}" if app else "", g)
        self.ed_repo_ref.setPlaceholderText("owner/repo")
        self.ed_repo_ref.editingFinished.connect(self._on_repo_ref_edited)
        self.lbl_source = QLabel("GitHub", g)  # 仅 GitHub，其余为预留
        row.addWidget(self.ed_repo_ref, 1)
        row.addWidget(self.lbl_source)
        f.addRow("仓库*", _wrap(row, g))
        return g

    def _match_group(self, app: App | None) -> QWidget:
        g = QGroupBox("版本匹配", self)
        f = QFormLayout(g)
        self.ed_asset_pattern = QLineEdit(app.asset_pattern if app else "", g)
        f.addRow("资产匹配正则*", self.ed_asset_pattern)

        ver_row = QHBoxLayout()
        self.rb_tag = QRadioButton("tag", g)
        self.rb_asset = QRadioButton("资产文件名", g)
        self._ver_group = QButtonGroup(g)
        self._ver_group.addButton(self.rb_tag)
        self._ver_group.addButton(self.rb_asset)
        src = app.version_source if app else VersionSource.TAG
        self.rb_asset.setChecked(src == VersionSource.ASSET_NAME)
        self.rb_tag.setChecked(src == VersionSource.TAG)
        ver_row.addWidget(self.rb_tag)
        ver_row.addWidget(self.rb_asset)
        ver_row.addStretch(1)
        f.addRow("版本来源", _wrap(ver_row, g))

        self.ed_version_pattern = QLineEdit(app.version_pattern if app else "", g)
        self.ed_version_pattern.setPlaceholderText("留空=用整体 tag/名")
        f.addRow("版本提取正则", self.ed_version_pattern)

        self.chk_prerelease = QCheckBox("包含预发布版本", g)
        self.chk_prerelease.setChecked(bool(app.include_prerelease) if app else False)
        f.addRow("", self.chk_prerelease)
        return g

    def _install_group(self, app: App | None) -> QWidget:
        g = QGroupBox("安装位置", self)
        f = QFormLayout(g)

        dir_row = QHBoxLayout()
        self.ed_target = QLineEdit(str(app.target_dir) if app else "", g)
        btn_browse = QPushButton("浏览…", g)
        btn_browse.clicked.connect(self._on_browse)
        dir_row.addWidget(self.ed_target, 1)
        dir_row.addWidget(btn_browse)
        f.addRow("目标目录*", _wrap(dir_row, g))

        exe_row = QHBoxLayout()
        self.ed_exe = QLineEdit(app.exe_relpath if app else "", g)
        btn_detect = QPushButton("探测版本", g)
        btn_detect.clicked.connect(self._on_detect)
        exe_row.addWidget(self.ed_exe, 1)
        exe_row.addWidget(btn_detect)
        f.addRow("可执行文件相对路径", _wrap(exe_row, g))

        ver_row = QHBoxLayout()
        self.ed_local_version = QLineEdit(
            (app.current_version if app and app.current_version else ""), g
        )
        self.lbl_version_src = QLabel(self._src_text(self._version_src), g)
        ver_row.addWidget(self.ed_local_version, 1)
        ver_row.addWidget(self.lbl_version_src)
        f.addRow("本地当前版本", _wrap(ver_row, g))
        return g

    def _behavior_group(self, app: App | None) -> QWidget:
        g = QGroupBox("更新行为", self)
        f = QFormLayout(g)
        f.addRow("进程名列表", self._list_editor(g, "process", app.process_names if app else []))
        f.addRow("排除路径(保留)", self._list_editor(g, "exclude", app.exclude_paths if app else []))

        self.chk_backup = QCheckBox("更新前备份(完整快照)", g)
        self.chk_backup.setChecked(bool(app.backup_enabled) if app else True)
        self.chk_backup.toggled.connect(self._on_backup_toggled)
        f.addRow("", self.chk_backup)

        self.chk_enabled = QCheckBox("启用(参与批量操作)", g)
        self.chk_enabled.setChecked(bool(app.enabled) if app else True)
        f.addRow("", self.chk_enabled)
        return g

    def _list_editor(self, parent, kind: str, items: list[str]) -> QWidget:
        w = QWidget(parent)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lst = QListWidget(w)
        lst.addItems(items)
        col = QVBoxLayout()
        btn_add = QPushButton("+ 添加", w)
        btn_del = QPushButton("− 删除", w)
        btn_add.clicked.connect(lambda: self._on_list_add(lst))
        btn_del.clicked.connect(lambda: self._on_list_del(lst))
        col.addWidget(btn_add)
        col.addWidget(btn_del)
        col.addStretch(1)
        lay.addWidget(lst, 1)
        lay.addLayout(col)
        if kind == "process":
            self._proc_list = lst
        else:
            self._exclude_list = lst
        return w

    # ---------- 交互 ----------
    def _on_repo_ref_edited(self) -> None:
        """失焦/回车时就地规范化，让用户立刻看到识别结果；失败则保持原样待提交时报错。"""
        parsed = parse_repo_ref(self.ed_repo_ref.text())
        if not parsed:
            return
        self.ed_repo_ref.setText(f"{parsed[0]}/{parsed[1]}")
        # 仅在解析结果发生变化时提示，避免同一仓库反复打扰（用户拒绝后不再追问）
        if parsed == self._last_parsed_repo:
            return
        self._last_parsed_repo = parsed
        self._maybe_prompt_name(parsed[1])

    def _maybe_prompt_name(self, repo: str) -> None:
        """名称与仓库名不一致时建议同步；已一致则不处理。"""
        if self.ed_name.text().strip() == repo:
            return
        ret = QMessageBox.question(
            self,
            "名称建议",
            f'名称与仓库名 "{repo}" 不一致，是否将名称改为 "{repo}"？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.ed_name.setText(repo)

    def _on_browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择目标目录", self.ed_target.text())
        if d:
            self.ed_target.setText(d)

    def _on_detect(self) -> None:
        target = self.ed_target.text().strip()
        exe = self.ed_exe.text().strip() or None
        if not target or not exe:
            QMessageBox.information(self, "探测版本", "请先填写目标目录与可执行文件相对路径。")
            return
        ver, src = LocalVersionDetector().detect(Path(target), exe)
        if ver:
            self.ed_local_version.setText(ver)
            self._version_src = src
        else:
            self._version_src = VersionDetectSource.UNKNOWN
            QMessageBox.information(self, "探测版本", "未能从 PE 版本资源探测到，请手动填写。")
        self.lbl_version_src.setText(self._src_text(self._version_src))

    def _on_backup_toggled(self, checked: bool) -> None:
        if not checked:
            QMessageBox.warning(
                self,
                "关闭备份",
                "关闭后备份不会创建，覆盖阶段失败将无法回滚，目标目录可能损坏。",
            )

    def _on_list_add(self, lst: QListWidget) -> None:
        text, ok = QInputDialog.getText(self, "添加", "值：")
        if ok and text.strip():
            lst.addItem(text.strip())

    def _on_list_del(self, lst: QListWidget) -> None:
        for item in lst.selectedItems():
            lst.takeItem(lst.row(item))

    # ---------- 校验 / 输出 ----------
    def _on_accept(self) -> None:
        parsed = parse_repo_ref(self.ed_repo_ref.text())
        if parsed is None:
            QMessageBox.critical(
                self,
                "校验失败",
                "无法识别仓库地址。\n\n"
                "请填 owner/repo，或粘贴 GitHub 的克隆地址：\n"
                "  https://github.com/owner/repo.git\n"
                "  git@github.com:owner/repo.git\n"
                "  gh repo clone owner/repo",
            )
            return
        owner, repo = parsed
        try:
            cfg = AppConfig(
                name=self.ed_name.text().strip(),
                source_type=SourceType.GITHUB,
                repo_owner=owner,
                repo_name=repo,
                asset_pattern=self.ed_asset_pattern.text().strip(),
                version_source=(
                    VersionSource.ASSET_NAME if self.rb_asset.isChecked() else VersionSource.TAG
                ),
                version_pattern=self.ed_version_pattern.text().strip() or None,
                include_prerelease=self.chk_prerelease.isChecked(),
                target_dir=Path(self.ed_target.text().strip() or "."),
                exe_relpath=self.ed_exe.text().strip() or None,
                process_names=_list_items(self._proc_list),
                exclude_paths=_list_items(self._exclude_list),
                backup_enabled=self.chk_backup.isChecked(),
                enabled=self.chk_enabled.isChecked(),
            )
        except ValidationError as exc:
            QMessageBox.critical(self, "校验失败", _format_errors(exc))
            return

        self._config = cfg
        text = self.ed_local_version.text().strip()
        if text:
            self._local_version = text
            # 用户手改过则视为手填（除非刚探测为 PE）
            if self._version_src == VersionDetectSource.UNKNOWN:
                self._version_src = VersionDetectSource.MANUAL
        else:
            self._local_version = None
        self.accept()

    def get_config(self) -> AppConfig | None:
        return self._config

    def get_local_version(self) -> "tuple[str | None, VersionDetectSource]":
        return self._local_version, self._version_src

    @staticmethod
    def _src_text(src: VersionDetectSource) -> str:
        return {
            VersionDetectSource.PE: "来源: PE自动",
            VersionDetectSource.MANUAL: "来源: 手填",
            VersionDetectSource.UNKNOWN: "来源: 未知",
        }.get(src, "来源: 未知")


def _wrap(layout, parent) -> QWidget:
    # 必须清零内边距：否则默认布局边距把行内容下推/右移，与同组其他字段错位
    layout.setContentsMargins(0, 0, 0, 0)
    w = QWidget(parent)
    w.setLayout(layout)
    return w


def _list_items(lst: QListWidget) -> list[str]:
    return [lst.item(i).text() for i in range(lst.count())]


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()))
        lines.append(f"{loc}: {e.get('msg')}")
    return "\n".join(lines) or str(exc)
