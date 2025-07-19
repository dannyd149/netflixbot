FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by Playwright at runtime
RUN apt-get update && apt-get install -y \
    curl gnupg unzip wget fonts-liberation libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdbus-1-3 libgdk-pixbuf2.0-0 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 libxrandr2 \
    xdg-utils libu2f-udev libvulkan1 libxss1 libappindicator3-1 \
    libxshmfence1 lsb-release libgbm1 ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Skip playwright install --with-deps (we're doing it in the CMD)
RUN pip install playwright

# Startup script will install browser at runtime
CMD ["sh", "-c", "playwright install chromium && python netflix_code_bot.py"]
