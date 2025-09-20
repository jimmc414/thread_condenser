from typing import Iterator

from app.db import SessionLocal


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
