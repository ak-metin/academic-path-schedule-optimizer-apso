"""
SQLAlchemy 2.0 Veritabanı Motoru (Engine) ve Oturum (Session) Yönetimi.
PostgreSQL 16 (veya yerel testlerde SQLite) ile tam uyumlu bağlantı katmanı sağlar.
"""

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Tüm SQLAlchemy ORM modellerinin türediği temel sınıf (Single Source of Truth)."""
    pass


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# SQLite kullanıldığında yabancı anahtar (ForeignKey) bütünlük kontrolünü aktif et
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI endpoint'leri için bağımlılık enjeksiyonu (Dependency Injection) oturumu."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
