FROM python:3.10

WORKDIR /app
COPY . .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install Playwright and its dependencies
RUN apt-get update && apt-get install -y libnss3 libatk-bridge2.0-0 libxss1 libgtk-3-0 libasound2
RUN playwright install --with-deps

CMD ["python", "netflix_code_bot.py"]
