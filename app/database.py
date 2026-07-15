"""Relay — Database setup. Uses Flask-SQLAlchemy."""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def normalize_database_url(database_url: str | None) -> str | None:
    """Select Psycopg 3 for provider-issued PostgreSQL connection strings."""
    if database_url and database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def init_db(app):
    """Bind the database; schema changes are handled only by versioned migrations."""
    db.init_app(app)
