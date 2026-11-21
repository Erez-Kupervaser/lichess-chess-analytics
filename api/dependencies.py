from db.database import SessionLocal

def get_db():
    """
    This is a FastAPI dependency. For every API request that needs the database,
    it opens a session. As soon as the request is done, it properly closes the session,
    ensuring we don't have database connection leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
