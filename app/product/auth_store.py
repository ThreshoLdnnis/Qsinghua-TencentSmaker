"""SQLite accounts and expiring sessions; raw session tokens are never persisted."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.agent.errors import RuntimeFailure


SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
_USERNAME = re.compile(r"[A-Za-z0-9_-]{3,32}", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_SCRYPT_N = 32768
_SCRYPT_R = 8
_SCRYPT_P = 3


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
        p=_SCRYPT_P, dklen=64, maxmem=64 * 1024 * 1024,
    )


_DUMMY_SALT = b"lovestone-account-dummy-salt-v1"
_DUMMY_PASSWORD = "not-a-real-account-password"
_DUMMY_HASH = _derive(_DUMMY_PASSWORD, _DUMMY_SALT)


def _valid_username(value: object) -> bool:
    return isinstance(value, str) and _USERNAME.fullmatch(value) is not None


def _valid_password(value: object) -> bool:
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _authentication_required() -> RuntimeFailure:
    return RuntimeFailure("authentication_required", "登录状态已过期，请重新登录。", 401)


class AuthStore:
    """Constructor has no IO. Each operation uses its own committed transaction."""

    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    @contextmanager
    def _connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.path, timeout=3, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0 and not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
            ).fetchone():
                connection.execute("""CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at REAL NOT NULL
                )""")
                connection.execute("""CREATE TABLE sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )""")
                connection.execute("CREATE INDEX sessions_expiry ON sessions(expires_at)")
                connection.execute("CREATE INDEX sessions_user ON sessions(user_id)")
                connection.execute("PRAGMA user_version=1")
            elif version != 1:
                raise RuntimeFailure("account_storage_error", "账号数据版本暂不受支持。", 503)
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError):
            raise RuntimeFailure("account_storage_error", "暂时无法读取或保存账号，请稍后再试。", 503) from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def register(self, username: str, password: str) -> dict[str, str]:
        if not _valid_username(username):
            raise RuntimeFailure("invalid_username", "用户名需为 3–32 位字母、数字、下划线或连字符。", 400)
        if not _valid_password(password):
            raise RuntimeFailure("weak_password", "密码需为 10–128 个字符。", 400)
        salt = secrets.token_bytes(32)
        digest = _derive(password, salt)
        user = {"id": str(uuid4()), "username": username}
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO users(id,username,password_salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                    (user["id"], username, salt, digest, time.time()),
                )
            except sqlite3.IntegrityError:
                # UNIQUE is checked inside the write transaction, including concurrent registration.
                raise RuntimeFailure("username_taken", "这个用户名已被使用，请换一个。", 409) from None
        return user

    def login(self, username: str, password: str) -> dict[str, str]:
        valid_input = _valid_username(username) and _valid_password(password)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id,username,password_salt,password_hash FROM users WHERE username=? COLLATE NOCASE",
                (username if _valid_username(username) else "",),
            ).fetchone()
        valid_record = row is not None and isinstance(row["password_salt"], bytes) \
            and len(row["password_salt"]) == 32 and isinstance(row["password_hash"], bytes) \
            and len(row["password_hash"]) == 64
        salt = row["password_salt"] if valid_record else _DUMMY_SALT
        expected = row["password_hash"] if valid_record else _DUMMY_HASH
        actual = _derive(password if valid_input else _DUMMY_PASSWORD, salt)
        matches = hmac.compare_digest(actual, expected)
        if not valid_input or not valid_record or not matches:
            raise RuntimeFailure("invalid_credentials", "用户名或密码不正确。", 401)
        return {"id": row["id"], "username": row["username"]}

    def create_session(self, user_id: str) -> tuple[str, str]:
        if not isinstance(user_id, str):
            raise _authentication_required()
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        now = time.time()
        with self._connection() as connection:
            if not connection.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                raise _authentication_required()
            connection.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            connection.execute(
                "INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)",
                (token_hash, user_id, csrf_token, now, now + SESSION_TTL_SECONDS),
            )
        return raw_token, csrf_token

    def authenticate(self, raw_token: str) -> dict:
        if not isinstance(raw_token, str) or _TOKEN.fullmatch(raw_token) is None:
            raise _authentication_required()
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        now = time.time()
        with self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=? AND expires_at<=?", (token_hash, now))
            row = connection.execute("""SELECT u.id,u.username,s.csrf_token FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?""",
                (token_hash, now),
            ).fetchone()
        if row is None:
            raise _authentication_required()
        return {"user": {"id": row["id"], "username": row["username"]}, "csrf_token": row["csrf_token"]}

    def logout(self, raw_token: str) -> None:
        if not isinstance(raw_token, str) or _TOKEN.fullmatch(raw_token) is None:
            return
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        with self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def delete_user(self, user_id: str) -> None:
        if not isinstance(user_id, str):
            raise _authentication_required()
        with self._connection() as connection:
            connection.execute("DELETE FROM users WHERE id=?", (user_id,))
