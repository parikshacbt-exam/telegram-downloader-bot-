FROM python:3.12-slim

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    ffmpeg \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose health check port
EXPOSE 8080

# Command to run bot
CMD ["python", "main.py"]
