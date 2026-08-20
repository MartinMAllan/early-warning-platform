import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Defaults to a local SQLite file so the schema is runnable and testable
# without a live Postgres instance. Point DATABASE_URL at Postgres in
# deployment (e.g. postgresql+psycopg2://user:pass@host/dbname) - the models
# in models.py use only dialect-portable SQLAlchemy types, so no code change
# is needed to switch.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./early_warning.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
