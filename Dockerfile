FROM python:3.9-slim

WORKDIR /app

# Install minimal system dependencies for Playwright (Chromium)
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libxshmfence1 \
    xvfb \
    libx11-xcb1 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for Playwright browsers BEFORE installing them.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# Explicitly install Chromium browsers with dependencies.
RUN playwright install chromium --with-deps

# Copy application code
COPY . .

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
