from db.database import engine, Base
# We must import models so that SQLAlchemy knows which tables to create
from db.models import Game
import logging

logging.basicConfig(level=logging.INFO)

def init_db():
    logging.info("Starting table creation in PostgreSQL...")
    try:
        # ⚠️  DEV ONLY: Drops all existing tables so we can recreate them with the
        # updated schema (Integer ELO columns + indexes). Remove drop_all() before
        # going to production, or after the schema is stable!
        logging.warning("Dropping all existing tables (dev mode)...")
        Base.metadata.drop_all(bind=engine)
        
        # Recreates all tables using the current models — now with Integer ELO + indexes.
        Base.metadata.create_all(bind=engine)
        logging.info("Database tables created successfully with the new schema!")
    except Exception as e:
        logging.error(f"Failed to create tables. Error: {e}")
        logging.error("Please verify that your username and password are correct in db/database.py,")
        logging.error("and that the database 'lichess_db' actually exists in PostgreSQL.")

if __name__ == "__main__":
    init_db()
