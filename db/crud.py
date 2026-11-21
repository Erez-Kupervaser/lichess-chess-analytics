from sqlalchemy.orm import Session
from db.models import Game
import logging

def insert_games_bulk(db: Session, games_data: list[dict]):
    """
    Inserts a list of game dictionaries into the database super quickly.
    We use bulk_insert_mappings to avoid the overhead of creating individual ORM objects for millions of rows.
    """
    try:
        db.bulk_insert_mappings(Game, games_data)
        db.commit()
    except Exception as e:
        db.rollback() # If something fails, revert the changes so we don't get corrupted data
        logging.error(f"Failed to bulk insert games: {e}")
