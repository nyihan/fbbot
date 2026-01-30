import os
import time
import asyncio
import random
import glob
import shutil
import threading
import textwrap
import re
import yt_dlp
from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient, events
from telethon.sessions import MemorySession
from fastapi import FastAPI

# ================= 1. API CREDENTIALS =================
try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ Error: Render Environment Variables မှာ Key တွေ မဖြည့်ရသေးပါ!")
    exit(1)

# ================= 2. FASTAPI SERVER =================
app = FastAPI()

@app.get("/")
@app.get("/health")
def health():
    return {"status": "alive"}

def run_api():
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

threading.Thread(target=run_api, daemon=True).start()

# ================= 3. CONFIG & DIRECTORIES =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

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

# 🔥 ခင်ဗျားရဲ့ Mapped Keywords တွေကို အတိအကျ ပြန်သုံးထားပါတယ်
MATHS_KEYWORDS = [
    "addition", "subtraction", "multiplication", "division",
    "number", "numbers", "ordinal", "even", "odd",
    "count", "counting", "chapter", "exercise", "page", "pages",
    "graph", "graphs", "picture graph", "number to", "numbers to"
]

SIGHT_KEYWORDS = [
    "sight", "sight word", "sight words",
    "sentences", "sentence practice",
    "who", "such", "long", "every"
]

PHONICS_KEYWORDS = [
    "phonics", "blend", "blends", "sound", "sounds",
    "wr", "gl", "bl", "cl", "fl", "pl", "sl",
    "br", "cr", "dr", "fr", "gr", "tr"
]

GRAMMAR_KEYWORDS = [
    "grammar", "preposition", "agreement", "subject", "verb",
    "noun", "pronoun", "adjective", "adverb", "tense"
]

def normalize_text(text):
    if not text: return ""
    return str(text).lower()

def classify(title, desc=""):
    text = normalize_text(title + " " + desc)
    scores = {"MATHS": 0, "SIGHT": 0, "PHONICS": 0, "GRAMMAR": 0}

    for kw in MATHS_KEYWORDS:
        if kw in text: scores["MATHS"] += 1
            
    for kw in SIGHT_KEYWORDS:
        if kw in text: scores["SIGHT"] += 1

    for kw in PHONICS_KEYWORDS:
        # စာလုံးရေ ၂ လုံးဆိုရင် (eg. bl, cl) သေချာမှ စစ်မယ်
        if len(kw) <= 2: 
             if re.search(rf'\b{kw}\b', text): scores["PHONICS"] += 1
        elif kw in text:
             scores["PHONICS"] += 1

    for kw in GRAMMAR_KEYWORDS:
        if kw in text: scores["GRAMMAR"] += 1

    # Logic: Phonics က Maths နဲ့ တူနေရင် Phonics ကို ဦးစားပေးမယ်
    if scores["PHONICS"] > 0 and scores["PHONICS"] >= scores["MATHS"]:
        best_cat = "PHONICS"
    else:
        best_cat = max(scores, key=scores.get)

    # Score မရှိရင် Default
    return best_cat if scores[best_cat] > 0 else "DEFAULT"

# ================= 4. THUMBNAIL GENERATOR (BIG TEXT) =================
def create_text_thumbnail(text, output_path):
    try:
        # HD Size (1280x720) ကို သုံးမယ် (စာလုံး ပိုရှင်းအောင်)
        W, H = 1280, 720
        # နောက်ခံ အဖြူရောင်
        img = Image.new('RGB', (W, H), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # ဘောင်ခတ်မယ် (အမည်းရောင်)
        draw.rectangle([0,0,W,H], outline="black", width=10)

        # Header Text (Video Lesson)
        header_text = "Video Lesson"
        
        # Font ရွေးချယ်မှု (Render Linux အတွက်)
        try:
            # Linux မှာ အများအားဖြင့် ရှိတဲ့ Font
            font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
        except:
            # မရှိရင် Default ကို အကြီးချဲ့မယ်
            font_header = ImageFont.load_default()
            font_title = ImageFont.load_default()

        # Header ရေးမယ် (အပေါ်နားမှာ)
        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((W-w)/2, 50), header_text, font=font_header, fill="black")

        # Title ရေးမယ် (အလယ်မှာ) - စာလုံးအနက်
        # စာသားကို ဖြတ်မယ် (Wrap)
        lines = textwrap.wrap(text, width=30) # တကြောင်းမှာ စာလုံး ၃၀ ခန့်
        
        current_h = 250 # Header အောက်ကနေ စမယ်
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W-w)/2, current_h), line, font=font_title, fill=(50, 50, 50))
            current_h += h + 20 # တကြောင်းနဲ့ တကြောင်း ခွာမယ်

        img.save(output_path)
        return True
    except Exception as e:
        print(f"Thumbnail Error: {e}")
        return False

# ================= 5. DOWNLOADER LOGIC =================
client = TelegramClient(MemorySession(), API_ID, API_HASH)
queue = asyncio.Queue()

def sanitize_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "", text)[:100]

def download_video_sync(url, status_cb):
    timestamp = int(time.time())
    uid = f"{timestamp}_{random.randint(1000,9999)}"
    
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
    custom_thumb_path = os.path.join(DOWNLOAD_DIR, f"{uid}_custom.jpg")
    
    meta = {}
    downloaded_files = {"video": None, "thumb": None}

    def hook(d):
        if d["status"] == "downloading":
            try:
                p = d.get('_percent_str', '0%')
                status_cb(f"⬇️ Downloading: {p}")
            except: pass
        elif d["status"] == "finished":
            status_cb("⚙️ Processing Metadata...")

    ydl_opts = {
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "progress_hooks": [hook],
        "nocheckcertificate": True,
        "writethumbnail": False, # ကိုယ်တိုင်လုပ်မှာမို့ ပိတ်ထားမယ်
    }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ၁။ Metadata အရင်ဆွဲထုတ်မယ်
            status_cb("🔍 Extracting Info...")
            info = ydl.extract_info(url, download=False) # Download မလုပ်သေးဘူး
            
            # 🔥 TITLE LOGIC (ခင်ဗျားလိုချင်တဲ့ ပုံစံ)
            raw_title = info.get("title", "")
            description = info.get("description", "")
            
            # Facebook Title တွေက "Facebook Video" သို့မဟုတ် ရက်စွဲတွေ ဖြစ်နေရင် Description ကို ယူမယ်
            final_title = raw_title
            if not raw_title or raw_title == "Facebook Video" or re.match(r'^\d{4}-\d{2}-\d{2}', str(raw_title)):
                if description:
                    # Description ရှည်လွန်းရင် ပထမ စာလုံး ၂၀ လောက်ပဲ ယူမယ်
                    words = description.split()
                    final_title = " ".join(words[:20]) + "..." if len(words) > 20 else description
            
            meta["title"] = sanitize_filename(final_title)
            meta["desc"] = description

            # ၂။ အခုမှ တကယ် Download လုပ်မယ်
            status_cb(f"⬇️ Downloading: {final_title[:30]}...")
            ydl.extract_info(url, download=True)

            # File ရှာမယ်
            video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.mp4"))
            if not video_candidates:
                video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.*"))
            
            if video_candidates:
                downloaded_files["video"] = video_candidates[0]
                
                # 🔥 CUSTOM THUMBNAIL ဖန်တီးခြင်း
                status_cb("🖼 Generating Big Cover...")
                if create_text_thumbnail(meta["title"], custom_thumb_path):
                    downloaded_files["thumb"] = custom_thumb_path

            return downloaded_files, meta

    except Exception as e:
        print(f"DL Error: {e}")
        return None, None

async def worker():
    print("👷 Worker started...")
    loop = asyncio.get_event_loop()

    while True:
        event, url, status_msg = await queue.get()
        files = None

        def update_status(msg):
            asyncio.run_coroutine_threadsafe(
                status_msg.edit(text=msg), loop
            )

        try:
            update_status("⏳ Starting Engine...")
            
            files, meta = await loop.run_in_executor(
                None, download_video_sync, url, update_status
            )

            if not files or not files["video"]:
                raise Exception("Download Failed!")

            # Categorize
            category = classify(meta.get("title", ""), meta.get("desc", ""))
            target_chat = GROUPS.get(category, GROUPS["DEFAULT"])
            
            await status_msg.edit(f"📂 Category: **{category}**\n📤 Uploading...")

            caption_text = (
                f"🎬 **{meta.get('title')}**\n\n"
                f"📂 **Folder:** #{category}\n"
                f"🔗 [Original Link]({url})"
            )

            await client.send_file(
                target_chat,
                files["video"],
                thumb=files.get("thumb"),
                caption=caption_text,
                supports_streaming=True
            )
            
            await status_msg.edit(f"✅ **Done!** Saved to #{category}")

        except Exception as e:
            print(f"Worker Error: {e}")
            try: await status_msg.edit(f"❌ Error: {str(e)[:100]}")
            except: pass
        finally:
            if files:
                if files["video"] and os.path.exists(files["video"]):
                    os.remove(files["video"])
                if files["thumb"] and os.path.exists(files["thumb"]):
                    os.remove(files["thumb"])
            queue.task_done()

# ================= 6. MAIN =================
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def message_handler(event):
    if event.file and event.file.name == "cookies.txt":
        await client.download_media(event.message, COOKIES_FILE)
        await event.reply("✅ **Cookies Updated!**")
        return

    text = event.text.strip()
    if not text.startswith(("http", "www")):
        return

    status_msg = await event.reply("🔍 Analying Link...")
    await queue.put((event, text, status_msg))

if __name__ == "__main__":
    print("🚀 Bot Started (Render Optimized)...")
    client.start(bot_token=BOT_TOKEN)
    loop = asyncio.get_event_loop()
    loop.create_task(worker())
    
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("Stopped")

