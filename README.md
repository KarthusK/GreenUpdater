# GreenUpdater（绿色更新器）

管理**便携版 / 绿色版软件**更新的开源桌面工具。从 GitHub Releases 检查新版本、下载压缩包、安全解压并覆盖到目标目录，尽量保留用户配置；覆盖失败时可手动回滚到更新前的完整快照。

- **纯前台、完全手动**：无后台常驻、无定时任务、无系统托盘。打开窗口 → 勾选软件 → 点【检查】/【更新】→ 查看结果。
- **Windows 优先**，后续兼容 Linux。
- 技术栈：Python 3.11+ / PySide6 / httpx / SQLite / keyring / psutil / py7zr / loguru，Nuitka 打包。

> 📖 **使用手册见 [`docs/usage.md`](docs/usage.md)**（安装、添加软件、正则匹配、Token、回滚、便携目录、FAQ）。
> 内部需求与架构设计见 [`docs/design/`](docs/design/README.md)。

## 使用

1. **启动**：双击绿色版 `GreenUpdater.exe`，或开发态 `python run.py`。
2. **添加软件**：点【添加】，填 GitHub `owner/repo`、资产匹配正则、目标目录、（可选）进程名与排除路径。
3. **检查**：勾选要处理的行 → 点【检查】，只读拉取最新版本、更新状态列。
4. **更新**：点【更新】，顺序执行「下载 → 解压 → 结束进程 → 快照 → 覆盖」；进度条 + 终端面板实时反馈，可随时【取消】。
5. **回滚**：覆盖阶段失败且存在快照的行标记「可回滚」，右键「回滚到此版本」还原程序文件（保留用户数据）。

> GitHub Token 存在**系统凭据库**（不入库、不进导出 JSON、不随便携目录携带），匿名访问限流约 60 次/小时。详见使用手册第 6 节。

## 文档

| 文档 | 内容 |
| --- | --- |
| [使用指南](docs/usage.md) | 面向用户：安装、操作、配置、FAQ |
| [设计总览](docs/design/README.md) | 需求收敛结论、技术栈、高层架构 |
| [数据模型](docs/design/01-data-model.md) | SQLite 表结构、枚举、pydantic 模型、导入导出 schema |
| [核心模块接口](docs/design/02-modules.md) | 各层类 / 方法 / 职责，Provider 适配器、编排、回滚 |
| [UI 布局与交互](docs/design/03-ui.md) | 窗口布局、对话框、交互时序、线程 / 信号 |
| [项目目录结构](docs/design/04-structure.md) | 分层目录树、便携数据布局、测试组织 |
| [技术选型复核](docs/design/05-tech-stack.md) | 库清单与理由、打包注意点、风险 |

## 开发

```bash
# 一键：创建虚拟环境 → 安装本项目(editable) → 启动
python run.py

# 或手动
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Windows
# .venv/bin/pip install -e ".[dev]"        # Linux/macOS
.venv/Scripts/python -m greenupdater
```

## 测试

```bash
pytest                              # 全量（单元 + UI）
pytest tests/unit                   # 仅纯逻辑单元
QT_QPA_PLATFORM=offscreen pytest    # 无显示器环境跑 UI 测试（CI）
```

UI 测试用 `pytest-qt`；无需真实系统凭据库（Token 相关测试走内存后端）。

## 打包

```bash
python build.py            # Nuitka standalone（文件夹，杀软误报少）
python build.py --onefile  # 单文件（分发方便，误报率较高）
```

产物为绿色版 `GreenUpdater.exe`，双击即运行；配置 / 日志 / 备份 / 数据库都生成在 exe 同级目录，整目录拷贝即迁移。

## 项目结构

```
src/greenupdater/
├── models/     # pydantic 模型与枚举（数据契约）
├── infra/      # SQLite 仓库 / keyring / loguru / 便携路径
├── domain/     # 纯逻辑：Provider / 版本 / 下载 / 解压 / 备份 / 覆盖 / 进程
├── service/    # UpdateOrchestrator：编排整条更新流水线
├── ui/         # PySide6：主窗口 / 列表模型 / worker / 对话框 / 单实例
├── app.py      # 装配根：把各层连起来，接信号槽
└── __main__.py # 入口
tests/          # unit(domain/service/infra) + ui(pytest-qt)
```

严格单向依赖：`ui → service → domain → infra`，领域层不 import PySide6，便于单测。分层细节见[设计总览](docs/design/README.md)。

## 许可证


[MIT](LICENSE)。GUI 依赖 PySide6（LGPL），以动态链接方式使用。界面图标来自 [Tabler Icons](https://tabler.io/icons)（MIT），声明见 [src/greenupdater/ui/icons/LICENSE](src/greenupdater/ui/icons/LICENSE)。
