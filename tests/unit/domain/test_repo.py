"""domain.repo 单测：三种克隆形式与常见变体都要能识别成 owner/repo。"""
from __future__ import annotations

import pytest

from greenupdater.domain import parse_repo_ref


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # HTTPS
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("http://github.com/owner/repo.git", ("owner", "repo")),
        # SSH
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("ssh://git@github.com/owner/repo.git", ("owner", "repo")),
        # GitHub CLI
        ("gh repo clone owner/repo", ("owner", "repo")),
        ("gh clone owner/repo", ("owner", "repo")),
        # 裸形式与变体
        ("owner/repo", ("owner", "repo")),
        ("github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
        ("  owner/repo  ", ("owner", "repo")),
        # 含 . - _ 的仓库名（GitHub 允许的字符集）
        ("owner/re-po_1.x", ("owner", "re-po_1.x")),
        ("https://github.com/my-org/my_repo.py.git", ("my-org", "my_repo.py")),
    ],
)
def test_parse_repo_ref_ok(text, expected):
    assert parse_repo_ref(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "justoneword",
        "gh repo clone",
        "https://github.com/owner",  # 只有一段
        "gh repo clone owner/repo -- --depth 1",  # 带额外参数，保守拒绝
    ],
)
def test_parse_repo_ref_rejects(text):
    assert parse_repo_ref(text) is None


def test_parse_repo_ref_roundtrip():
    """解析结果拼回 owner/repo 后必须能再次解析（编辑态回填依赖这点）。"""
    for text in ("git@github.com:owner/repo.git", "https://github.com/a/b.git"):
        owner, repo = parse_repo_ref(text)
        assert parse_repo_ref(f"{owner}/{repo}") == (owner, repo)
