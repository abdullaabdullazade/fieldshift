import hashlib
import hmac
import os
import secrets
import time

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import ROOT, connect, row

_SECRET_FILE = ROOT / "data" / ".jwt_secret"


def _secret() -> str:
    env = os.environ.get("FIELDSHIFT_JWT_SECRET")
    if env:
        return env
    if not _SECRET_FILE.exists():
        _SECRET_FILE.write_text(secrets.token_urlsafe(48))
        _SECRET_FILE.chmod(0o600)
    return _SECRET_FILE.read_text().strip()


SECRET = _secret()
TOKEN_TTL = 60 * 60 * 24 * 14


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(calc.hex(), dk)


def make_token(uid: int) -> str:
    return jwt.encode({"sub": str(uid), "exp": int(time.time()) + TOKEN_TTL}, SECRET, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def _load(creds: HTTPAuthorizationCredentials | None):
    if not creds:
        return None
    try:
        uid = int(jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    con = connect()
    try:
        return row(con, "SELECT id, email, phone, name, role, bio, whatsapp, telegram, show_phone, sms_alerts, "
                        "created_at FROM users WHERE id=?", uid)
    finally:
        con.close()


def _creds(creds, x_auth_token):
    # X-Auth-Token is used when the site sits behind HTTP basic auth, which owns the Authorization header
    if x_auth_token:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=x_auth_token)
    return creds if creds and creds.scheme.lower() == "bearer" else None


def optional_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                  x_auth_token: str | None = Header(default=None)):
    return _load(_creds(creds, x_auth_token))


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 x_auth_token: str | None = Header(default=None)):
    u = _load(_creds(creds, x_auth_token))
    if not u:
        raise HTTPException(401, "Please sign in")
    return u
