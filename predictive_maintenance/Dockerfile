# PDM - Predictive Maintenance System
# Multi-stage Dockerfile for production deployment

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional production dependencies
RUN pip install --no-cache-dir \
    gunicorn \
    uvloop \
    httptools \
    psycopg2-binary \
    asyncpg \
    sqlalchemy[asyncio]

# =============================================================================
# Stage 2: Production
# =============================================================================
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd --create-home --shell /bin/bash pdm
USER pdm

# Copy application code
COPY --chown=pdm:pdm . /app/predictive_maintenance

# Set Python path
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default environment variables
ENV PDM_ENVIRONMENT=production
ENV PDM_API_HOST=0.0.0.0
ENV PDM_API_PORT=8000
ENV PDM_LOG_LEVEL=INFO
ENV PDM_LOG_FORMAT=json

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PDM_API_PORT}/health || exit 1

# Expose ports
EXPOSE 8000
EXPOSE 9090

# Default command - run API server
CMD ["uvicorn", "predictive_maintenance.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools"]

# =============================================================================
# Stage 3: Development
# =============================================================================
FROM production as development

USER root

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    black \
    flake8 \
    mypy \
    ipython

USER pdm

ENV PDM_ENVIRONMENT=development
ENV PDM_DEBUG=true
ENV PDM_API_RELOAD=true

# Development command with hot reload
CMD ["uvicorn", "predictive_maintenance.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload"]
