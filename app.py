import os
import asyncio
import httpx
from fastapi import FastAPI, Request, BackgroundTasks

# ================= CONFIG =================
# Render မှာ Environment Variable ထဲကနေ ယူသုံးမယ်
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()

# ================= TELEGRAM SENDER =================
async def safe_send_message(chat_id: int, text: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            await client.post(
                f"{TG_API}/sendMessage",
                json={"chat_id": chat_id, "text": text}
            )
        except Exception as e:
            print(f"Error sending message: {e}")

# ================= WEBHOOK =================
@app.post("/webhook")
async def telegram_webhook(req: Request, bg: BackgroundTasks):
    try:
        update = await req.json()
        if "message" in update and "text" in update["message"]:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")
            user_name = update["message"]["from"].get("first_name", "User")

            print(f"📩 Received: {text}")

            bg.add_task(
                safe_send_message,
                chat_id,
                f"✅ **Render is Working!**\n\nHello {user_name}!\nRender Server ကနေ စာပြန်တာပါ။"
            )
        return {"ok": True}
    except:
        return {"ok": False}

# ================= HEALTH CHECK =================
@app.get("/")
def health():
    return {"status": "Render Bot is Active"}