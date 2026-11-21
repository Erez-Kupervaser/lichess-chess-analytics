import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# URL configuration for PostgreSQL
# When running inside Docker, DATABASE_URL is injected via docker-compose.yml.
# When running locally, it falls back to the default localhost connection string.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://demo:1234@localhost:5432/lichess_db"
)

# The engine is the core interface to the database
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# SessionLocal is the factory for creating new database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class for all our database models (ORM objects)
Base = declarative_base()
