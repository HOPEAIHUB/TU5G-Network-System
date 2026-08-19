# Multi-stage build for optimal image size and security
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies for compiling any binary wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies into the user directory to easily transfer in multi-stage
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/tu5guser/.local/bin:${PATH}"

# Install curl for health check and general utility, and create a security-hardened non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home tu5guser

# Copy installed python dependencies from builder
COPY --from=builder --chown=tu5guser:tu5guser /root/.local /home/tu5guser/.local

# Copy application files (with correct ownership)
COPY --chown=tu5guser:tu5guser . .

# Switch to the non-root user
USER tu5guser

# Expose the port FastAPI will run on
EXPOSE 8000

# Container healthcheck to ensure service is actively running and responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
