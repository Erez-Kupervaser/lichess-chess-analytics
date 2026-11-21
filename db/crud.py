from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from db.models import Game
import logging


def insert_games_bulk(db: Session, games_data: list[dict]) -> int:
    """
    Inserts a batch of game dictionaries in a single multi-row INSERT statement.

    ON CONFLICT DO NOTHING makes the load idempotent: a game that is already stored
    (same identity, see the uq_games_identity index in db/models.py) is skipped instead
    of being inserted twice. This is what allows re-running the loader after a crash.

    Returns the number of rows actually inserted (duplicates are not counted).
    """
    if not games_data:
        return 0

    stmt = insert(Game).values(games_data).on_conflict_do_nothing()
    try:
        result = db.execute(stmt)
        db.commit()
        return result.rowcount
    except Exception:
        # Revert the whole batch, then let the caller decide what to do.
        # Re-raising matters: silently swallowing the error would drop a batch of games
        # while the loader keeps reporting them as loaded.
        db.rollback()
        logging.exception("Failed to bulk insert games")
        raise
