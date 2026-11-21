# ============================================================
# Stage 1: Builder — install dependencies
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install all Python dependencies into a dedicated directory
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Runtime — lean final image
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Install only the runtime PostgreSQL client library
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy the entire project source code
COPY . .

# Expose the port that Uvicorn will listen on
EXPOSE 8000

# Default command: start the FastAPI server
# HOST 0.0.0.0 is required so Docker can forward traffic into the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
