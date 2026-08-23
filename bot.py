import re
import io
import os
import sys
import logging
import urllib.request
import unicodedata
import shutil
import subprocess
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler
)
from telegram.request import HTTPXRequest
import google.genai as genai

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = "gemini-3.5-flash-lite"

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY:
    logger.error("❌ Environment variables TELEGRAM_BOT_TOKEN or GOOGLE_API_KEY missing!")
    sys.exit(1)

BOT_USERNAME = "BioDiagrams_Bot"  
BOT_NAME = "Biovra AI 🧡⚡️"

MAIN_CHANNEL_LINK = "https://t.me/BiologyHubLK"
MAIN_CHANNEL_USERNAME = "@BiologyHubLK"
BACKUP_CHANNEL_LINK = "https://t.me/BiologyHubLKBackup"
BACKUP_CHANNEL_USERNAME = "@BiologyHubLKBackup"
GROUP_LINK = "https://t.me/BiologyHUbLK_Chat"
STICKER_FILE_ID = "CAACAgIAAxkBAAERojJqa38J94V3D0krLrqkGC4_fubIBAACnA0AAmVJ2Eh6rZ_M40MN6j0E"
EXEMPT_USER_IDS = [8175452079]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

SINHALA_FONT_PATH = os.path.join(FONTS_DIR, "NotoSansSinhala-Regular.ttf")
ENGLISH_FONT_PATH = os.path.join(FONTS_DIR, "NotoSans-Regular.ttf")
EMOJI_FONT_PATH = os.path.join(FONTS_DIR, "NotoColorEmoji.ttf")

SINHALA_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSansSinhala/NotoSansSinhala-Regular.ttf"
ENGLISH_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
EMOJI_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@main/fonts/NotoColorEmoji.ttf"

MESSAGES = {
    "private_chat_not_allowed": f"Hi! යාලූ...👋🏻☺️ මමයි {BOT_NAME}, මගෙත් එක්ක Chat කරන්න අපේ Group එකට join වෙන්න 🤗",
    "not_a_member": "AI පාවිච්චි කරන්න අපේ channel දෙකටම join වෙන්න 🤍🌿",
    "waiting": "පොඩ්ඩක් ඉන්න යාලු...😚🪄",
    "error": "අයියෝ... Diagram එක හැදෙද්දි පොඩි අවුලක් ආවා යාලු 🥹"
}

client = genai.Client(api_key=GOOGLE_API_KEY)

# ================= HEALTH CHECK SERVER =================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/health', '/']:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', 7860), HealthCheckHandler)
    server.serve_forever()

# ================= FONT DOWNLOAD =================
def download_font_with_retry(urls: list, output_path: str, max_retries: int = 2) -> bool:
    if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
        return True
    for attempt in range(max_retries):
        for current_url in urls:
            try:
                req = urllib.request.Request(current_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    content = response.read()
                    if len(content) < 10000: continue
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    return True
            except Exception:
                continue
    return False

def ensure_fonts_downloaded():
    os.makedirs(FONTS_DIR, exist_ok=True)
    if not os.path.exists(SINHALA_FONT_PATH): download_font_with_retry([SINHALA_FONT_URL], SINHALA_FONT_PATH)
    if not os.path.exists(ENGLISH_FONT_PATH): download_font_with_retry([ENGLISH_FONT_URL], ENGLISH_FONT_PATH)
    if not os.path.exists(EMOJI_FONT_PATH): download_font_with_retry([EMOJI_FONT_URL], EMOJI_FONT_PATH)

    try:
        sys_font_dir = "/usr/share/fonts/truetype/custom"
        os.makedirs(sys_font_dir, exist_ok=True)
        for font in [SINHALA_FONT_PATH, ENGLISH_FONT_PATH, EMOJI_FONT_PATH]:
            if os.path.exists(font):
                shutil.copy(font, sys_font_dir)
        subprocess.run(["fc-cache", "-f"], check=False)
    except Exception as e:
        logger.warning(f"Failed to copy fonts: {e}")

# ================= TEXT & CAPTION HELPERS =================
def fix_ai_sinhala_mistakes(text: str) -> str:
    replacements = {
        'ග්ලයිකපොරීන': 'ග්ලයිකොප්‍රෝටීන',
        'ප්‍ර‌ට‌ෝ න': 'ප්‍රෝටීන',
        'කලෝෙස්ටරෙලෝ': 'කොලෙස්ටරෝල්',
        'සලෛ': 'සෛල',
        'අන්තර්ගත ප්‍රෙටීන': 'අන්තර්ගත ප්‍රෝටීන',
        'ජලාකාර්ෂක': 'ජලාකර්ෂක',
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    text = re.sub(r'\s+([\u0DCA-\u0DDF])', r'\1', text)
    return text.replace('\u200B', '')

def clean_final_caption(raw_caption: str) -> str:
    patterns_to_remove = [
        r' - Educational Diagram for G\.C\.E\. A/L (Science|Physics|Chemistry|Biology)',
        r' - උසස් පෙළ (භෞතික|රසායන|ජීව)? විද්‍යා අධ්‍යාපනික සටහන',
        r'Educational Diagram for G\.C\.E\. A/L (Science|Physics|Chemistry|Biology)',
        r'උසස් පෙළ (භෞතික|රසායන|ජීව)? විද්‍යා අධ්‍යාපනික සටහන'
    ]
    clean_text = raw_caption
    for pattern in patterns_to_remove:
        clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE)
    return clean_text.strip(" -")

def inject_watermark(svg_code: str) -> str:
    watermark_text = "Biovra AI 🧡⚡️ - By @BiologyHUBLK 🩵"
    if watermark_text not in svg_code:
        watermark_svg = f'''
    <text x="800" y="1170" font-family="'Noto Sans Sinhala', 'LKLUG', sans-serif" font-size="20px" fill="#7F8C8D" text-anchor="middle">{watermark_text}</text>
</svg>'''
        svg_code = svg_code.rstrip().replace("</svg>", watermark_svg)
    return svg_code

# ================= PROMPT BUILDER =================
def build_gemini_prompt(user_query: str) -> str:
    is_mindmap = "mind map" in user_query.lower() or "mindmap" in user_query.lower()
    
    common_text_rules = """
**CRITICAL TEXT FORMATTING RULE**:
Restrict ALL text blocks to a MAXIMUM of 2 lines.
For ALL text nodes, use EXACTLY TWO `<tspan>` elements with dy positioning:
- Line 1 (English): dy="0" (font-size: 20px)
- Line 2 (Sinhala): dy="30" (font-size: 20px)
Do NOT use more than 2 lines per text block!
"""
    
    if is_mindmap:
        style_instructions = """
**CREATIVE MIND MAP DESIGN RULES**:
Choose ONE layout style:
1. RADIAL MAP: Root node in center (x="800", y="600"), branches radiating outwards symmetrically.
2. HORIZONTAL TREE: Root node on far left (x="250", y="600"), branches fanning right.
3. ORGANIC CLUSTER: Nodes arranged in a clean grid/cluster with soft rounded pill shapes (`<rect rx="50">`).

- Use varied pastel background colors for nodes.
- Connect nodes using smooth curved paths (`<path d="..." fill="none" stroke="#2C3E50" stroke-width="2"/>`).
"""
    else:
        style_instructions = """
**DIAGRAM DESIGN RULES**:
- Keep structure and labels tightly packed within safe zones.
- Use short straight pointer lines (50px to 80px).
- Labels MUST be free-floating text (no rectangular backgrounds behind diagram labels).
"""

    return f"""
You are {BOT_NAME}, an expert scientific vector illustrator for Sri Lankan G.C.E. A/L Science subjects.
Create a clean educational vector graphic for: "{user_query}"

{style_instructions}
{common_text_rules}

**SAFE CANVAS**: viewBox="0 0 1600 1200". Keep ALL graphics strictly between x="200" to "1400" and y="150" to "1100".
**LANGUAGE**: Every label MUST have English AND genuine Sinhala Unicode.

**OUTPUT FORMAT**:
<<<CAPTION>>>
English Title
Sinhala Title + Emojis
<<<END_CAPTION>>>

<<<SVG>>>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1200" width="1600" height="1200">
<defs>...</defs>
<rect width="1600" height="1200" fill="#ffffff"/>
...
</svg><<<END_SVG>>>
"""

# ================= GENERATE DIAGRAM =================
def sanitize_unwanted_characters(text: str) -> str:
    cleaned = re.sub(r'[^\u0000-\u007F\u0D80-\u0DFF\u00A0-\u00FF\u2000-\u206F\u2600-\u27BF\U0001F000-\U0001FFFF]', '', text)
    return unicodedata.normalize('NFC', fix_ai_sinhala_mistakes(cleaned))

def force_close_xml_tags(svg_code: str) -> str:
    svg_code = svg_code.replace("```xml", "").replace("```svg", "").replace("```", "")
    svg_code = re.sub(r"<<<END_SVG>>>[\s\S]*$", "", svg_code, flags=re.IGNORECASE)
    svg_code = sanitize_unwanted_characters(svg_code)
    last_bracket = svg_code.rfind('>')
    if last_bracket != -1: svg_code = svg_code[:last_bracket+1]
    stack = []
    for match in re.finditer(r'<\s*(/?)\s*([a-zA-Z0-9_\-]+)[^>]*?(/?)>', svg_code):
        is_closing, tag_name, is_self_closing = match.group(1) == '/', match.group(2), match.group(3) == '/'
        if is_self_closing or tag_name.lower() in ['xml', 'doctype']: continue
        if not is_closing: stack.append(tag_name)
        else:
            for i in range(len(stack)-1, -1, -1):
                if stack[i] == tag_name: stack = stack[:i]; break
    for tag in reversed(stack): svg_code += f"\n</{tag}>"
    return svg_code

def generate_diagram_sync(query: str, attempt: int = 0):
    prompt = build_gemini_prompt(query)
    temp = min(0.3 + (attempt * 0.2), 0.8)
    
    # Disable AFC function calls to avoid freezing the model response
    config = genai.types.GenerateContentConfig(
        temperature=temp, 
        top_p=0.95, 
        max_output_tokens=8192,
        tools=[]  
    )
    
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=config
    )
    raw_text = response.text if response else ""
    caption_match = re.search(r"<<<CAPTION>>>\s*([\s\S]*?)\s*<<<END_CAPTION>>>", raw_text, re.IGNORECASE)
    raw_caption = caption_match.group(1).strip() if caption_match else f"Diagram: {query} 🧬"
    
    clean_caption = sanitize_unwanted_characters(clean_final_caption(raw_caption))
    start_idx = raw_text.find("<svg")
    if start_idx == -1: return clean_caption, None
    return clean_caption, force_close_xml_tags(raw_text[start_idx:])

# ================= PLAYWRIGHT RENDERING =================
async def render_svg_with_playwright(svg_code: str) -> bytes:
    from playwright.async_api import async_playwright
    
    font_style = """
    <style>
        text, tspan { 
            font-family: 'Noto Sans Sinhala', 'LKLUG', sans-serif !important; 
            text-rendering: optimizeLegibility;
        }
    </style>
    """
    if "</defs>" in svg_code:
        svg_code = svg_code.replace("</defs>", f"{font_style}</defs>")
    elif "<svg" in svg_code:
        svg_code = re.sub(r'(<svg[^>]*>)', r'\1' + font_style, svg_code, count=1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        try:
            page = await browser.new_page(viewport={'width': 1600, 'height': 1200})
            await page.set_content(svg_code, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(0.5)
            png_bytes = await page.screenshot(type='png', full_page=True, timeout=10000)
            return png_bytes
        finally:
            await browser.close()

async def convert_svg_to_png_bytes(svg_code: str) -> bytes:
    ensure_fonts_downloaded()
    svg_code = inject_watermark(unicodedata.normalize('NFC', svg_code))
    return await render_svg_with_playwright(svg_code)

# ================= REQUEST PROCESSOR =================
async def process_diagram_request(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    waiting_msg = await update.message.reply_text(MESSAGES["waiting"])
    
    try:
        async with asyncio.timeout(45):
            png_bytes, caption = None, ""
            for attempt in range(2):
                try:
                    caption, svg_code = await asyncio.to_thread(generate_diagram_sync, query_text, attempt)
                    if not svg_code: raise ValueError("No SVG produced")
                    
                    png_bytes = await convert_svg_to_png_bytes(svg_code)
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt+1} failed: {e}")

            if png_bytes:
                await update.message.reply_photo(
                    photo=io.BytesIO(png_bytes), 
                    caption=caption, 
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(MESSAGES["error"])

    except TimeoutError:
        logger.error(f"Request timed out for query: {query_text}")
        await update.message.reply_text("⏱️ Diagram generation took too long. Please try again!")
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        await update.message.reply_text(MESSAGES["error"])
    finally:
        try:
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=waiting_msg.message_id)
        except Exception:
            pass

# ================= MEMBERSHIP & HANDLERS =================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE, channel_username: str) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

async def is_user_exempt(user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    if user_id in EXEMPT_USER_IDS: return True
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ['creator', 'administrator']: return True
    except Exception:
        pass
    return False

async def send_private_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join Group 🌿🤍", url=GROUP_LINK)]])
    try:
        await context.bot.send_sticker(chat_id=chat.id, sticker=STICKER_FILE_ID)
    except Exception as e:
        logger.warning(f"Failed to send sticker: {e}")
    await update.message.reply_text(MESSAGES["private_chat_not_allowed"], reply_markup=keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat: return

    # Always reply with welcome screen in PMs
    if chat.type == "private":
        await send_private_welcome(update, context)
        return

    text = message.text or message.caption or ""
    has_mention = bool(re.search(rf"@{BOT_USERNAME}(\s|$|\?|\.|,)", text, re.IGNORECASE))
    is_reply = message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.username and message.reply_to_message.from_user.username.lower() == BOT_USERNAME.lower()
    
    if not has_mention and not is_reply:
        return

    cleaned_query = re.sub(rf"@{BOT_USERNAME}\s*", "", text, flags=re.IGNORECASE).strip()
    if not cleaned_query: cleaned_query = "general science diagram"

    if await is_user_exempt(user.id, context, chat.id):
        await process_diagram_request(update, context, cleaned_query)
        return

    in_main = await check_membership(user.id, context, MAIN_CHANNEL_USERNAME)
    in_backup = await check_membership(user.id, context, BACKUP_CHANNEL_USERNAME)

    if in_main and in_backup:
        await process_diagram_request(update, context, cleaned_query)
    else:
        context.user_data['pending_query'] = cleaned_query
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("අපේ Main Channel එක 🤍🌝", url=MAIN_CHANNEL_LINK)],
            [InlineKeyboardButton("අපේ Backup Channel එක 🤍🌝", url=BACKUP_CHANNEL_LINK)],
            [InlineKeyboardButton("මම දෙකටම join වෙලා ඉන්නේ ✅", callback_data="check_join")]
        ])
        await update.message.reply_text(MESSAGES["not_a_member"], reply_markup=keyboard)

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id, chat_id = query.from_user.id, query.message.chat_id

    in_main = await check_membership(user_id, context, MAIN_CHANNEL_USERNAME)
    in_backup = await check_membership(user_id, context, BACKUP_CHANNEL_USERNAME)

    if in_main and in_backup:
        original_query = context.user_data.get('pending_query')
        if original_query:
            await query.message.delete()
            fake_update = update._replace(message=query.message)
            fake_update.effective_user = query.from_user
            fake_update.effective_chat = query.message.chat
            await process_diagram_request(fake_update, context, original_query)
        else:
            await query.message.reply_text("කරුණාකර නැවත ඔබගේ ප්‍රශ්නය ටයිප් කරන්න.")
    else:
        await query.message.reply_text("Channel දෙකටම join වෙලා නැහැ..🙃")

# ================= APP START =================
async def post_init(application: Application):
    await application.bot.get_me()

def main():
    try:
        ensure_fonts_downloaded()
    except Exception as e:
        logger.warning(f"Font download issue: {e}")
    
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # 1. Connection Timeouts increased to 20s to stop Render from failing to connect
    request_config = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0
    )

    # 2. Build App with robust request config
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request_config)
        .get_updates_request(request_config)
        .post_init(post_init)
        .build()
    )
    
    # 3. Add explicit /start command handler for PMs, plus message/callback handlers
    app.add_handler(CommandHandler("start", handle_message))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))
    app.add_handler(CallbackQueryHandler(join_callback, pattern="check_join"))
    
    logger.info(f"⚡ {BOT_NAME} Bot started!")
    
    # 4. bootstrap_retries=-1 means if network drops on startup, keep retrying silently!
    app.run_polling(
        drop_pending_updates=False,
        bootstrap_retries=-1
    )

if __name__ == "__main__":
    main()
