from __future__ import annotations

from sqlalchemy import UUID as SA_UUID, Uuid as SA_Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_for_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_for_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "CHAR(32)"


@compiles(SA_UUID, "sqlite")
def _compile_uuid_for_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "CHAR(32)"


@compiles(SA_Uuid, "sqlite")
def _compile_emulated_uuid_for_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "CHAR(32)"


class Base(DeclarativeBase):
    pass
