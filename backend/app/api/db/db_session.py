# backend/app/api/db/db_session.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from app.config.env import DATABASE_URL

# ------------------------------------------------------
# DATABASE ENGINE (POOLING + AUTO-RECONNECT)
# ------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,            # max connections
    max_overflow=20,         # extra if required
    pool_timeout=30,         # wait before giving up
    pool_recycle=1800,       # refresh stale connections
    echo=False,
    future=True
)

# Thread-safe session factory
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
        future=True
    )
)

# ------------------------------------------------------
# DEPENDENCY FOR FASTAPI
# ------------------------------------------------------
def get_db():
    """Yields a safe database session for each request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
