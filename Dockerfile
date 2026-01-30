# Python 3.9 Slim ကို သုံးမယ်
FROM python:3.9-slim

# 1. Video Download အတွက် မရှိမဖြစ်လိုအပ်တဲ့ FFmpeg ကို Install လုပ်မယ်
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 2. Folder သတ်မှတ်မယ်
WORKDIR /app

# 3. ဖိုင်တွေ ကူးထည့်မယ်
COPY . /app

# 4. Library တွေ Install လုပ်မယ်
RUN pip install --no-cache-dir -r requirements.txt

# 5. Render က ပေးတဲ့ Port မှာ Run မယ်
CMD uvicorn app:app --host 0.0.0.0 --port $PORT