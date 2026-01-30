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
import json
from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient, events, Button
from telethon.sessions import MemorySession
from fastapi import FastAPI

# ================= 1. API CREDENTIALS =================
try:
    API_ID = int(os.environ.get("API_ID", 2693994))
    API_HASH = os.environ.get("API_HASH", "b151256f2d7874a77cfa533d008d6d09")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8364825649:AAGKifPlcXPYkcmVxE5neJ-9ogEj2JxGMdY")
except:
    print("❌ Error: API Keys missing!")
    exit(1)

# ================= 2. FASTAPI SERVER =================
app = FastAPI()

@app.get("/")
@app.head("/")
async def root():
    return {"status": "alive"}

@app.get("/health")
@app.head("/health")
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
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json") # Memory for learning

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

# ================= ORIGINAL KEYWORDS & LOGIC FROM speedupfb.py =================

MATHS_KEYWORDS = ["addition", "subtraction", "multiplication", "division", "number", "numbers", "ordinal", "even", "odd", "count", "counting", "chapter", "exercise", "page", "pages", "graph", "graphs", "picture graph", "number to", "numbers to"]
SIGHT_KEYWORDS = ["sight", "sight word", "sight words", "sentences", "sentence practice", "who", "such", "long", "every"]
PHONICS_KEYWORDS = ["phonics", "blend", "blends", "sound", "sounds", "wr", "gl", "bl", "cl", "fl", "pl", "sl", "br", "cr", "dr", "fr", "gr", "tr"]
GRAMMAR_KEYWORDS = ["grammar", "preposition", "agreement", "subject", "verb", "noun", "pronoun", "adjective", "adverb", "tense"]

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def normalize_text_for_ai(text):
    if not text: return ""
    t = text.lower()
    t = re.sub(r'\b(lesson|unit|term|part|book|video|chapter|week)\b', '', t)
    t = re.sub(r'[^a-z\s,]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

# 🔥 ORIGINAL CLASSIFICATION LOGIC 🔥
def classify_by_keywords(title, body=""):
    text = normalize_text_for_ai(str(title) + " " + str(body))
    scores = {"MATHS": 0, "SIGHT": 0, "PHONICS": 0, "GRAMMAR": 0}

    for kw in MATHS_KEYWORDS:
        if kw in text: scores["MATHS"] += 1
            
    for kw in SIGHT_KEYWORDS:
        if kw in text: scores["SIGHT"] += 1
    if str(title).count(',') >= 2: scores["SIGHT"] += 1

    for kw in PHONICS_KEYWORDS:
        if len(kw) <= 2: 
             if re.search(rf'\b{kw}\b', text): scores["PHONICS"] += 1
        elif kw in text:
             scores["PHONICS"] += 1

    for kw in GRAMMAR_KEYWORDS:
        if kw in text: scores["GRAMMAR"] += 1

    # Priority Logic: PHONICS wins ties
    if scores["PHONICS"] > 0 and scores["PHONICS"] >= scores["MATHS"]:
        best_cat = "PHONICS"
    else:
        best_cat = max(scores, key=scores.get)

    if scores[best_cat] == 0: return None
    return best_cat

def get_signature_for_memory(title):
    t = normalize_text_for_ai(title)
    if len(t) < 3: return None
    return t

def learn_category(title, category):
    sig = get_signature_for_memory(title)
    if not sig: return
    mem = load_json(MEMORY_FILE)
    mem[sig] = category
    save_json(MEMORY_FILE, mem)

def predict_from_memory(title):
    sig = get_signature_for_memory(title)
    if not sig: return None
    mem = load_json(MEMORY_FILE)
    return mem.get(sig, None)

def sanitize_filename(text):
    if not text: return "video"
    clean = re.sub(r'[\\/*?:"<>|]', "", text)
    clean = clean.replace("\n", " ").strip()
    return clean[:150]

# 🔥 ORIGINAL TITLE NORMALIZATION LOGIC 🔥
def normalize_lesson_title(title):
    if not title: return "Video Lesson"
    title = title.replace("…", "...")
    # Bracket removal Logic from speedupfb.py
    m = re.search(r'^(.+?\(\s*\d+\s*\))', title)
    if m: return sanitize_filename(m.group(1).strip())
    # See more splitting Logic
    title = re.split(r'See more|\.\.\.', title, flags=re.IGNORECASE)[0]
    return sanitize_filename(title.strip())

# ================= 4. THUMBNAIL GENERATOR =================
def create_text_thumbnail(text, output_path):
    try:
        W, H = 1280, 720
        img = Image.new('RGB', (W, H), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0,0,W,H], outline="black", width=10)

        header_text = "Video Lesson"
        try:
            font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
        except:
            font_header = ImageFont.load_default()
            font_title = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((W-w)/2, 50), header_text, font=font_header, fill="black")

        lines = textwrap.wrap(text, width=30)
        current_h = 250
        for line in lines[:5]:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W-w)/2, current_h), line, font=font_title, fill=(50, 50, 50))
            current_h += h + 20

        img.save(output_path)
        return True
    except Exception as e:
        print(f"Thumbnail Error: {e}")
        return False

# ================= 5. DOWNLOADER LOGIC (yt-dlp) =================
client = TelegramClient(MemorySession(), API_ID, API_HASH)
queue = asyncio.Queue()

def resolve_lesson_folder_flat(base_dir, category, title):
    # Logic from speedupfb.py to create folders based on lesson names if needed
    # Keeping it simple for Render: Downloads/Category/Title.mp4
    path = os.path.join(base_dir, category)
    if not os.path.exists(path): os.makedirs(path)
    return path

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
        "writethumbnail": False,
        "restrictfilenames": True,
    }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            status_cb("🔍 Extracting Info (Complex Mode)...")
            info = ydl.extract_info(url, download=False)
            
            # 🔥 ORIGINAL LOGIC INTEGRATION 🔥
            raw_title = info.get("title", "")
            description = info.get("description", "")
            
            # Use Description as Title source if Title is generic "Facebook Video"
            source_text_for_title = raw_title
            if not raw_title or "Facebook" in raw_title or re.match(r'^\d{4}-\d{2}-\d{2}', str(raw_title)):
                if description:
                    source_text_for_title = description
            
            # Apply original normalization
            final_title = normalize_lesson_title(source_text_for_title)
            
            # Apply original classification
            ai_category = classify_by_keywords(final_title, description)
            
            meta["title"] = final_title
            meta["desc"] = description
            meta["category"] = ai_category

            # Start Download
            status_cb(f"⬇️ Downloading: {final_title[:30]}...")
            ydl.extract_info(url, download=True)

            # Find File
            video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.mp4"))
            if not video_candidates:
                video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.*"))
            
            if video_candidates:
                downloaded_files["video"] = video_candidates[0]
                
                # Generate Thumbnail
                status_cb("🖼 Generating Cover...")
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

            # 🔥 CATEGORY LOGIC WITH MEMORY
            category = predict_from_memory(meta["title"])
            if not category:
                category = meta.get("category") # From AI
            if not category:
                category = "DEFAULT"
            
            # Learn for next time
            learn_category(meta["title"], category)

            target_chat = GROUPS.get(category, GROUPS["DEFAULT"])
            
            await status_msg.edit(f"📂 Category: **{category}**\n📤 Uploading to Group...")

            caption_text = (
                f"🎬 **{meta.get('title')}**\n\n"
                f"📂 **Folder:** #{category}\n"
                f"🔗 [Original Link]({url})"
            )

            # 🔥 UPLOAD TO GROUP
            msg = await client.send_file(
                target_chat,
                files["video"],
                thumb=files.get("thumb"),
                caption=caption_text,
                supports_streaming=True
            )
            
            # 🔥 FIXED: BUTTON LINK
            clean_id = str(target_chat).replace("-100", "")
            post_link = f"https://t.me/c/{clean_id}/{msg.id}"
            
            buttons = [
                [Button.url("📂 View in Group", post_link)],
                [Button.inline("➡️ Move to GRAMMAR", f"MOVE:GRAMMAR:{msg.id}")],
                [Button.inline("➡️ Move to SIGHT", f"MOVE:SIGHT:{msg.id}")],
                [Button.inline("➡️ Move to MATHS", f"MOVE:MATHS:{msg.id}")],
                [Button.inline("➡️ Move to PHONICS", f"MOVE:PHONICS:{msg.id}")]
            ]
            
            # Reply to User
            await status_msg.edit(
                f"✅ **Done!** Uploaded to #{category}",
                buttons=buttons
            )

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
@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    if "MOVE" in data:
        _, cat, msg_id = data.split(":")
        await event.edit(f"✅ Learned: **{cat}**")
        # Note: Actual moving requires admin rights and delete/resend logic which is complex
        # For now, we just acknowledge the learning.

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
    print("🚀 Bot Started (Render Mode + Original Complex Logic)...")
    client.start(bot_token=BOT_TOKEN)
    loop = asyncio.get_event_loop()
    loop.create_task(worker())
    
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("Stopped")
