
import json
import os
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import SystemSetting

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://guidxus-main-production.up.railway.app").rstrip("/")

def _get_value(db: Session, key: str) -> Optional[str]:
    return db.execute(
        select(SystemSetting.value).where(SystemSetting.key == key)
    ).scalar_one_or_none()

def _get_row(db: Session, key: str) -> Optional[SystemSetting]:
    return db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    ).scalar_one_or_none()

def get_str(db: Session, key: str, default: str = "") -> str:
    v = _get_value(db, key)
    return v if v is not None else default

def get_bool(db: Session, key: str, default: bool = False) -> bool:
    v = _get_value(db, key)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

def get_json(db: Session, key: str, default: Any = None) -> Any:
    v = _get_value(db, key)
    if v is None:
        return [] if default is None else default
    try:
        return json.loads(v)
    except Exception:
        return [] if default is None else default

def set_str(db: Session, key: str, value: str) -> None:
    row = _get_row(db, key)
    if row is None:
        row = SystemSetting(key=key, value=str(value))
        db.add(row)
    else:
        row.value = str(value)
    db.commit()

def set_bool(db: Session, key: str, value: bool) -> None:
    set_str(db, key, "1" if value else "0")

def set_json(db: Session, key: str, value: Any) -> None:
    set_str(db, key, json.dumps(value, ensure_ascii=False))