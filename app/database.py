import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

if all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT]):
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
else:
    SQLALCHEMY_DATABASE_URL = "sqlite:///app.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_sqlite() -> bool:
    """التحقق من أن قاعدة البيانات هي SQLite"""
    return SQLALCHEMY_DATABASE_URL.startswith("sqlite")

def ilike_op(column: str) -> str:
    """إرجاع صيغة ILIKE أو LIKE حسب نوع قاعدة البيانات"""
    if is_sqlite():

        return f"UPPER({column}) LIKE UPPER(:q)"
    else:

        return f"{column} ILIKE :q"

import sys
sys.stdout.reconfigure(encoding='utf-8')
print("🔗 Using DB:", SQLALCHEMY_DATABASE_URL)