# Python 3.9 Slim
FROM python:3.9-slim

# Aria2c ကို ဖြုတ်လိုက်ပါပြီ (Error တက်နေလို့ပါ)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py"]

