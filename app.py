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

# ================= 2. FASTAPI SERVER (For Render) =================
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

# Start FastAPI in a background thread
threading.Thread(target=run_api, daemon=True).start()

# ================= 3. CONFIG & DIRECTORIES =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

if os.path.exists(DOWNLOAD_DIR):
    shutil.rmtree(DOWNLOAD_DIR)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

GROUPS = {
    "GRAMMAR":  -1003590384770,
    "SIGHT":    -1003679375354,
    "MATHS":    -1003506257738,
    "SG_MATHS": -1003506257738,  # SG Maths လည်း ID အတူတူပဲထားထားသည်
    "PHONICS":  -1002767847761,
    "DEFAULT":  -1003672925665
}

# ================= 4. KEYWORDS & AI CLASSIFICATION =================
MATHS_KEYWORDS = ["addition", "subtraction", "multiplication", "division", "number", "numbers", "ordinal", "even", "odd", "count", "counting", "chapter", "exercise", "page", "pages", "graph", "graphs", "picture graph", "number to", "numbers to"]
SIGHT_KEYWORDS = ["sight", "sight word", "sight words", "sentences", "sentence practice", "who", "such", "long", "every"]
PHONICS_KEYWORDS = ["phonics", "blend", "blends", "sound", "sounds", "wr", "gl", "bl", "cl", "fl", "pl", "sl", "br", "cr", "dr", "fr", "gr", "tr"]
GRAMMAR_KEYWORDS = ["grammar", "preposition", "agreement", "subject", "verb", "noun", "pronoun", "adjective", "adverb", "tense"]
SG_MATHS_KEYWORDS = ["singapore maths", "singapore math", "1b", "ppc"]

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
    return re.sub(r'\s+', ' ', t).strip()

def classify_by_keywords(title, body=""):
    text = normalize_text_for_ai(str(title) + " " + str(body))
    scores = {"MATHS": 0, "SIGHT": 0, "PHONICS": 0, "GRAMMAR": 0, "SG_MATHS": 0}

    for kw in MATHS_KEYWORDS:
        if kw in text: scores["MATHS"] += 1
    for kw in SIGHT_KEYWORDS:
        if kw in text: scores["SIGHT"] += 1
    for kw in PHONICS_KEYWORDS:
        if len(kw) <= 2: 
             if re.search(rf'\b{kw}\b', text): scores["PHONICS"] += 1
        elif kw in text: scores["PHONICS"] += 1
    for kw in GRAMMAR_KEYWORDS:
        if kw in text: scores["GRAMMAR"] += 1
    for kw in SG_MATHS_KEYWORDS:
        if kw in text: scores["SG_MATHS"] += 1

    # Phonics က တခြား Maths တွေထက်များရင် Phonics ယူမယ်
    if scores["PHONICS"] > 0 and scores["PHONICS"] >= max([scores["MATHS"], scores["SG_MATHS"]]):
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

# ================= 5. STRICT CUSTOM TITLE LOGIC =================
def extract_custom_title(description, yt_title):
    source_text = ""
    # Description က ပထမဦးစားပေး
    if description and len(description.strip()) > 0:
        source_text = description
    elif yt_title and len(yt_title.strip()) > 0:
        source_text = yt_title
    
    if not source_text: return "Video Lesson"

    # ပထမဆုံး စာကြောင်းကိုပဲ ယူမည်
    first_line = source_text.strip().split('\n')[0]
    
    # URL များဖယ်ရှားမည်
    text_no_links = re.sub(r'http\S+', '', first_line)
    
    # သတ်မှတ်ထားသော သင်္ကေတများသာ ထားမည်
    clean_text = re.sub(r'[^\w\s\-\(\)\.\,_]', '', text_no_links)
    
    # နေရာလွတ်များ ရှင်းမည်
    final_title = re.sub(r'\s+', ' ', clean_text).strip()

    if not final_title: return "Video Lesson"
    return final_title[:100]

# ================= 6. THUMBNAIL GENERATOR =================
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

# ================= 7. DOWNLOADER LOGIC (YT-DLP) =================
client = TelegramClient(MemorySession(), API_ID, API_HASH)
queue = asyncio.Queue()

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
        "source_address": "0.0.0.0",  # IPv6 ကြောင့် Error မတက်စေရန် IPv4 ကိုသာ အတင်းသုံးခိုင်းခြင်း
        "sleep_requests": 2,          # Facebook က Block မလုပ်စေရန် Request တစ်ခုနှင့်တစ်ခုကြား ၂ စက္ကန့် နားခြင်း
        "retries": 5,
    }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            status_cb("🔍 Extracting Info...")
            info = ydl.extract_info(url, download=False)
            
            raw_desc = info.get("description", "")
            raw_title_yt = info.get("title", "")
            
            final_title = extract_custom_title(raw_desc, raw_title_yt)
            ai_category = classify_by_keywords(final_title, raw_desc)
            
            meta["title"] = final_title
            meta["desc"] = raw_desc
            meta["category"] = ai_category

            status_cb(f"⬇️ Downloading: {final_title[:30]}...")
            ydl.extract_info(url, download=True)

            video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.mp4"))
            if not video_candidates:
                video_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{uid}.*"))
            
            if video_candidates:
                downloaded_files["video"] = video_candidates[0]
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
            asyncio.run_coroutine_threadsafe(status_msg.edit(text=msg), loop)

        try:
            update_status("⏳ Starting Engine...")
            
            files, meta = await loop.run_in_executor(None, download_video_sync, url, update_status)

            if not files or not files["video"]:
                raise Exception("Download Failed!")

            category = predict_from_memory(meta["title"])
            if not category:
                category = meta.get("category")
            if not category:
                category = "DEFAULT"
            
            learn_category(meta["title"], category)
            target_chat = GROUPS.get(category, GROUPS["DEFAULT"])
            
            await status_msg.edit(f"📂 Category: **{category}**\n📤 Uploading to Group...")

            display_folder = "Singapore Maths 1B for PPC" if category == "SG_MATHS" else category
            caption_text = (
                f"🎬 **{meta.get('title')}**\n\n"
                f"📂 **Folder:** #{display_folder}\n"
                f"🔗 [Original Link]({url})"
            )

            msg = await client.send_file(
                target_chat,
                files["video"],
                thumb=files.get("thumb"),
                caption=caption_text,
                supports_streaming=True
            )
            
            clean_id = str(target_chat).replace("-100", "")
            post_link = f"https://t.me/c/{clean_id}/{msg.id}"
            
            # 🔥 Group အဟောင်း(category) ကိုပါ မှတ်သားပြီး ရွှေ့ပေးမည့် ခလုတ်များ
            buttons = [
                [Button.url("📂 View in Group", post_link)],
                [Button.inline("➡️ SG MATHS 1B", f"MOVE:SG_MATHS:{category}:{msg.id}")],
                [Button.inline("➡️ MATHS", f"MOVE:MATHS:{category}:{msg.id}"), Button.inline("➡️ PHONICS", f"MOVE:PHONICS:{category}:{msg.id}")],
                [Button.inline("➡️ GRAMMAR", f"MOVE:GRAMMAR:{category}:{msg.id}"), Button.inline("➡️ SIGHT", f"MOVE:SIGHT:{category}:{msg.id}")]
            ]
            
            await status_msg.edit(
                f"✅ **Done!** Uploaded to #{display_folder}\n📄 Title: `{meta.get('title')}`",
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

# ================= 8. TELEGRAM HANDLERS (TRUE MOVE LOGIC) =================
@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    if data.startswith("MOVE:"):
        parts = data.split(":")
        if len(parts) == 4:
            _, target_cat, old_cat, msg_id = parts
            msg_id = int(msg_id)
            
            await event.answer("🔄 Group အသစ်သို့ ပြောင်းရွှေ့နေပါသည်...", alert=False)
            
            # ခေါင်းစဉ် (Title) ကို လက်ရှိ Message ပေါ်မှ ပြန်ရှာခြင်း
            status_msg = await event.get_message()
            title_match = re.search(r'Title: `(.*?)`', status_msg.text)
            title = title_match.group(1) if title_match else "Video Lesson"
            
            # Memory သို့ သင်ယူမှတ်သားခြင်း
            learn_category(title, target_cat)
            
            old_chat = GROUPS.get(old_cat)
            new_chat = GROUPS.get(target_cat)
            display_folder = "Singapore Maths 1B for PPC" if target_cat == "SG_MATHS" else target_cat
            
            try:
                # Group အဟောင်းမှ Video အား ယူ၍ Group အသစ်သို့ ပို့ခြင်း
                old_msg = await client.get_messages(old_chat, ids=msg_id)
                if old_msg and old_msg.media:
                    new_caption = f"🎬 **{title}**\n\n📂 **Folder:** #{display_folder}"
                    new_msg = await client.send_file(new_chat, old_msg.media, caption=new_caption, supports_streaming=True)
                    
                    # Group အဟောင်းမှ မူလ Video အား ဖျက်ခြင်း (Admin ဖြစ်ရန်လိုသည်)
                    await client.delete_messages(old_chat, msg_id)
                    
                    # လင့်ခ်အသစ်ဖြင့် Button အသစ် ဖန်တီးခြင်း
                    clean_id = str(new_chat).replace("-100", "")
                    post_link = f"https://t.me/c/{clean_id}/{new_msg.id}"
                    buttons = [[Button.url(f"📂 View in {display_folder}", post_link)]]
                    
                    await event.edit(f"✅ **ပြောင်းရွှေ့ပြီးပါပြီ! (Learned)**\n📂 ရောက်ရှိသွားသော နေရာ: #{display_folder}\n📄 Title: `{title}`", buttons=buttons)
                else:
                    await event.answer("⚠️ Video ကို Group အဟောင်းထဲတွင် ရှာမတွေ့တော့ပါ။", alert=True)
            except Exception as e:
                await event.answer(f"❌ ပြောင်းရွှေ့ရာတွင် အမှားဖြစ်နေပါသည်: {str(e)}", alert=True)

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def message_handler(event):
    if event.file and event.file.name == "cookies.txt":
        await client.download_media(event.message, COOKIES_FILE)
        await event.reply("✅ **Cookies Updated!**")
        return

    text = event.text.strip()
    if not text.startswith(("http", "www")):
        return

    status_msg = await event.reply("🔍 Analying Link & Queuing...")
    await queue.put((event, text, status_msg))

# ================= 9. ASYNC RUNNER FIX =================
async def main():
    print("🚀 Bot Started (All Features Fixed & Integrated)...")
    await client.start(bot_token=BOT_TOKEN)
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        # Python 3.7+ တွင် Asyncio ပြဿနာမရှိစေရန် ဤနည်းဖြင့် Run ပါသည်
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by User")
