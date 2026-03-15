"""SQLAlchemy session and engine configuration."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "database.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False  # Set to True for SQL query logging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_session():
    """Dependency for FastAPI/Flask to get database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Initialize database - create all tables."""
    # Import all models to ensure they're registered with Base
    from database import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
