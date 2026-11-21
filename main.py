from fastapi import FastAPI
from api.routes import router as games_router
from api.openings import router as openings_router

# Initialize our clean, main FastAPI App
app = FastAPI(
    title="Lichess Big Data API",
    description="High-performance API for analyzing massive amounts of Lichess games.",
    version="1.0.0"
)

# Connect the "games" routes to the main app
app.include_router(games_router)
app.include_router(openings_router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Lichess Big Data API!",
        "hint": "Go to /docs to see the visual API documentation and test it out!"
    }

# (The old PGN-reading code has been fully moved over to etl/parser.py)
