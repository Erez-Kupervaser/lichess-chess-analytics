from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date

from db.models import Game
from api.schemas import (
    GameResponse, PlayerStatsResponse, OpeningStatsResponse, UpsetResponse,
    TopPlayerByOpening, PositionSearchResult, OpeningEloBracketStats,
    OpeningEloPerformanceResponse, TimeVsSkillResult
)
from api.dependencies import get_db

# Create a router specifically for everything related to "/games"
router = APIRouter(prefix="/games", tags=["Games"])

@router.get("/", response_model=List[GameResponse])
def get_games(
    skip: int = 0, 
    limit: int = 50,
    player: Optional[str] = None,
    opening: Optional[str] = None,
    min_elo: Optional[int] = Query(None, description="Minimum ELO (at least one player must qualify)"),
    max_elo: Optional[int] = Query(None, description="Maximum ELO (at least one player must qualify)"),
    db: Session = Depends(get_db)
):

    print("=========================================")
    print(f"HELLO! Searching for min_elo: {min_elo}, opening: {opening}")
    print("=========================================")
    """
    Fetches games from the database.
    - **skip**: How many results to skip (for pagination)
    - **limit**: Maximum number of games to return
    - **player**: Filter by a specific player's name (whether they played black or white)
    - **opening**: Filter by chess opening names
    - **min_elo**: Return only games where at least one player has ELO >= min_elo
    - **max_elo**: Return only games where at least one player has ELO <= max_elo
    """
    query = db.query(Game)
    
    # If the user searched for a specific player: ILIKE ignores uppercase/lowercase
    if player:
        query = query.filter((Game.white_player.ilike(f"%{player}%")) | (Game.black_player.ilike(f"%{player}%")))
        
    # If the user searched for an opening:
    if opening:
        query = query.filter(Game.opening.ilike(f"%{opening}%"))

    # ELO filters — fast thanks to the Integer index on white_elo and black_elo!
    # We use IS NOT NULL to avoid including games with unknown ratings in the comparison.
    if min_elo is not None:
        query = query.filter(
            (Game.white_elo >= min_elo) | (Game.black_elo >= min_elo)
        )

    if max_elo is not None:
        query = query.filter(
            (Game.white_elo <= max_elo) | (Game.black_elo <= max_elo)
        )
        
    # Fetch the results from PostgreSQL
    games = query.offset(skip).limit(limit).all()
    return games

@router.get("/stats/player/{player_name}", response_model=PlayerStatsResponse)
def get_player_stats(
    player_name: str, 
    color: Optional[str] = None,
    time_control: Optional[str] = None,
    start_date: Optional[date] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[date] = Query(None, description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db)):
    """
    Calculate advanced statistics for a specific player, filtering by color, time control, or dates.
    Analyzes performance dynamically including success against higher rated vs lower rated players.
    """
    query = db.query(Game).filter(
        (Game.white_player.ilike(player_name)) | (Game.black_player.ilike(player_name))
    )
    
    # --- DYNAMIC FILTERS ---
    if color:
        if color.lower() == "white":
            query = query.filter(Game.white_player.ilike(player_name))
        elif color.lower() == "black":
            query = query.filter(Game.black_player.ilike(player_name))
            
    if time_control:
        query = query.filter(Game.time_control.ilike(f"%{time_control}%"))
        
    if start_date:
        query = query.filter(Game.date >= start_date)
        
    if end_date:
        query = query.filter(Game.date <= end_date)
        
    games = query.all()
    if not games:
        raise HTTPException(status_code=404, detail="No games found matching criteria")
        
    # --- DEEP ANALYTICS ---
    wins = 0
    losses = 0
    draws = 0
    
    higher_elo_games = 0
    higher_elo_wins = 0
    
    lower_elo_games = 0
    lower_elo_wins = 0
    
    for g in games:
        is_white = g.white_player.lower() == player_name.lower()
        
        # Outcome Tracking
        is_win = False
        if g.result == "1/2-1/2":
            draws += 1
        elif (is_white and g.result == "1-0") or (not is_white and g.result == "0-1"):
            wins += 1
            is_win = True
        else:
            losses += 1
            
        # ELO Difference Analysis — no int() cast needed, DB already returns integers (or None)
        try:
            p_elo = g.white_elo if is_white else g.black_elo
            o_elo = g.black_elo if is_white else g.white_elo
            
            # Skip if either player's rating is unknown (NULL)
            if p_elo is None or o_elo is None:
                continue
            
            # If opponent is rated at least 50 points higher
            if o_elo > p_elo + 50:
                higher_elo_games += 1
                if is_win: higher_elo_wins += 1
            # If opponent is rated at least 50 points lower
            elif o_elo < p_elo - 50:
                lower_elo_games += 1
                if is_win: lower_elo_wins += 1
        except (TypeError, ValueError):
            pass  # Safety net — should not happen with Integer columns
            
    success_higher = (higher_elo_wins / higher_elo_games * 100) if higher_elo_games else 0
    success_lower = (lower_elo_wins / lower_elo_games * 100) if lower_elo_games else 0
        
    return PlayerStatsResponse(
        player_name=player_name,
        total_games_played=len(games),
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate_vs_higher_elo=round(success_higher, 1),
        win_rate_vs_lower_elo=round(success_lower, 1)
    )

@router.get("/stats/top-openings", response_model=List[OpeningStatsResponse])
def get_top_openings(limit: int = 10, db: Session = Depends(get_db)):
    """
    Finds the most frequently played openings across all games in our database.
    """
    # SQL Equivalent: SELECT opening, COUNT(id) FROM games GROUP BY opening ORDER BY count DESC LIMIT 10
    results: List[OpeningStatsResponse] = (
        db.query(Game.opening, func.count(Game.id).label("played_count"))
        .group_by(Game.opening)
        .order_by(func.count(Game.id).desc())
        .limit(limit)
        .all()
    )
    
    return [OpeningStatsResponse(opening=row.opening, played_count=row.played_count) for row in results]


@router.get("/upsets", response_model=List[UpsetResponse])
def get_upsets(
    min_diff: int = Query(300, description="Minimum ELO gap between the two players"),
    limit: int = Query(20, description="Maximum number of upset games to return"),
    db: Session = Depends(get_db)
):
    """
    Returns games where the lower-rated player won against a significantly
    higher-rated opponent (the classic 'David vs Goliath' matches).
    - **min_diff**: Minimum ELO gap to qualify as an upset (default: 300)
    - **limit**: How many results to return
    """
    # Fetch only games where both players have known ELO ratings
    games = (
        db.query(Game)
        .filter(Game.white_elo.isnot(None))
        .filter(Game.black_elo.isnot(None))
        .filter(Game.result.in_(["1-0", "0-1"]))  # Only decisive games (no draws)
        .all()
    )

    upsets = []
    for g in games:
        diff = abs(g.white_elo - g.black_elo)
        if diff < min_diff:
            continue

        # White was the underdog and won
        white_is_underdog: bool = g.white_elo < g.black_elo and g.result == "1-0"
        # Black was the underdog and won
        black_is_underdog: bool = g.black_elo < g.white_elo and g.result == "0-1"

        if white_is_underdog or black_is_underdog:
            upsets.append(UpsetResponse(
                id=g.id,
                white_player=g.white_player,
                black_player=g.black_player,
                white_elo=g.white_elo,
                black_elo=g.black_elo,
                result=g.result,
                opening=g.opening,
                elo_diff=diff
            ))

    # Sort by the biggest ELO gap first (most impressive upsets at the top)
    upsets.sort(key=lambda x: x.elo_diff, reverse=True)
    return upsets[:limit]


@router.get("/opening-leaders/{opening_name}", response_model=List[TopPlayerByOpening])
def get_opening_leaders(
    opening_name: str,
    limit: int = Query(10, description="Number of top players to return"),
    db: Session = Depends(get_db)
):
    """
    Returns the highest-rated players who have played a specific opening,
    ranked by their peak ELO in those games.
    - **opening_name**: The opening to search for (partial match supported)
    - **limit**: How many top players to return
    """
    # SQL: For each player (white or black), find their max ELO and game count within this opening
    white_leaders = (
        db.query(
            Game.white_player.label("player_name"),
            func.max(Game.white_elo).label("peak_elo"),
            func.count(Game.id).label("games_played")
        )
        .filter(Game.opening.ilike(f"%{opening_name}%"))
        .filter(Game.white_elo.isnot(None))
        .group_by(Game.white_player)
        .all()
    )

    black_leaders = (
        db.query(
            Game.black_player.label("player_name"),
            func.max(Game.black_elo).label("peak_elo"),
            func.count(Game.id).label("games_played")
        )
        .filter(Game.opening.ilike(f"%{opening_name}%"))
        .filter(Game.black_elo.isnot(None))
        .group_by(Game.black_player)
        .all()
    )

    # Merge both sides: a player might have played the opening as both white AND black
    player_map: dict = {}
    for row in list(white_leaders) + list(black_leaders):
        name = row.player_name
        if name not in player_map:
            player_map[name] = {"peak_elo": row.peak_elo, "games_played": row.games_played}
        else:
            # Keep highest ELO and sum the game count
            player_map[name]["peak_elo"] = max(player_map[name]["peak_elo"], row.peak_elo)
            player_map[name]["games_played"] += row.games_played

    if not player_map:
        raise HTTPException(status_code=404, detail=f"No games found for opening: '{opening_name}'")

    # Build and sort result by peak ELO descending
    results = [
        TopPlayerByOpening(player_name=name, peak_elo=data["peak_elo"], games_played=data["games_played"])
        for name, data in player_map.items()
    ]
    results.sort(key=lambda x: x.peak_elo, reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Stage 3 Enrichment Endpoints
# ---------------------------------------------------------------------------

@router.get("/search/position", response_model=List[PositionSearchResult])
def search_by_position(
    fen: str = Query(..., description="The FEN string to look for (exact match on final board position)"),
    limit: int = Query(20, description="Maximum number of results"),
    db: Session = Depends(get_db)
):
    """
    Finds all games in our database that ended at a specific board position (FEN).
    This lets you ask: **"Has this exact position ever occurred in a real game?"**
    
    The `final_fen` column was populated during Stage 3 Data Enrichment.
    FEN comparison is exact — castling rights and en-passant state must match.
    """
    games = (
        db.query(Game)
        .filter(Game.final_fen == fen)
        .limit(limit)
        .all()
    )
    if not games:
        raise HTTPException(status_code=404, detail="No games found ending at that position.")
    return games


@router.get("/openings/{opening_name}/performance-by-elo", response_model=OpeningEloPerformanceResponse)
def opening_performance_by_elo(
    opening_name: str,
    db: Session = Depends(get_db)
):
    """
    Shows how win rates for a specific opening vary across ELO skill levels.
    
    Breaks results into ELO brackets (e.g. 1200-1499, 1500-1799 …) and reports
    the White win %, Black win %, and Draw % within each bracket.
    This answers: **"Does the Sicilian work better at 1200 or at 2000?"**
    """
    # ELO brackets: (label, min_elo, max_elo)
    brackets_def = [
        ("<1200",   0,    1199),
        ("1200-1499", 1200, 1499),
        ("1500-1799", 1500, 1799),
        ("1800-2099", 1800, 2099),
        ("2100+",   2100, 9999),
    ]

    # Pre-fetch only games matching this opening (partial match) with known ELOs
    games = (
        db.query(Game)
        .filter(Game.opening.ilike(f"%{opening_name}%"))
        .filter(Game.white_elo.isnot(None))
        .filter(Game.black_elo.isnot(None))
        .all()
    )

    if not games:
        raise HTTPException(status_code=404, detail=f"No rated games found for opening: '{opening_name}'")

    bracket_results: List[OpeningEloBracketStats] = []

    for label, lo, hi in brackets_def:
        # Use the AVERAGE of both players' ELO as the bracket key
        # (more representative than picking only one side)
        subset = [g for g in games if lo <= (g.white_elo + g.black_elo) // 2 <= hi]
        total = len(subset)
        if total == 0:
            continue

        white_wins = sum(1 for g in subset if g.result == "1-0")
        black_wins = sum(1 for g in subset if g.result == "0-1")
        draws      = sum(1 for g in subset if g.result == "1/2-1/2")

        bracket_results.append(OpeningEloBracketStats(
            bracket=label,
            total_games=total,
            white_win_pct=round(white_wins / total * 100, 1),
            black_win_pct=round(black_wins / total * 100, 1),
            draw_pct=round(draws / total * 100, 1),
        ))

    return OpeningEloPerformanceResponse(opening=opening_name, brackets=bracket_results)


@router.get("/analytics/time-vs-skill", response_model=List[TimeVsSkillResult])
def time_vs_skill(
    db: Session = Depends(get_db)
):
    """
    Analyzes how much time players spend per move across different ELO skill brackets.
    
    Uses the `white_avg_think_time` and `black_avg_think_time` columns populated
    during Stage 3 Data Enrichment from the [%clk ...] PGN annotations.
    
    Returns NULL for brackets where clock data is unavailable (e.g. old 2013 games
    predate Lichess's clock annotation feature).
    """
    brackets_def = [
        ("<1200",     0,    1199),
        ("1200-1499", 1200, 1499),
        ("1500-1799", 1500, 1799),
        ("1800-2099", 1800, 2099),
        ("2100+",    2100, 9999),
    ]

    # Only fetch games that have clock data AND known ELOs
    games = (
        db.query(Game)
        .filter(Game.white_avg_think_time.isnot(None))
        .filter(Game.white_elo.isnot(None))
        .filter(Game.black_elo.isnot(None))
        .all()
    )

    results: List[TimeVsSkillResult] = []

    for label, lo, hi in brackets_def:
        subset = [g for g in games if lo <= (g.white_elo + g.black_elo) // 2 <= hi]
        total = len(subset)
        if total == 0:
            continue

        avg_white = round(sum(g.white_avg_think_time for g in subset) / total, 2)
        avg_black = round(sum(g.black_avg_think_time for g in subset if g.black_avg_think_time) / total, 2)

        results.append(TimeVsSkillResult(
            elo_bracket=label,
            sample_size=total,
            white_avg_think_time=avg_white,
            black_avg_think_time=avg_black,
        ))

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No games with clock data found. Load a newer dataset (2014+) that includes [%clk] annotations."
        )

    return results
