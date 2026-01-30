import os
import time
import asyncio
import random
import yt_dlp
import shutil
import threading
from telethon import TelegramClient, events
from telethon.sessions import MemorySession
from fastapi import FastAPI

# ================= 1. API CREDENTIALS (RESTORED) =================
# အရင်က ပေးခဲ့တဲ့ Key တွေကို ဒီမှာ တိုက်ရိုက်ထည့်ထားပါတယ်
API_ID = 2693994
API_HASH = "b151256f2d7874a77cfa533d008d6d09"
BOT_TOKEN = "8364825649:AAGKifPlcXPYkcmVxE5neJ-9ogEj2JxGMdY"

# ================= 2. FASTAPI (HEALTH CHECK) =================
app = FastAPI()

@app.get("/")
@app.get("/health")
def health():
    return {"status": "alive", "message": "Bot is running!"}

def run_api():
    import uvicorn
    # Render က ပေးတဲ့ PORT (မရှိရင် 10000)
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# API ကို Thread တစ်ခုနဲ့ ခွဲ run မယ် (Bot ကို မနှောင့်ယှက်အောင်)
threading.Thread(target=run_api, daemon=True).start()

# ================= 3. CONFIG & DIRECTORIES =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

# Folder ရှင်းလင်းခြင်း
if os.path.exists(DOWNLOAD_DIR):
    shutil.rmtree(DOWNLOAD_DIR)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

GROUPS = {
    "GRAMMAR":  -1003590384770,
    "SIGHT":    -1003679375354,
    "MATHS":    -1003506257738,
    "PHONICS":  -1002767847761,
    "DEFAULT":  -1003672925665
}

KEYWORDS = {
    "MATHS": ["number","addition","subtraction","count","math"],
    "SIGHT": ["sight","sentence","practice","reading"],
    "PHONICS": ["phonics","sound","blend","vowel"],
    "GRAMMAR": ["grammar","noun","verb","tense","adjective"]
}

def classify(title, desc=""):
    t = (title + " " + desc).lower()
    score = {k: sum(w in t for w in v) for k, v in KEYWORDS.items()}
    best = max(score, key=score.get)
    return best if score[best] > 0 else "DEFAULT"

# ================= 4. TELETHON SETUP =================
client = TelegramClient(MemorySession(), API_ID, API_HASH)
queue = asyncio.Queue()

# 🔥 FIXED: Worker Ready Flag မလိုတော့ပါ
# Bot စတာနဲ့ Worker ကို Main Loop မှာပဲ တခါတည်း စမှာမို့ Double Start မဖြစ်တော့ပါ

# ================= 5. DOWNLOADER LOGIC =================
def download_video_sync(url, status_cb):
    uid = f"{int(time.time())}_{random.randint(1000,9999)}"
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
    meta = {}

    def hook(d):
        if d["status"] == "downloading":
            try:
                p = d.get('_percent_str', '0%')
                # Message တွေ အရမ်းများမသွားအောင် 10% ပြည့်တိုင်းမှ update မယ် (Optional)
                status_cb(f"⬇️ Downloading: {p}")
            except: pass
        elif d["status"] == "finished":
            status_cb("⚙️ Processing video...")

    ydl_opts = {
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "progress_hooks": [hook],
        # Dockerfile မှာ aria2c ပါမှ ဒါအလုပ်လုပ်မယ်
        "external_downloader": "aria2c",
        "external_downloader_args": ["-x","8","-s","8","-k","1M"],
        "nocheckcertificate": True,
    }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            meta["title"] = info.get("title", "Facebook Video")
            meta["desc"] = info.get("description", "")
            path = ydl.prepare_filename(info)
            
            if not path.endswith(".mp4"):
                pre, ext = os.path.splitext(path)
                if os.path.exists(pre + ".mp4"):
                    path = pre + ".mp4"
            
            return path, meta
    except Exception as e:
        print(f"DL Error: {e}")
        return None, None

async def worker():
    print("👷 Worker started and waiting for tasks...")
    loop = asyncio.get_event_loop()

    while True:
        # Queue ထဲက အလုပ်လာမယ့်အချိန်ကို စောင့်မယ်
        event, url, status_msg = await queue.get()
        path = None 

        def update_status(msg):
            asyncio.run_coroutine_threadsafe(
                status_msg.edit(text=msg), loop
            )

        try:
            update_status("⏳ Starting Download (Render Server)...")
            
            # Download ကို သီးသန့် Thread နဲ့ Run မယ် (Bot မလေးအောင်)
            path, meta = await loop.run_in_executor(
                None, download_video_sync, url, update_status
            )

            if not path or not os.path.exists(path):
                raise Exception("Download Failed! (Check logs)")

            # Classify & Upload
            category = classify(meta.get("title", ""), meta.get("desc", ""))
            target_chat = GROUPS.get(category, GROUPS["DEFAULT"])
            
            await status_msg.edit(f"📤 Uploading to **{category}**...")

            await client.send_file(
                target_chat,
                path,
                caption=f"**{meta.get('title','Video')}**\n\n📂 Category: #{category}",
                supports_streaming=True
            )
            
            await status_msg.edit(f"✅ **Done!** Sent to #{category}")

        except Exception as e:
            print(f"Worker Error: {e}")
            try: await status_msg.edit(f"❌ Error: {str(e)[:50]}")
            except: pass
        finally:
            if path and os.path.exists(path):
                os.remove(path)
            queue.task_done()

# ================= 6. EVENT HANDLER =================
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def message_handler(event):
    
    # Cookie File Update
    if event.file and event.file.name == "cookies.txt":
        await client.download_media(event.message, COOKIES_FILE)
        await event.reply("✅ **Cookies Updated Successfully!**")
        return

    text = event.text.strip()
    if not text.startswith(("http", "www")):
        return

    # User ကို တုံ့ပြန်
    status_msg = await event.reply("🔄 Added to queue...")
    
    # 🔥 FIXED: Worker ကို ဒီကနေ လှမ်းမခေါ်တော့ဘူး (Double Start မဖြစ်အောင်)
    # Queue ထဲကိုပဲ ထည့်လိုက်မယ်
    await queue.put((event, text, status_msg))

# ================= 7. MAIN EXECUTION =================
if __name__ == "__main__":
    print("🚀 Starting Bot on Render...")
    client.start(bot_token=BOT_TOKEN)
    
    # Worker ကို ဒီနေရာမှာ တစ်ခါတည်း စမယ် (Singleton Worker)
    loop = asyncio.get_event_loop()
    loop.create_task(worker())
    
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("Bot Stopped.")
