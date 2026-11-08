import hashlib
import re
import sqlite3
from uuid import UUID

import pytest

from app.agent.errors import RuntimeFailure
from app.product import auth_store
from app.product.auth_store import AuthStore, SESSION_TTL_SECONDS


PASSWORD = "a good password 123"


def assert_failure(code, call):
    with pytest.raises(RuntimeFailure) as caught:
        call()
    assert caught.value.code == code
    return caught.value


def test_registration_login_and_session_survive_new_store(tmp_path):
    path = tmp_path / "private" / "accounts.sqlite3"
    store = AuthStore(path)
    assert not path.exists()
    user = store.register("Feather_1", PASSWORD)
    assert UUID(user["id"]).version == 4
    token, csrf = store.create_session(user["id"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert re.fullmatch(r"[0-9a-f]{64}", csrf)
    restored = AuthStore(path)
    assert restored.login("fEATHER_1", PASSWORD) == user
    assert restored.authenticate(token) == {"user": user, "csrf_token": csrf}
    with sqlite3.connect(path) as connection:
        salt, digest = connection.execute("SELECT password_salt,password_hash FROM users").fetchone()
        saved_hash, created, expires = connection.execute(
            "SELECT token_hash,created_at,expires_at FROM sessions"
        ).fetchone()
    assert isinstance(salt, bytes) and len(salt) == 32
    assert isinstance(digest, bytes) and len(digest) == 64
    assert saved_hash == hashlib.sha256(token.encode()).hexdigest()
    assert expires - created == SESSION_TTL_SECONDS
    payload = path.read_bytes()
    assert token.encode() not in payload
    assert PASSWORD.encode() not in payload


def test_case_insensitive_unique_and_distinct_salts(tmp_path):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    first = store.register("Feather", PASSWORD)
    second = store.register("Another", PASSWORD)
    assert first["id"] != second["id"]
    assert_failure("username_taken", lambda: store.register("FEATHER", PASSWORD))
    assert store.login("feather", PASSWORD) == first
    with sqlite3.connect(store.path) as connection:
        credentials = connection.execute("SELECT password_salt,password_hash FROM users").fetchall()
    assert credentials[0][0] != credentials[1][0]
    assert credentials[0][1] != credentials[1][1]


@pytest.mark.parametrize("username", [None, True, 123, "ab", "a" * 33, "用户名", "user name", "../user", " user", "user\n"])
def test_invalid_usernames_rejected_without_creating_database(tmp_path, username):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    assert_failure("invalid_username", lambda: store.register(username, PASSWORD))
    assert not store.path.exists()


@pytest.mark.parametrize("password", [None, True, 123, "short", "a" * 129, "a" * 9 + "\ud800"])
def test_invalid_passwords_rejected_without_creating_database(tmp_path, password):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    assert_failure("weak_password", lambda: store.register("Feather", password))
    assert not store.path.exists()


@pytest.mark.parametrize("username,password", [
    ("Feather", "wrong password"), ("Unknown", PASSWORD),
    (None, PASSWORD), ("Feather", None), ("Feather", "a" * 10000),
])
def test_login_refusals_all_hash_and_expose_only_generic_error(tmp_path, monkeypatch, username, password):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    store.register("Feather", PASSWORD)
    original = auth_store._derive
    calls = []

    def derive(value, salt):
        calls.append((value, salt))
        return original(value, salt)

    monkeypatch.setattr(auth_store, "_derive", derive)
    error = assert_failure("invalid_credentials", lambda: store.login(username, password))
    assert error.status_code == 401
    assert len(calls) == 1
    assert len(calls[0][0]) <= 128
    assert PASSWORD not in str(error)


def test_expired_session_is_refused_and_removed(tmp_path, monkeypatch):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    user = store.register("Feather", PASSWORD)
    monkeypatch.setattr(auth_store.time, "time", lambda: 1000.0)
    token, _ = store.create_session(user["id"])
    monkeypatch.setattr(auth_store.time, "time", lambda: 1000.0 + SESSION_TTL_SECONDS)
    assert_failure("authentication_required", lambda: store.authenticate(token))
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_logout_revokes_only_target_token_and_is_idempotent(tmp_path):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    user = store.register("Feather", PASSWORD)
    first, _ = store.create_session(user["id"])
    second, _ = store.create_session(user["id"])
    store.logout(first)
    store.logout(first)
    store.logout(None)
    assert_failure("authentication_required", lambda: store.authenticate(first))
    assert store.authenticate(second)["user"] == user
    for token in (None, "", "x" * 43, "../secret", "a" * 10000, True):
        assert_failure("authentication_required", lambda: store.authenticate(token))


def test_delete_user_cascades_sessions_and_does_not_affect_other_accounts(tmp_path):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    first = store.register("Feather", PASSWORD)
    second = store.register("Another", PASSWORD)
    first_token, _ = store.create_session(first["id"])
    second_token, _ = store.create_session(second["id"])
    store.delete_user(first["id"])
    store.delete_user(first["id"])
    assert_failure("authentication_required", lambda: store.authenticate(first_token))
    assert_failure("authentication_required", lambda: store.create_session(first["id"]))
    assert_failure("invalid_credentials", lambda: store.login("Feather", PASSWORD))
    assert store.authenticate(second_token)["user"] == second
    assert store.login("Another", PASSWORD) == second


def test_storage_failure_is_safe_and_unknown_database_not_modified(tmp_path):
    path = tmp_path / "accounts.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('keep')")
    store = AuthStore(path)
    assert_failure("account_storage_error", lambda: store.register("Feather", PASSWORD))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == "keep"
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchone()


def test_transaction_rolls_back_when_interrupted(tmp_path):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    user = store.register("Feather", PASSWORD)
    with pytest.raises(RuntimeError):
        with store._connection() as connection:
            connection.execute("DELETE FROM users WHERE id=?", (user["id"],))
            raise RuntimeError("interrupted")
    assert store.login("Feather", PASSWORD) == user
