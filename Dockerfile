FROM python:3.12-slim

# Install Chromium and ChromeDriver
RUN apt-get update && \
    apt-get install -y --no-install-recommends chromium chromium-driver && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV WEB_CONCURRENCY=1
ENV GUNICORN_CMD_ARGS="--timeout 3600 --graceful-timeout 3600"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000
CMD gunicorn app:app --bind 0.0.0.0:10000 --workers 1 --threads 4 --timeout 3600 --graceful-timeout 3600
