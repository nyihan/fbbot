# Python 3.9 Slim
FROM python:3.9-slim

# Install FFmpeg AND Aria2c (အရေးကြီးသည်)
RUN apt-get update && \
    apt-get install -y ffmpeg aria2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# Render Port Setup
CMD uvicorn app:app --host 0.0.0.0 --port $PORT

