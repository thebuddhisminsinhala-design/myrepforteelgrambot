# Dockerfile for SnapDeploy - Telegram Bot
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies and fonts first
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-lklug-sinhala \
    fonts-noto-extra \
    fontconfig \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and dependencies
RUN playwright install --with-deps chromium
RUN playwright install-deps

# Create fonts directory
RUN mkdir -p /app/fonts

# Copy your bot code
COPY bot.py .

# Expose port for health check
EXPOSE 7860

# ✅ Health check for SnapDeploy (මේක add කරන්නම ඕනෙ!)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python bot.py" || exit 1

# Run the bot
CMD ["python", "bot.py"]
