"""Shared SQLAlchemy metadata for versioned database migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for persistence models introduced in later milestones."""
