FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Environment variables for production
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV PORT=8080

# Health check (optional but recommended)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Cloud Run listens on 8080
CMD exec gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 1 \
    --threads 8 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    wsgi:app