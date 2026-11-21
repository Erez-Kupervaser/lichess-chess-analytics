from pydantic import BaseModel
import datetime
from typing import Optional, List

class GameBase(BaseModel):
    """
    This is the base schema that defines what data fields are expected for a standard game piece of data.
    """
    white_player: str
    black_player: str
    # Optional[int] = None means it can be an integer or None (for unknown ratings)
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    result: str
    opening: str
    total_moves: int
    
    date: Optional[datetime.date] = None
    utc_time: Optional[datetime.time] = None
    time_control: Optional[str] = None
    event: Optional[str] = None

    final_fen: Optional[str] = None
    white_avg_think_time: Optional[float] = None
    black_avg_think_time: Optional[float] = None

class GameResponse(GameBase):
    """
    This schema extends GameBase and adds the 'id' field, because when we return a game
    FROM the database to the user, we also attach its ID.
    """
    id: int

    class Config:
        # Important! This tells Pydantic to read data even if it's an SQLAlchemy ORM model and not a regular dictionary.
        from_attributes = True

class PlayerStatsResponse(BaseModel):
    player_name: str
    total_games_played: int
    wins: int
    losses: int
    draws: int
    win_rate_vs_higher_elo: float
    win_rate_vs_lower_elo: float

class OpeningStatsResponse(BaseModel):
    opening: str
    played_count: int

class OpeningsEloBracket(BaseModel):
    bracket_name: str
    total_games: int
    white_win_rate: float
    black_win_rate: float
    draw_rate: float

class OpeningsEloPerformanceResponse(BaseModel):
    opening_name: str
    brackets: List[OpeningsEloBracket]

class NextMoveRecommendation(BaseModel):
    move: str
    played_count: int
    white_win_rate: float
    black_win_rate: float
    
class NextMoveResponse(BaseModel):
    current_sequence: str
    recommendations: List[NextMoveRecommendation]

class UpsetResponse(BaseModel):
    """
    Represents a game where the lower-rated player defeated a significantly
    higher-rated opponent. The 'elo_diff' field shows the rating gap.
    """
    id: int
    white_player: str
    black_player: str
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    result: str
    opening: str
    elo_diff: int  # Absolute ELO gap between the two players

    class Config:
        from_attributes = True

class TopPlayerByOpening(BaseModel):
    """
    Represents a player who has played a specific opening,
    ranked by their peak ELO recorded in those games.
    """
    player_name: str
    peak_elo: int        # Highest ELO this player had while playing this opening
    games_played: int    # How many times they played this opening

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Stage 3 Enrichment Schemas
# ---------------------------------------------------------------------------

class PositionSearchResult(BaseModel):
    """
    Returned when searching for games that reached a specific FEN position.
    Gives enough context to identify the game without returning the full move list.
    """
    id: int
    white_player: str
    black_player: str
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    result: str
    opening: str
    total_moves: int
    final_fen: Optional[str] = None

    class Config:
        from_attributes = True


class OpeningEloBracketStats(BaseModel):
    """
    Win/draw/loss rates for a specific opening within one ELO bracket,
    e.g. '1200-1499' or '1800-2099'.
    """
    bracket: str           # e.g. "1500-1799"
    total_games: int
    white_win_pct: float
    black_win_pct: float
    draw_pct: float


class OpeningEloPerformanceResponse(BaseModel):
    """Aggregated win-rate breakdown for an opening across all ELO brackets."""
    opening: str
    brackets: List[OpeningEloBracketStats]


class TimeVsSkillResult(BaseModel):
    """
    Correlation row: for games in a given ELO bracket, what is the
    average thinking time per move for White and Black?
    """
    elo_bracket: str
    sample_size: int
    white_avg_think_time: Optional[float] = None
    black_avg_think_time: Optional[float] = None
