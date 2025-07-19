# Use stable, compatible Python version
FROM python:3.11-slim

WORKDIR /app

# Install OS-level dependencies required by Playwright
RUN apt-get update && apt-get install -y \
    wget curl unzip gnupg \
    fonts-liberation libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 libnss3 libxcomposite1 \
    libxdamage1 libxrandr2 xdg-utils libu2f-udev libvulkan1 libxss1 \
    libappindicator3-1 libxshmfence1 lsb-release libgbm1 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install playwright

# Playwright browser install moved to CMD (runtime)
CMD ["sh", "-c", "playwright install chromium && python netflix_code_bot.py"]
