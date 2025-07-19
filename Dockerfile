FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN apt-get update && \
    apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements.txt
RUN playwright install && playwright install-deps

CMD ["python", "netflix_code_bot.py"]
