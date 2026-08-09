"""DeclarativeBase and the shared column mixins. Deliberately a leaf module.

Alembic autogenerate only sees tables attached to `Base.metadata`, and this file used to import
every model to guarantee that. It cannot: each model imports `Base` from here, so the models had
to be imported *after* `Base` was defined, and any module that reached `app.models` before
`app.db.base` hit a partially-initialized module and an ImportError. Whether the code worked
depended on which import an entrypoint happened to run first.

**Importing `app.models` is now what completes the metadata** — its `__init__` imports all three
model modules. Anything needing the full metadata (alembic, the test schema builder) imports
`app.models`, not just this module.
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


__all__ = ["Base", "TimestampMixin"]
