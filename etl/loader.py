import logging
from db.database import SessionLocal
from db.crud import insert_games_bulk
from etl.parser import yield_games

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def load_games_to_db(file_path: str, max_games: int = None, batch_size: int = 5000):
    """
    Reads games from the compressed PGN, groups them into batches, 
    and loads them into PostgreSQL efficiently.
    """
    # Open a "Session" - a working connection window to our database
    db = SessionLocal()
    
    batch: list[dict] = []
    total_inserted = 0
    
    try:
        # yield_games gives us one dictionary at a time lazily without exploding RAM
        for game_dict in yield_games(file_path, max_games=max_games):
            batch.append(game_dict)
            
            # When the batch reaches the desired size (e.g., 5000 games)
            # we do a single massive "INSERT" to the database
            if len(batch) >= batch_size:
                insert_games_bulk(db, batch)
                total_inserted += len(batch)
                logging.info(f"Loaded {total_inserted} games so far...")
                batch.clear() # Empty the batch to prepare for the next 5000
                
        # After the loop finishes, there might be a few games left in the batch (e.g. 3000 games left over)
        if batch:
            insert_games_bulk(db, batch)
            total_inserted += len(batch)
            logging.info(f"Loaded final remaining batch. Total games loaded: {total_inserted}")
            
    except Exception as e:
        logging.error(f"Error during data loading process: {e}")
    finally:
        # We MUST close the connection when we're completely done
        db.close()
        
if __name__ == "__main__":
    import os
    import sys
    
    # Allow passing a file path via command line argument: python -m etl.loader <path>
    if len(sys.argv) > 1:
        data_file = sys.argv[1]
    else:
        # Fallback to the default file we used for testing
        data_file = "../lichess_db_standard_rated_2013-01.pgn.zst"
        if not os.path.exists(data_file):
            data_file = "lichess_db_standard_rated_2013-01.pgn.zst"
        
    logging.info(f"Starting the Big Data ETL Engine on: {data_file}")
    
    # SCALE MODE: 
    # max_games=None means it will process the entire file (millions of games).
    # batch_size=10000 means it will bulk insert 10,000 rows at a time to PostgreSQL.
    load_games_to_db(data_file, max_games=None, batch_size=10000)
    logging.info("Big Data ETL process finished successfully!")
