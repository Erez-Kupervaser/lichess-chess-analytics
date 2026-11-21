# Lichess Chess Analytics Platform

An end-to-end data engineering project that ingests raw game dumps from the
[Lichess open database](https://database.lichess.org/), stores them in PostgreSQL,
and exposes chess analytics through a REST API and an interactive dashboard.

~3 million rated games loaded from the February 2017 dump (1.8 GB zstd-compressed PGN).

## Architecture

```
 Lichess .pgn.zst dump
          │  streaming zstd decompression + python-chess parsing (constant memory)
          ▼
   ETL  (etl/parser.py, etl/loader.py)  ── bulk inserts, 10K rows per batch
          │
          ▼
   PostgreSQL  (db/)  ── indexed `games` table (SQLAlchemy ORM)
          │
     ┌────┴─────────────────┐
     ▼                      ▼
 FastAPI REST API      Streamlit + Plotly
 (main.py, api/)       dashboard (dashboard.py)
```

All services run with Docker Compose.

## Features

**ETL pipeline**
- Streams `.pgn.zst` files game by game, so memory stays flat regardless of file size.
- Enriches each game during ingestion: final board position (FEN) and average
  think time per move for each side, computed from `[%clk]` PGN clock comments.
- Bulk-loads into PostgreSQL in configurable batches.

**Database**
- Integer Elo columns, date/time, time control, opening, move list.
- Single-column indexes on players, Elo, opening and date, plus composite
  `(opening, elo)` indexes for opening-by-rating queries.

**REST API** (interactive docs at `/docs`)

| Endpoint | Description |
|---|---|
| `GET /games/` | Browse games with filters |
| `GET /games/stats/player/{player_name}` | Player statistics (wins/losses/draws, by color) |
| `GET /games/stats/top-openings` | Most frequently played openings |
| `GET /games/upsets` | Games where the lower-rated player won by a large Elo gap |
| `GET /games/opening-leaders/{opening_name}` | Top players in a given opening |
| `GET /games/search/position?fen=...` | Games that ended in an exact FEN position |
| `GET /games/openings/{opening_name}/performance-by-elo` | Opening results by Elo bracket |
| `GET /games/analytics/time-vs-skill` | Think time vs. player rating |
| `GET /openings/stats/{opening_name}/elo_performance` | Opening success rate by Elo bracket |
| `GET /openings/next_move?current_sequence=...` | Most popular and successful replies to a move sequence |

**Dashboard** – Streamlit + Plotly charts on top of the same database.

## Tech stack

Python 3.11 · PostgreSQL 16 · SQLAlchemy · FastAPI · python-chess · zstandard ·
pandas · Streamlit · Plotly · Docker Compose

## Running it

1. Download a monthly dump (e.g. `lichess_db_standard_rated_2017-02.pgn.zst`)
   from <https://database.lichess.org/> into the project folder.
2. Start the database, API and dashboard:
   ```bash
   docker compose up -d --build
   ```
3. Create the tables:
   ```bash
   docker compose exec api python -m db.setup_db
   ```
4. Load games:
   ```bash
   docker compose run --rm etl python -m etl.loader lichess_db_standard_rated_2017-02.pgn.zst
   ```
5. Open the API docs at <http://localhost:8000/docs> and the dashboard at
   <http://localhost:8501>.

> The credentials in `docker-compose.yml` are local development defaults only.

## Roadmap

- Full-text / pattern search over move lists (e.g. Elasticsearch)
- Scheduled ingestion of new monthly dumps (Airflow)
- Player network analysis (rivalries, shortest path between players)
