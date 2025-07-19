# Use official Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl unzip gnupg build-essential libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 libxss1 libasound2 libxtst6 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxrandr2 libgbm1 libxinerama1 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 && \
    apt-get clean

# Install pip packages
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN pip install playwright && playwright install --with-deps

# Copy app code
COPY . .

# Run the bot
CMD ["python", "netflix_code_bot.py"]
