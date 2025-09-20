from datetime import datetime, timedelta

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import settings

ALGO = "HS256"
AUD = "thread-condenser"


def make_jwt(subject: str, ttl_seconds: int = 900) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": subject,
        "aud": AUD,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, settings.APP_SECRET, algorithm=ALGO)


def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.APP_SECRET, algorithms=[ALGO], audience=AUD)
    except JWTError as exc:  # pragma: no cover - direct translation
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc
