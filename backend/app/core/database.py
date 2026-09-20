"""
Database configuration and utilities for Firelink.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Use SQLite for the MVP (container default; override for local dev via .env)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/firelink.db")

# Create engine with check_same_thread=False for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from ..models import Base
    Base.metadata.create_all(bind=engine)
