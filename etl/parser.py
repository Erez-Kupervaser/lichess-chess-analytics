import re
import zstandard as zstd
import chess
import chess.pgn
import io
import logging
from datetime import datetime
from typing import Optional

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Pre-compiled regex for %clk comments — much faster than re.search() on every move.
# Matches patterns like: [%clk 0:05:23] or [%clk 1:23:45.6]
_CLK_PATTERN = re.compile(r'\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]')


def _clk_to_seconds(hours: str, minutes: str, seconds: str) -> float:
    """Converts clock string parts (h, m, s) to a total float of seconds."""
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _extract_enrichment(game: chess.pgn.Game) -> dict:
    """
    Walks through all the moves of a game to extract two advanced metrics:

    1. final_fen:
       We simulate the game move-by-move using a chess.Board object and capture
       the FEN string after the very last move is played. This gives us the exact
       board state at the end, enabling position-search queries later.

    2. white_avg_think_time / black_avg_think_time:
       Lichess embeds the remaining clock time in each move's comment, like:
           1. e4 { [%clk 0:05:00] } e5 { [%clk 0:04:58] }
       
       THE KEY IDEA: seconds_spent_on_move = clock_BEFORE_move - clock_AFTER_move
       
       We track the previous clock reading for White and Black separately.
       On each move, we subtract the current clock from the previous one to get
       "thinking time for that move", accumulate the total, and divide at the end.

       Edge cases handled:
       - No %clk at all → avg times returned as None
       - Only one move with a clock → not enough data for a delta, returns None
       - Negative delta (clock anomaly in data) → that move is skipped safely
    """
    board = chess.Board()
    final_fen = None

    # Separate tracking lists for each side
    white_think_times = []
    black_think_times = []

    # Previous clock values (in seconds). None until we see the first clock comment.
    prev_white_clk: Optional[float] = None
    prev_black_clk: Optional[float] = None

    try:
        node = game
        while node.variations:
            next_node = node.variations[0]
            move = next_node.move # The move leading to this node or None if this is the root node of the game.

            # Play the move on the board
            board.push(move)

            # --- FINAL FEN: capture after every move; the last assignment wins ---
            final_fen = board.fen()

            # --- CLOCK PARSING ---
            comment = next_node.comment or ""
            clk_match = _CLK_PATTERN.search(comment)

            if clk_match:
                current_clk = _clk_to_seconds(
                    clk_match.group(1),  # hours
                    clk_match.group(2),  # minutes
                    clk_match.group(3),  # seconds
                )

                # White plays on odd half-moves (ply), Black on even half-moves.
                # board.turn has already flipped AFTER push(), so we check the opposite.
                # If it's now Black's turn, the move just played was White's.
                if board.turn == chess.BLACK:  # White just moved
                    if prev_white_clk is not None:
                        delta = prev_white_clk - current_clk
                        if delta >= 0:  # Skip anomalies (clock resets from increment can be negative)
                            white_think_times.append(delta)
                    prev_white_clk = current_clk
                else:  # Black just moved
                    if prev_black_clk is not None:
                        delta = prev_black_clk - current_clk
                        if delta >= 0:
                            black_think_times.append(delta)
                    prev_black_clk = current_clk

            node = next_node

    except Exception as e:
        # Never crash the ETL pipeline over enrichment failures — just log and return partials
        logging.warning(f"Enrichment extraction failed mid-game: {e}. Returning partial data.")

    white_avg = round(sum(white_think_times) / len(white_think_times), 2) if white_think_times else None
    black_avg = round(sum(black_think_times) / len(black_think_times), 2) if black_think_times else None

    return {
        "final_fen": final_fen,
        "white_avg_think_time": white_avg,
        "black_avg_think_time": black_avg,
    }


def extract_game_data(game: chess.pgn.Game) -> dict:
    """
    Extracts all relevant data from a single chess.pgn.Game object and returns it as a dictionary.
    Includes base metadata AND enriched analytics (FEN, clock times).
    """
    def parse_elo(elo_str: str) -> Optional[int]:
        """
        Converts an ELO string to an integer, or returns None for unknown/invalid values.
        Lichess uses "?" when the rating is unknown — we store that as NULL in the DB.
        Storing NULL (not 0) is critical: 0 would corrupt averages and ELO comparisons.
        """
        if not elo_str or elo_str == "?":
            return None
        try:
            return int(elo_str)
        except ValueError:
            return None  # Handles any other non-numeric garbage

    try:
        # PGN standard dates are "YYYY.MM.DD", but sometimes they have placeholders like "????.??.??"
        utc_date_str = game.headers.get("UTCDate", "")
        utc_time_str = game.headers.get("UTCTime", "")

        parsed_date = None
        parsed_time = None

        # Safely parse date if it's not missing/unknown
        if utc_date_str and "?" not in utc_date_str:
            try:
                parsed_date = datetime.strptime(utc_date_str, "%Y.%m.%d").date()
            except ValueError:
                pass

        # Safely parse time if it's not missing/unknown
        if utc_time_str and "?" not in utc_time_str:
            try:
                parsed_time = datetime.strptime(utc_time_str, "%H:%M:%S").time()
            except ValueError:
                pass

        # --- BASE METADATA ---
        data = {
            "white_player": game.headers.get("White", "Unknown"),
            "black_player": game.headers.get("Black", "Unknown"),
            # parse_elo converts to int and returns None for unknown "?" ratings
            "white_elo": parse_elo(game.headers.get("WhiteElo")),
            "black_elo": parse_elo(game.headers.get("BlackElo")),
            "result": game.headers.get("Result", "*"),
            "opening": game.headers.get("Opening", "Unknown"),
            "total_moves": sum(1 for _ in game.mainline_moves()),
            "date": parsed_date,
            "utc_time": parsed_time,
            "time_control": game.headers.get("TimeControl", ""),
            "event": game.headers.get("Event", ""),
            "moves": str(game.mainline_moves()),
        }

        # --- DATA ENRICHMENT (Stage 3) ---
        # Walk the game tree once for both FEN and clock-time extraction.
        enrichment = _extract_enrichment(game)
        data.update(enrichment)

        return data

    except Exception as e:
        logging.error(f"Failed to extract data for a game: {e}")
        return None


def yield_games(file_path: str, max_games: int = None):
    """
    A generator that lazily reads a compressed PGN file and yields game data dictionaries one by one.
    Memory-efficient: decompresses and parses the stream without loading the entire file into RAM.
    """
    logging.info(f"Starting to yield games from: {file_path}")

    try:
        with open(file_path, 'rb') as compressed_file:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(compressed_file) as reader:
                text_stream = io.TextIOWrapper(reader, encoding='utf-8')

                games_yielded = 0
                while True:
                    # Stop if we reached the maximum requested games
                    if max_games is not None and games_yielded >= max_games:
                        logging.info(f"Reached the maximum requested limit of {max_games} games.")
                        break

                    try:
                        game = chess.pgn.read_game(text_stream)
                        # If game is None, we've hit the end of the file
                        if game is None:
                            logging.info("Reached the end of the PGN file.")
                            break

                        # Extract the data into a structured dictionary
                        game_data = extract_game_data(game)
                        if game_data:
                            yield game_data
                            games_yielded += 1

                    except ValueError as e:
                        # Handle specific parsing errors from python-chess (e.g. invalid syntax in PGN)
                        logging.warning(f"Corrupted game found, skipping. Error: {e}")
                        continue
                    except Exception as e:
                        logging.error(f"Unexpected error while reading a game, skipping: {e}")
                        continue

    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
    except Exception as e:
        logging.error(f"Failed to open or decompress file: {e}")


if __name__ == "__main__":
    import os

    test_file = "../lichess_db_standard_rated_2013-01.pgn.zst"
    if not os.path.exists(test_file):
        test_file = "lichess_db_standard_rated_2013-01.pgn.zst"

    print(f"Testing enriched parser on {test_file}...\n")
    for i, game_dict in enumerate(yield_games(test_file, max_games=5), 1):
        print(f"--- Game {i} ---")
        print(f"  Players:   {game_dict['white_player']} vs {game_dict['black_player']}")
        print(f"  Final FEN: {game_dict['final_fen']}")
        print(f"  White avg think: {game_dict['white_avg_think_time']}s")
        print(f"  Black avg think: {game_dict['black_avg_think_time']}s")
        print()