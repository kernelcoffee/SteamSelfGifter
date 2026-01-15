"""Base classes and mixins for database models."""

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all database models.

    This is the declarative base that all SQLAlchemy models inherit from.
    It provides the foundation for model metadata and table mapping.

    Usage:
        All database models should inherit from this class:

        >>> class MyModel(Base):
        ...     __tablename__ = "my_table"
        ...     id: Mapped[int] = mapped_column(Integer, primary_key=True)
    """

    pass


class TimestampMixin:
    """
    Mixin for automatic created_at and updated_at timestamps.

    This mixin adds two timestamp fields to any model that inherits it:
    - created_at: Set automatically when record is inserted
    - updated_at: Set automatically on insert and updates on every change

    Both timestamps use database-level defaults (func.now()) to ensure
    accuracy even when records are created/updated outside the application.

    Attributes:
        created_at: Timestamp when record was created (UTC)
        updated_at: Timestamp when record was last modified (UTC)

    Usage:
        >>> class MyModel(Base, TimestampMixin):
        ...     __tablename__ = "my_table"
        ...     id: Mapped[int] = mapped_column(Integer, primary_key=True)
        ...     # created_at and updated_at automatically added

    Design Notes:
        - Uses server_default for database-level timestamp generation
        - onupdate ensures updated_at changes on every modification
        - Timestamps are UTC (relies on database timezone settings)
        - Not all models use this mixin (e.g., ActivityLog doesn't need updated_at)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="When record was created (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When record was last updated (UTC)",
    )
