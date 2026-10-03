"""theme.qss 模板与 colors.py 令牌的一致性测试（不创建 QApplication）。"""
from __future__ import annotations

import re
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

