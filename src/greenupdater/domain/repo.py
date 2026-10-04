"""仓库地址解析：把常见的 GitHub 仓库引用统一成 ``owner/repo``。

用户在「添加软件」里通常直接粘贴从 GitHub 复制的克隆地址，形式有三种：

- HTTPS：``https://github.com/owner/repo.git``
- SSH：``git@github.com:owner/repo.git``（含 ``ssh://git@github.com/owner/repo.git``）
- GitHub CLI：``gh repo clone owner/repo``

另外兼容裸 ``owner/repo``、``github.com/owner/repo``、结尾斜杠与 ``.git`` 后缀。
纯逻辑、不依赖 PySide6 与网络，便于单测。
"""
from __future__ import annotations

import re

# 锚定末尾两段：这样 "gh repo clone owner/repo" 里的子命令词（clone/repo）不会被误当作
# owner；若改成从左往右取第一段，就会解析出 "repo"/"clone" 这类错误结果。
_REPO_REF = re.compile(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")

# 形如 https://github.com/owner 的输入（缺仓库名）会匹配出 ("github.com", "owner")，
# 这是把主机名当成了 owner。用户可能只填了半个地址，宁可不识别也不要写错 owner。
_HOSTNAME_LIKE = re.compile(r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")


def parse_repo_ref(text: str) -> tuple[str, str] | None:
    """解析仓库引用为 ``(owner, repo)``；无法识别时返回 ``None``。

    只做形式识别，不校验域名——裸 ``owner/repo`` 本就没有域名信息。
    """
    if not text:
        return None
    match = _REPO_REF.search(text.strip())
    if match is None:
        return None
    owner, repo = match.group(1), match.group(2)
    if _HOSTNAME_LIKE.match(owner):
        return None
    return owner, repo
