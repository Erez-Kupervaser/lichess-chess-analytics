from sqlalchemy import Column, Integer, Float, String, Date, Time, Index, func
from db.database import Base

class Game(Base):
    __tablename__ = "games"

    # Composite indexes: speeds up queries that filter by BOTH opening AND ELO at the same time.
    # e.g. "Find top rated players who played the Sicilian Defense"
    # Without this, PostgreSQL would scan all rows. With it — instant lookup.
    __table_args__ = (
        Index("ix_games_opening_white_elo", "opening", "white_elo"),
        Index("ix_games_opening_black_elo", "opening", "black_elo"),
    )

    # Primary key (unique ID for every game in our database)
    id = Column(Integer, primary_key=True, index=True)
    
    # We index the players and openings because people will likely search for them
    white_player = Column(String, index=True)
    black_player = Column(String, index=True)
    
    # ELO is Integer (not String!) so numeric comparisons and sorting work correctly.
    # nullable=True means unknown ratings ("?") are stored as NULL instead of 0.
    # index=True allows fast filtering like "find all games above 2000 ELO".
    white_elo = Column(Integer, index=True, nullable=True)
    black_elo = Column(Integer, index=True, nullable=True)
    
    result = Column(String)
    opening = Column(String, index=True)
    total_moves = Column(Integer)
    
    # New Advanced Analytics Columns
    date = Column(Date, index=True, nullable=True) # Indexed because we'll search by date ranges often
    utc_time = Column(Time, nullable=True)
    time_control = Column(String, nullable=True)
    event = Column(String, nullable=True)
    moves = Column(String, nullable=True)

    # --- Data Enrichment Columns (Stage 3) ---
    # The board position (FEN string) at the last move of the game.
    # Enables position-search: "has this exact position ever occurred?"
    final_fen = Column(String, nullable=True)

    # Average seconds spent per move, calculated from [%clk ...] PGN comments.
    # NULL when the game has no clock information (common in older datasets).
    white_avg_think_time = Column(Float, nullable=True)
    black_avg_think_time = Column(Float, nullable=True)


# Game identity: the same two players, starting at the same second, with the same moves.
# Players + start time alone is NOT enough: Lichess has pairs who started two different
# games within the same second (e.g. an aborted game and its rematch), so the move list is
# part of the key. md5(moves) keeps the index small - long move strings would exceed
# PostgreSQL's B-tree entry size limit.
# Being UNIQUE makes loading idempotent: the loader uses INSERT ... ON CONFLICT DO NOTHING,
# so re-running it over the same file skips games that are already stored.
Index(
    "uq_games_identity",
    Game.white_player,
    Game.black_player,
    Game.date,
    Game.utc_time,
    func.md5(Game.moves),
    unique=True,
)
