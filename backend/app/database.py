import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


SCHEMA_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def database_schema(schema: str | None = None) -> str:
    schema = os.getenv("DB_SCHEMA", "") if schema is None else schema
    if schema and not SCHEMA_PATTERN.fullmatch(schema):
        raise RuntimeError("DB_SCHEMA must contain only lowercase letters, digits, and underscores")
    return schema


def make_engine(url: str | None = None, schema: str | None = None):
    url = url or get_settings().database_url
    # Render exposes a generic PostgreSQL URL. Select the psycopg 3 driver
    # explicitly because it is the PostgreSQL driver declared by the project.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        selected_schema = database_schema(schema)
        connect_args = {"options": f"-csearch_path={selected_schema},public"} if selected_schema else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database(bind=engine, schema: str | None = None):
    selected_schema = database_schema(schema)
    if bind.dialect.name == "postgresql" and selected_schema:
        with bind.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{selected_schema}"'))
    Base.metadata.create_all(bind=bind)


def get_db():
    with SessionLocal() as session:
        yield session
