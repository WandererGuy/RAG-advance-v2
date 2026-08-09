"""DeclarativeBase + model imports.

Alembic autogenerate only sees tables that are attached to Base.metadata, so every model
module must be imported here. Importing this module is what makes the metadata complete.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """created_at, defaulted by the database rather than by Python.

    server_default matters here: rows inserted by a migration or by psql get a timestamp too.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Imported for their side effect of registering tables on Base.metadata.
from app.models.chunk import Chunk  # noqa: E402,F401
from app.models.document import Document  # noqa: E402,F401
from app.models.query import Query  # noqa: E402,F401

__all__ = ["Base", "Chunk", "Document", "Query", "TimestampMixin"]
