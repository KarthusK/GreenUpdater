"""infra.tokenstore 测试：用内存 backend，绝不触碰真实系统凭据库。"""
from __future__ import annotations

import pytest
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as FailKeyring

from greenupdater.infra import KeyringUnavailableError, TokenStore


class InMemoryBackend(KeyringBackend):
    """内存字典后端，priority>0 使其可被选用。"""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    @property
    def priority(self) -> int:  # type: ignore[override]
        return 1

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


def test_available_with_memory_backend():
    store = TokenStore(backend=InMemoryBackend())
    assert store.is_available() is True


def test_set_get_clear_roundtrip():
    store = TokenStore(backend=InMemoryBackend())
    assert store.get() is None
    store.set("ghp_secret")
    assert store.get() == "ghp_secret"
    store.clear()
    assert store.get() is None


def test_unavailable_backend_reports_false():
    store = TokenStore(backend=FailKeyring())
    assert store.is_available() is False


def test_set_raises_when_unavailable():
    store = TokenStore(backend=FailKeyring())
    with pytest.raises(KeyringUnavailableError):
        store.set("ghp_secret")


def test_get_returns_none_when_unavailable():
    store = TokenStore(backend=FailKeyring())
    assert store.get() is None
