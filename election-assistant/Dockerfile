# ─────────────────────────────────────────────
# Dockerfile — VoteSmart India (FastAPI edition)
# Optimised for Google Cloud Run
# ─────────────────────────────────────────────

# Use official slim Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Create a non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies first (leverages Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Start with uvicorn — FastAPI's native ASGI server
# 2 workers × 4 threads handles Cloud Run concurrency well
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--log-level", "info", "--proxy-headers", "--forwarded-allow-ips", "*"]