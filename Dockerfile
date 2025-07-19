# Use Python 3.11 instead of 3.13 to avoid greenlet/imghdr issues
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl gnupg unzip build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy app files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install Playwright and its browsers
RUN pip install playwright
RUN playwright install --with-deps

# Start the bot
CMD ["python", "netflix_code_bot.py"]
