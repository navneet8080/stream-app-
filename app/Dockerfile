FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/videos /app/secrets /app/config

# Expose dashboard port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["python", "-u", "entrypoint.py"]
