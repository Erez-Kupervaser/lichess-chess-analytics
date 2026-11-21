from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from db.models import Game
from api.schemas import OpeningsEloPerformanceResponse, OpeningsEloBracket, NextMoveResponse, NextMoveRecommendation
from api.dependencies import get_db

router = APIRouter(prefix="/openings", tags=["Openings Analytics"])

@router.get("/stats/{opening_name}/elo_performance", response_model=OpeningsEloPerformanceResponse)
def get_opening_elo_performance(opening_name: str, db: Session = Depends(get_db)):
    """
    Analyzes an opening's success rates across different ELO brackets.
    """
    games = db.query(Game).filter(Game.opening.ilike(f"%{opening_name}%")).all()
    
    if not games:
        raise HTTPException(status_code=404, detail="No games found for this opening.")
        
    brackets_data = {
        "Beginner (<1400)": {"games": 0, "white_wins": 0, "black_wins": 0, "draws": 0},
        "Intermediate (1400-2000)": {"games": 0, "white_wins": 0, "black_wins": 0, "draws": 0},
        "Advanced (2000+)": {"games": 0, "white_wins": 0, "black_wins": 0, "draws": 0}
    }
    
    for g in games:
    # 1. We will verify that the ELO exists before calculating (prevents TypeError crashes)
        if g.white_elo is None or g.black_elo is None:
            continue
        
        # 2. Calculating the average (the number is already an Integer thanks to SQLAlchemy, no need for int)
        avg_elo = (g.white_elo + g.black_elo) / 2
    
    # 3. Assigning to a group
        if avg_elo < 1400: 
            b = "Beginner (<1400)"
        elif avg_elo <= 2000: # It's better to use <= 2000 so we don't miss players with exactly 2000
            b = "Intermediate (1400-2000)"
        else: 
            b = "Advanced (2000+)"
        
    # 4. Counting games (before checking who won)
        brackets_data[b]["games"] += 1
    
    # 5. Precise checking of the results (without a general else)
        if g.result == "1-0": 
            brackets_data[b]["white_wins"] += 1
        elif g.result == "0-1": 
            brackets_data[b]["black_wins"] += 1
        elif g.result == "1/2-1/2": 
            brackets_data[b]["draws"] += 1
        # Games that were canceled ("*") are counted in games but will not receive a win or draw.
            
    result_brackets = []
    for b_name, b_stats in brackets_data.items():
        tg = b_stats["games"]
        result_brackets.append(OpeningsEloBracket(
            bracket_name=b_name,
            total_games=tg,
            white_win_rate=round((b_stats["white_wins"]/tg*100), 1) if tg else 0,
            black_win_rate=round((b_stats["black_wins"]/tg*100), 1) if tg else 0,
            draw_rate=round((b_stats["draws"]/tg*100), 1) if tg else 0,
        ))
        
    return OpeningsEloPerformanceResponse(
        opening_name=opening_name,
        brackets=result_brackets
    )

@router.get("/next_move", response_model=NextMoveResponse)
def get_next_move_recommendations(
    current_sequence: str = Query(..., description="Enter exact sequence spaces included, e.g., '1. e4 e5' or '1. d4'"),
    db: Session = Depends(get_db)):
    """
    Finds the most popular and successful responding moves to any given board state.
    """
    seq = current_sequence.strip()
    
    # Require trailing space to ensure we match sequence strictly
    games = db.query(Game).filter(Game.moves.like(f"{seq} %")).all()
    
    if not games:
        raise HTTPException(status_code=404, detail="No games found with this exact sequence.")
        
    next_moves_stats = {}
    
    for g in games:
        # String slice starting from the end of the user sequence
        remaining = g.moves[len(seq):].strip()
        tokens = remaining.split()
        
        if not tokens:
            continue
            
        next_move = tokens[0]
        # Ignore step numbers like '2.' or '15.'
        if next_move.endswith('.'):
            if len(tokens) > 1:
                next_move = tokens[1]
            else:
                continue
                
        if next_move not in next_moves_stats:
            next_moves_stats[next_move] = {"count": 0, "white_wins": 0, "black_wins": 0}
            
        next_moves_stats[next_move]["count"] += 1
        if g.result == "1-0": next_moves_stats[next_move]["white_wins"] += 1
        elif g.result == "0-1": next_moves_stats[next_move]["black_wins"] += 1
        
    recommendations = []
    for mv, stats in sorted(next_moves_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
        c = stats["count"]
        recommendations.append(NextMoveRecommendation(
            move=mv,
            played_count=c,
            white_win_rate=round(stats["white_wins"]/c*100, 1),
            black_win_rate=round(stats["black_wins"]/c*100, 1)
        ))
        
    return NextMoveResponse(
        current_sequence=seq,
        recommendations=recommendations
    )
