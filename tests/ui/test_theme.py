"""theme.qss 模板与 colors.py 令牌的一致性测试（不创建 QApplication）。"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from greenupdater.ui import colors, theme

_QSS_PATH = Path(theme.__file__).with_name("theme.qss")


def test_qss_rendered_without_placeholders():
    """渲染后不应残留 $TOKEN 或未替换的花括号转义痕迹。"""
    assert "$" not in theme.QSS
    assert "color: #e8eaed" in theme.QSS  # TEXT 已代入
    assert "background-color: #1e1f22" in theme.QSS  # WINDOW_BG 已代入


def test_qss_placeholders_all_known_tokens():
    """模板占位符必须都在 colors.__all__ 中，防止拼错令牌名。"""
    text = _QSS_PATH.read_text(encoding="utf-8")
    used = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", text))
    assert used, "模板中未找到占位符，检查 theme.qss 是否被误改"
    unknown = used - set(colors.__all__)
    assert not unknown, f"theme.qss 使用了未定义令牌: {unknown}"


def test_theme_reexports_color_tokens():
    """既有 from theme import X 的引用方依赖 re-export，抽查关键令牌。"""
    for name in ("DANGER", "ICON", "ACCENT", "STATUS_OK", "TEXT", "TERMINAL_BG"):
        assert getattr(theme, name) == getattr(colors, name)


def test_status_ok_follows_accent():
    """状态绿跟随品牌绿：同一对象，杜绝两者再次分叉。"""
    assert colors.STATUS_OK is colors.ACCENT


def test_qss_has_no_hardcoded_accent():
    """强调色必须全部走令牌；写死会让改色只生效一半（曾出现 9 处硬编码）。"""
    text = _QSS_PATH.read_text(encoding="utf-8").lower()
    for literal in ("74, 222, 128", "4ade80", "86e7ae", "22c55e"):
        assert literal not in text, f"theme.qss 出现写死的强调色值: {literal}"


# ---------- 对比度辅助（WCAG 相对亮度） ----------


def _rel_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(raw[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_accent_contrast_within_band():
    """品牌绿需落在 6.0~7.5 亮度带：太亮刺眼、太暗则按钮文字发灰。"""
    ratio = _contrast(colors.ACCENT, colors.WINDOW_BG)
    assert 6.0 <= ratio <= 7.5, f"ACCENT 对比度 {ratio:.2f} 越出 6.0~7.5"


def test_primary_button_text_stays_readable():
    """主按钮深字在三态底色上都必须满足 AA 正文 4.5（pressed 最易踩线）。"""
    for name in ("ACCENT", "ACCENT_HOVER", "ACCENT_PRESSED"):
        bg = getattr(colors, name)
        ratio = _contrast(colors.ACCENT_TEXT, bg)
        assert ratio >= 4.5, f"{name} 上的按钮文字对比度仅 {ratio:.2f}"


# ---------- 图标（icons/*.svg） ----------

_ICONS_DIR = Path(theme.__file__).with_name("icons")
_MAIN_WINDOW = Path(theme.__file__).with_name("main_window.py")


def test_all_icon_files_exist():
    """ICON_NAMES 里每个名字都必须有对应 .svg 文件。"""
    missing = [n for n in theme.ICON_NAMES if not (_ICONS_DIR / f"{n}.svg").is_file()]
    assert not missing, f"缺少图标文件: {missing}"


def test_no_orphan_icon_files():
    """icons/ 下不应有多余的 .svg（改名后留下的孤儿文件）。"""
    on_disk = {p.stem for p in _ICONS_DIR.glob("*.svg")}
    assert on_disk == set(theme.ICON_NAMES), f"多余: {on_disk - set(theme.ICON_NAMES)}"


def test_icons_use_color_placeholder():
    """图标必须用 currentColor 占位、且不得写死颜色，否则三态染色失效。"""
    for name in theme.ICON_NAMES:
        text = (_ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")
        assert theme._COLOR_PLACEHOLDER in text, f"{name}.svg 缺少 currentColor 占位"
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", text), f"{name}.svg 写死了颜色"


def test_icon_names_match_usage():
    """main_window.py 里用到的图标名都必须在 ICON_NAMES 内，防止拼错。"""
    used = set(re.findall(r'icon_name="([^"]+)"', _MAIN_WINDOW.read_text(encoding="utf-8")))
    assert used, "未在 main_window.py 中解析到 icon_name，检查正则是否失效"
    unknown = used - set(theme.ICON_NAMES)
    assert not unknown, f"main_window.py 引用了未定义的图标: {unknown}"


# ---------- 应用图标（ui/app.ico） ----------

_APP_ICON = Path(theme.__file__).with_name("app.ico")
_BUILD_PY = Path(theme.__file__).resolve().parents[3] / "build.py"


def test_app_icon_file_exists():
    """应用图标必须存在于包内（打包后靠它设窗口图标）。"""
    assert _APP_ICON.is_file(), f"缺少应用图标: {_APP_ICON}"


def test_app_icon_has_multiple_sizes():
    """ico 必须含多个尺寸，否则任务栏 / 高分屏会用低清图。"""
    data = _APP_ICON.read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00", "不是合法的 ICO 文件"
    assert struct.unpack("<H", data[4:6])[0] >= 3, "内嵌尺寸过少"


def test_build_icon_path_is_valid():
    """build.py 的 ICON 必须指向真实存在的文件。

    历史 bug：它指向不存在的 packaging/nuitka/app.ico，又用 exists() 静默跳过，
    导致打包产物长期没有图标。此测试锁死该回归。
    """
    source = _BUILD_PY.read_text(encoding="utf-8")
    match = re.search(r'^ICON = ROOT((?: / "[^"]+")+)$', source, re.M)
    assert match, "未能从 build.py 解析出 ICON 定义，检查写法是否变更"
    parts = re.findall(r'"([^"]+)"', match.group(1))
    icon_path = _BUILD_PY.parent.joinpath(*parts)
    assert icon_path.is_file(), f"build.py 的 ICON 指向不存在的文件: {icon_path}"



