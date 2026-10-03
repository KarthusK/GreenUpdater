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
