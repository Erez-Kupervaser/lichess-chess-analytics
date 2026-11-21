"""
One-off migration: brings the indexes of an existing `games` table in line with db/models.py.

- Drops ix_games_id          - duplicate of the primary key's own index (games_pkey).
- Drops ix_games_opening     - covered by the composite (opening, white_elo) index.
- Replaces ix_games_white_player / ix_games_black_player with indexes on lower(name),
  which the case-insensitive player-stats query can actually use.

New databases don't need this: setup_db.py creates the right indexes from the models.
Safe to run more than once.

Usage:  python -m db.cleanup_indexes
"""
import logging

from sqlalchemy import text

from db.database import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

STATEMENTS = [
    "DROP INDEX IF EXISTS ix_games_id",
    "DROP INDEX IF EXISTS ix_games_opening",
    "DROP INDEX IF EXISTS ix_games_white_player",
    "DROP INDEX IF EXISTS ix_games_black_player",
    "CREATE INDEX IF NOT EXISTS ix_games_white_player_lower ON games (lower(white_player))",
    "CREATE INDEX IF NOT EXISTS ix_games_black_player_lower ON games (lower(black_player))",
]


def cleanup_indexes() -> None:
    with engine.begin() as conn:  # one transaction: all changes apply, or none do
        for statement in STATEMENTS:
            logging.info(statement)
            conn.execute(text(statement))
        conn.execute(text("ANALYZE games"))  # statistics for the new expression indexes
    logging.info("Index cleanup complete")


if __name__ == "__main__":
    cleanup_indexes()
