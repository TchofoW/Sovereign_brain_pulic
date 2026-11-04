# =====================================================================
# STAGE 1: Build dependency wheels cleanly
# =====================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to leverage Docker build caching optimizations
COPY requirements.txt .

# Compile wheels to a localized wheelhouse directory
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# =====================================================================
# STAGE 2: Construct minimal runtime footprint container
# =====================================================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime PostgreSQL client libraries (required by psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Pull compiled wheels from the builder stage
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install dependencies cleanly without downloading raw source code tools again
RUN pip install --no-cache /wheels/*

# Copy the actual application code source matrix
COPY . /app

# Expose default port 8080 to match Google Cloud Run's native specification
EXPOSE 8080

# Environment variables flags for optimized Python production behavior
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Start high-performance ASGI server layer 
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
# Start high-performance ASGI server layer 
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
