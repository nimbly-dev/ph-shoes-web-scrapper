FROM python:3.9-slim

WORKDIR /app

# Install minimal system dependencies plus those needed for Chromium
RUN apt-get update && apt-get install -y \
    build-essential \
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

# Install Playwright browsers
RUN playwright install

# Set the environment variable to persist browser installation
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers
# Install Playwright browsers
RUN playwright install

# Copy your app code
COPY . .

# Default port Render uses (set via ENV variable)
ENV PORT=10000

# Start FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
