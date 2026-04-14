"""Database engine and session management."""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from bot.database.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def init_db(database_url: str = "sqlite:///trading_bot.db") -> None:
    """Initialize the database engine and create all tables."""
    global _engine, _SessionFactory

    _engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )
    _SessionFactory = sessionmaker(bind=_engine)

    # Create all tables
    Base.metadata.create_all(_engine)
    logger.info("Database initialized at %s", database_url)


def get_session() -> Session:
    """Get a new database session."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionFactory()


def get_engine():
    """Get the database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
