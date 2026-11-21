"""
One-off migration: removes duplicate games and adds the uq_games_identity unique index.

Background: before loads were idempotent, restarting the loader re-inserted games that
were already stored (about 500,000 rows in the February 2017 load). This script keeps the
first copy of every game (lowest id), deletes the rest, and then creates the unique index
so it cannot happen again.

Both steps run in one transaction: if creating the index fails, no rows are deleted.
Safe to run more than once.

Usage:  python -m db.deduplicate
"""
import logging
import time

from sqlalchemy import text

from db.database import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Must match the definition of uq_games_identity in db/models.py
IDENTITY = "white_player, black_player, date, utc_time, md5(moves)"

DELETE_DUPLICATES = f"""
    DELETE FROM games
    WHERE id IN (
        SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY {IDENTITY} ORDER BY id) AS copy_number
            FROM games
        ) numbered
        WHERE copy_number > 1
    )
"""

CREATE_UNIQUE_INDEX = f"""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_games_identity ON games ({IDENTITY})
"""


def deduplicate() -> None:
    start = time.time()
    with engine.begin() as conn:  # one transaction: commit on success, rollback on error
        before = conn.execute(text("SELECT COUNT(*) FROM games")).scalar()
        logging.info(f"Rows before: {before:,}")

        deleted = conn.execute(text(DELETE_DUPLICATES)).rowcount
        logging.info(f"Deleted {deleted:,} duplicate rows")

        conn.execute(text(CREATE_UNIQUE_INDEX))
        logging.info("Unique index uq_games_identity is in place")

        after = conn.execute(text("SELECT COUNT(*) FROM games")).scalar()
        logging.info(f"Rows after: {after:,}")

    # VACUUM cannot run inside a transaction; it marks the deleted rows' space as reusable
    # and refreshes the planner statistics. PARALLEL 0: parallel index vacuuming needs more
    # shared memory than Docker's default 64 MB /dev/shm allows.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("VACUUM (PARALLEL 0, ANALYZE) games"))

    logging.info(f"Done in {time.time() - start:.0f}s")


if __name__ == "__main__":
    deduplicate()
