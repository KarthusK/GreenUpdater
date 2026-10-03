# AGENT.md — GreenUpdater 协作指南

给 AI 编码助手的项目上下文与约束。动手前先读这一页。

## 项目是什么

**GreenUpdater（绿色更新器）**：管理便携版/绿色版软件更新的桌面工具。从 GitHub Releases 检查新版本 → 下载压缩包 → 安全解压 → 覆盖目标目录（保留用户配置）→ 覆盖失败可手动回滚。

- **纯前台、完全手动**：无后台常驻、无定时、无托盘、无通知。
- **Windows 优先**，兼顾 Linux。仅中文界面。
- 当前状态：models → infra → domain → service → ui 五层已实现，测试全绿。

## 技术栈

Python 3.11+ · PySide6（Qt for Python，LGPL）· httpx（同步，跑在 QThread）· pydantic v2 · SQLite（stdlib）· keyring · psutil · py7zr · loguru。GitHub API 直接调 REST，**不引入 PyGithub**。打包用 Nuitka。

## 命令

```bash
python run.py                              # 开发态一键启动（建 venv + editable 安装 + 运行）
.venv/Scripts/python -m greenupdater       # 直接运行（Windows）
pytest                                     # 全量测试
pytest tests/unit                          # 仅纯逻辑单元
QT_QPA_PLATFORM=offscreen pytest           # 无显示器环境跑 UI 测试（CI）
python build.py [--onefile]                # Nuitka 打包，产物在 build/
ruff check src tests                       # 代码检查（配置见 pyproject，line-length=100）
```

- src-layout：源码在 `src/`，`pyproject.toml` 已设 `pythonpath=["src"]`、`testpaths=["tests"]`。
- 不要为测试触碰真实系统凭据库：Token 相关测试用**内存 keyring 后端**。

## 架构（强约束）

严格**单向依赖**：

```
ui (PySide6)  →  service (UpdateOrchestrator)  →  domain (纯逻辑)  →  infra (SQLite/keyring/loguru/paths)
```

- **domain 层绝不 import PySide6**，保持纯逻辑可单测。
- **models** 是数据契约（pydantic 模型 + 枚举），被各层共享。
- UI 只做展示与交互，业务动作以 **intent 信号**抛出，由 `app.py` 的 `Controller` 连接执行；MainWindow 只从 repo **读**，不做写操作。
- 装配根是 `src/greenupdater/app.py`：构建 Paths/日志/Repo/TokenStore/Orchestrator，worker 移入 QThread，连接所有信号槽。

### 目录

```
src/greenupdater/
├── models/   # app.py(AppConfig/App) enums.py history.py settings.py
├── infra/    # paths.py db.py repository.py(ConfigRepository) tokenstore.py logging.py
├── domain/   # errors.py events.py version.py detect.py download.py extract.py
│             # backup.py overwrite.py process.py _fs.py provider/(base,github,matcher)
├── service/  # orchestrator.py(UpdateOrchestrator)
├── ui/       # main_window.py worker.py single_instance.py app.py(在上级)
│             # models/(app_table_model) widgets/(terminal_view) dialogs/(5 个)
├── app.py    # Controller + main()
└── __main__.py
tests/        # unit/{domain,service,infra} + ui/（pytest-qt）
docs/         # usage.md(用户手册,发布) + design/(内部设计,gitignore)
```

## 关键实现约定（改动时务必遵守）

- **Token 只进 keyring**（系统凭据库）：绝不写 SQLite、绝不进导入导出 JSON、不随便携目录携带。keyring 不可用时降级匿名并提示。
- **便携数据**都在程序目录内：`greenupdater.db` / `logs/` / `backups/<uid>/` / `tmp/<uid>/`。可用环境变量 `GREENUPDATER_HOME` 覆盖数据根。
- **解压防 Zip Slip**（路径穿越）是硬性要求；`Extractor` 校验每个条目不得越出目标目录。
- **SHA256 校验**：Release 提供则比对，不一致失败；缺失仅警告不失败。
- **覆盖只增不删**：`Overwriter` 只新增/覆盖文件，不删除目标目录其它内容。
- **回滚模型**：失败**不自动回滚**；仅**覆盖阶段失败且存在快照**时置 `rollback_available`，用户手动触发；回滚跳过 `exclude_paths` 以保留当前用户数据。每个软件只保留 1 份最近快照。
- **更新流水线阶段顺序**固定：`check → download → extract → kill_process → snapshot → overwrite`（见 `UpdateStage` 枚举）。下载/解压在临时目录，这两步失败不动目标目录。
- **顺序执行**，不并行；批量更新逐个处理。
- **结束进程需用户确认**（弹框），且校验进程 exe 位于目标目录，避免误杀同名进程。

### 线程 / 信号模型

- 耗时操作全在 worker 线程（`UpdateWorker` moveToThread QThread）。
- 领域 `UpdateListener` 回调 → `_QtListener` → worker 的 Qt 信号（队列连接跨线程投递到 UI）。
- **阻塞式用户决策**（`ask_kill` / `ask_asset`）用 `Qt.BlockingQueuedConnection` + `_Response` 容器：worker 发信号后阻塞，UI 弹模态框把结果写回 `resp.value`。依赖 worker 与 UI 分处不同线程。
- **跨线程不改共享可变对象**：worker 只发 `sig_app_changed(uid)`，UI 在主线程用 `repo.get_app(uid)` 重新读取刷新该行（repo 有 RLock）。
- 进度信号高频，UI 侧按「百分比变化或 ≥100ms 间隔」节流刷新。

## 编码风格

- 注释/docstring 用**中文**，聚焦「为什么」而非「做什么」；默认少写注释。
- 枚举继承 `str` 以便与 SQLite TEXT / JSON 直接互转。
- 校验用 pydantic v2（正则合法性、必填非空等在模型层）。
- ruff 规则集：`E,F,I,UP,B`，行宽 100。
- 与用户交流用中文。

## 协作方式（重要）

- **按模块增量推进**，一次一层/一块，配测试验证，做完与用户确认再继续；**不要一次性倒出全部代码**。
- 不要超出任务范围加功能、抽象或「顺手重构」；bug 修复就只修 bug。
- 安装依赖 / 改环境前先征得同意。
- 设计事实来源是 `docs/design/`（内部，可能不发布）；用户手册是 `docs/usage.md`（发布）。改了行为就同步更新对应文档。
- **所有生成的临时文件统一放在仓库根的 `tmp/` 下**（验证脚本、diff 对比、中间产物等）；在该目录内创建文件是允许的，不要散落到项目根或其它目录；`tmp/` 已在 .gitignore 中，不会进版本库。

## Commit 规范
- git 操作只做用户字面要求的范围（「生成 commit」不等于 add+commit+push）。
- 使用多行形式：首行 `type: 中文概要`（type 用 feat/fix/docs/refactor/chore），空一行后用 `- ` 列出要点
- 要点条数控制在 1-4 行，概括改动与行为影响，不写代码细节
- 只提交本次相关文件，不加多余文件
