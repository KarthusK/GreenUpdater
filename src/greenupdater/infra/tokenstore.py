"""TokenStore：GitHub Token 的 keyring 封装（对应 docs/design/02-modules.md §4.2）。

Token 只存系统凭据库，绝不落 SQLite / 导出 JSON。后端不可用时降级为匿名（返回 None）。
可注入 backend 便于测试，避免触碰真实系统凭据库。
"""
from __future__ import annotations

import keyring
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as FailKeyring


class KeyringUnavailableError(RuntimeError):
    """当前系统无可用凭据库后端。"""


class TokenStore:
    SERVICE = "GreenUpdater"
    KEY = "github_token"

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend = backend

    def _backend_or_default(self) -> KeyringBackend:
        return self._backend if self._backend is not None else keyring.get_keyring()

    def is_available(self) -> bool:
        """是否存在可用的凭据库后端（非 fail Keyring）。"""
        try:
            return not isinstance(self._backend_or_default(), FailKeyring)
        except Exception:  # noqa: BLE001 - 任何异常都视为不可用
            return False

    def get(self) -> str | None:
        """取 Token；不可用或未设置返回 None（匿名访问）。"""
        try:
            return self._backend_or_default().get_password(self.SERVICE, self.KEY)
        except Exception:  # noqa: BLE001
            return None

    def set(self, token: str) -> None:
        """写入 Token；后端不可用抛 KeyringUnavailableError（UI 据此提示）。"""
        try:
            self._backend_or_default().set_password(self.SERVICE, self.KEY, token)
        except Exception as exc:  # noqa: BLE001
            raise KeyringUnavailableError(str(exc)) from exc

    def clear(self) -> None:
        """删除 Token；不存在或不可用时静默。"""
        try:
            self._backend_or_default().delete_password(self.SERVICE, self.KEY)
        except Exception:  # noqa: BLE001
            pass
