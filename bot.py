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
from pathlib import Path
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
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
GEMINI_MODEL_NAME = "gemini-3.5-flash-lite"  # Updated to latest

if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set!")
    sys.exit(1)

if not GOOGLE_API_KEY:
    logger.error("❌ GOOGLE_API_KEY environment variable not set!")
    sys.exit(1)

BOT_USERNAME = "BioDiagrams_Bot"  
BOT_NAME = "Biovra AI 🧡⚡️"

# Channel details
MAIN_CHANNEL_LINK = "https://t.me/BiologyHubLK"
MAIN_CHANNEL_USERNAME = "@BiologyHubLK"
BACKUP_CHANNEL_LINK = "https://t.me/BiologyHubLKBackup"
BACKUP_CHANNEL_USERNAME = "@BiologyHubLKBackup"

GROUP_LINK = "https://t.me/BiologyHUbLK_Chat"
STICKER_FILE_ID = "CAACAgIAAxkBAAERojJqa38J94V3D0krLrqkGC4_fubIBAACnA0AAmVJ2Eh6rZ_M40MN6j0E"

# Exempt user IDs (these users skip membership check)
EXEMPT_USER_IDS = [8175452079]  # add more if needed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

SINHALA_FONT_NAME = "NotoSansSinhala-Regular.ttf"
ENGLISH_FONT_NAME = "NotoSans-Regular.ttf"
EMOJI_FONT_NAME = "NotoColorEmoji.ttf"
SINHALA_FONT_PATH = os.path.join(FONTS_DIR, SINHALA_FONT_NAME)
ENGLISH_FONT_PATH = os.path.join(FONTS_DIR, ENGLISH_FONT_NAME)
EMOJI_FONT_PATH = os.path.join(FONTS_DIR, EMOJI_FONT_NAME)

# Font URLs
SINHALA_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSansSinhala/NotoSansSinhala-Regular.ttf"
ENGLISH_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
EMOJI_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@main/fonts/NotoColorEmoji.ttf"

ALT_SINHALA_FONT_URL = "https://fonts.gstatic.com/s/notosanssinhala/v26/NotoSansSinhala-Regular.ttf"
ALT_ENGLISH_FONT_URL = "https://fonts.gstatic.com/s/notosans/v35/NotoSans-Regular.ttf"
ALT_EMOJI_FONT_URL = "https://fonts.gstatic.com/s/notoemoji/v47/NotoColorEmoji-Regular.ttf"

MESSAGES = {
    "private_chat_not_allowed": f"Hi! යාලූ...👋🏻☺️ මමයි {BOT_NAME}, මගෙත් එක්ක Chat කරන්න අපේ Group එකට join වෙන්න 🤗",
    "not_a_member": "AI පාවිච්චි කරන්න අපේ channel දෙකටම join වෙන්න 🤍🌿",
    "waiting": "පොඩ්ඩක් ඉන්න යාලු...😚🪄",
    "error": "අයියෝ... Diagram එක හැදෙද්දි පොඩි අවුලක් ආවා යාලු 🥹 (කරුණාකර නැවත උත්සාහ කරන්න)"
}

# Configure Gemini API
client = genai.Client(api_key=GOOGLE_API_KEY)

# ================= FLASK APP FOR WEBHOOK =================
flask_app = Flask(__name__)
bot_app = None

@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        update = Update.de_json(request.get_json(), bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy", "message": "Bot is running!"})

@flask_app.route('/')
def home():
    return jsonify({"status": "running", "message": "Bot is running!"})

# ================= FONT DOWNLOAD =================
def download_font_with_retry(urls: list, output_path: str, max_retries: int = 3) -> bool:
    if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
        return True
    for attempt in range(max_retries):
        for current_url in urls:
            try:
                req = urllib.request.Request(current_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    content = response.read()
                    if len(content) < 10000: continue
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    return True
            except Exception:
                continue
        import time
        time.sleep(1)
    return False

def ensure_fonts_downloaded():
    os.makedirs(FONTS_DIR, exist_ok=True)
    if not os.path.exists(SINHALA_FONT_PATH): download_font_with_retry([SINHALA_FONT_URL, ALT_SINHALA_FONT_URL], SINHALA_FONT_PATH)
    if not os.path.exists(ENGLISH_FONT_PATH): download_font_with_retry([ENGLISH_FONT_URL, ALT_ENGLISH_FONT_URL], ENGLISH_FONT_PATH)
    if not os.path.exists(EMOJI_FONT_PATH): download_font_with_retry([EMOJI_FONT_URL, ALT_EMOJI_FONT_URL], EMOJI_FONT_PATH)

    try:
        sys_font_dir = "/usr/share/fonts/truetype/custom"
        os.makedirs(sys_font_dir, exist_ok=True)
        for font in [SINHALA_FONT_PATH, ENGLISH_FONT_PATH, EMOJI_FONT_PATH]:
            if os.path.exists(font):
                shutil.copy(font, sys_font_dir)
        subprocess.run(["fc-cache", "-f"], check=False)
    except Exception as e:
        logger.warning(f"Failed to copy fonts to system font dir: {e}")

# ================= FIX AI SINHALA MISSPELLINGS =================
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
    text = text.replace('\u200B', '')
    return text

# ================= FIX CAPTION CLEANUP =================
def clean_final_caption(raw_caption: str) -> str:
    patterns_to_remove = [
        r' - Educational Diagram for G\.C\.E\. A/L Science',
        r' - Educational Diagram for G\.C\.E\. A/L Physics',
        r' - Educational Diagram for G\.C\.E\. A/L Chemistry',
        r' - Educational Diagram for G\.C\.E\. A/L Biology',
        r' - උසස් පෙළ භෞතික විද්‍යා අධ්‍යාපනික සටහන',
        r' - උසස් පෙළ රසායන විද්‍යා අධ්‍යාපනික සටහන',
        r' - උසස් පෙළ ජීව විද්‍යා අධ්‍යාපනික සටහන',
        r' - උසස් පෙළ විද්‍යා අධ්‍යාපනික සටහන',
        r'Educational Diagram for G\.C\.E\. A/L Physics',
        r'Educational Diagram for G\.C\.E\. A/L Chemistry',
        r'Educational Diagram for G\.C\.E\. A/L Biology',
        r'Educational Diagram for G\.C\.E\. A/L Science',
        r'උසස් පෙළ භෞතික විද්‍යා අධ්‍යාපනික සටහන',
        r'උසස් පෙළ රසායන විද්‍යා අධ්‍යාපනික සටහන',
        r'උසස් පෙළ ජීව විද්‍යා අධ්‍යාපනික සටහන',
        r'උසස් පෙළ විද්‍යා අධ්‍යාපනික සටහන'
    ]
    
    clean_text = raw_caption
    for pattern in patterns_to_remove:
        clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE)
        
    clean_text = re.sub(r'^[\s\-]+|[\s\-]+$', '', clean_text)
    return clean_text.strip()

# ================= FORCE INJECT WATERMARK =================
def inject_watermark(svg_code: str) -> str:
    watermark_text = "Biovra AI 🧡⚡️ - By @BiologyHUBLK 🩵"
    if watermark_text not in svg_code:
        watermark_svg = f'''
    <text x="800" y="1150" font-family="'Noto Sans Sinhala', 'LKLUG', sans-serif" font-size="20px" fill="#7F8C8D" text-anchor="middle">{watermark_text}</text>
</svg>'''
        svg_code = svg_code.rstrip().replace("</svg>", watermark_svg)
    return svg_code

# ================= UPDATED PROMPT =================
def build_gemini_prompt(user_query: str) -> str:
    is_mindmap = "mind map" in user_query.lower() or "mindmap" in user_query.lower()
    
    if is_mindmap:
        style_instructions = """
**MIND MAP DESIGN RULES**:
- Space out the central node and branch nodes generously across the entire 1600x1200 canvas.
- Nodes MUST NOT overlap each other.
- **MANDATORY**: You MUST draw a `<rect>` or `<circle>` background for EVERY text node (label).
- Format nodes EXACTLY like this example template:
  <rect x="200" y="300" width="280" height="120" rx="15" fill="#E8F8F5" stroke="#2C3E50" stroke-width="2"/>
  <text x="340" y="340" text-anchor="middle">
      <tspan x="340" dy="0" font-size="22px" font-weight="600" fill="#1A1A2E">English Text</tspan>
      <tspan x="340" dy="35" font-size="20px" font-weight="500" fill="#16213E">සිංහල පෙළ</tspan>
      <tspan x="340" dy="25" font-size="16px" fill="#34495E">Sub-text / Extra Details</tspan>
  </text>
"""
    else:
        style_instructions = """
**DIAGRAM DESIGN RULES**:
- Keep the structure, Title, and Labels tightly packed to fit perfectly on the canvas. 
- Use straight pointer lines to connect labels to the specific parts of the graphic.
- **CRITICAL: DO NOT** draw boxes, rectangles (`<rect>`), or circles (`<circle>`) around the label texts. The labels MUST be free-floating text.
- Format labels EXACTLY like this example template (NO `<rect>` background):
  <text x="340" y="340" text-anchor="start">
      <tspan x="340" dy="0" font-size="22px" font-weight="600" fill="#1A1A2E">English Text</tspan>
      <tspan x="340" dy="35" font-size="20px" font-weight="500" fill="#16213E">සිංහල පෙළ</tspan>
  </text>
"""

    return f"""
You are {BOT_NAME}, an expert scientific vector graphic illustrator for Sri Lankan G.C.E. A/L Science subjects (Biology, Chemistry, and Physics).
The user requested an educational graphic for: "{user_query}"

**YOUR GOAL**: Create a simple, clean, professional textbook-quality educational graphic.

{style_instructions}

**QUALITY STANDARDS**:
1. **Visual Appeal**: Use modern, clean aesthetics with soft pastel gradients and dark outlines for drawings.
2. **Scientific Accuracy**: Ensure all structures and branches are logically placed and precise.
3. **Simplicity**: DO NOT include extra legends, keys, or unnecessary decorative elements. ONLY draw Title, Graphic, and Labels.

**LANGUAGE RULES (STRICT SINHALA & ENGLISH)**:
- EVERY label and mind map node MUST be in BOTH English AND genuine Sinhala (සිංහල). 
- Use ONLY Sinhala Unicode (U+0D80 to U+0DFF). DO NOT put spaces between a Sinhala letter and its vowel modifier (pillama).

**CRITICAL DESIGN & TEXT OVERLAP RULES (READ CAREFULLY)**:

1. **CANVAS**: viewBox="0 0 1600 1200" with white background.

2. **MANDATORY TITLE**: You MUST include the Main Title at x="800" y="80" (English) and Subtitle at x="800" y="130" (Sinhala). DO NOT skip the title!

3. **NODE & TEXT STRUCTURE (PREVENT BROKEN TEXT)**:
   - To prevent text from dropping to the bottom in a single broken line, EVERY `<tspan>` MUST have the EXACT SAME `x` coordinate as its parent `<text>` tag.

4. **SUPERSCRIPTS AND SUBSCRIPTS**:
   - DO NOT use HTML `<sub>` or `<sup>` tags (they break SVG rendering).
   - For **subscripts** (e.g., H₂O, CO₂), use inline SVG tspan with baseline-shift: `H<tspan baseline-shift="sub" font-size="0.7em">2</tspan>O`
   - For **superscripts** (e.g., x², Mg²⁺), use inline SVG tspan with baseline-shift: `Mg<tspan baseline-shift="super" font-size="0.7em">2+</tspan>`
   - Do NOT add a new `x` attribute to the inline baseline-shift tspan, keep it exactly as shown above.

5. **STRICT MARGINS**: Keep ALL content strictly within x="100" to "1500", and y="150" to "1100".

**COLORS AND STYLES**:
- Use pastel colors for structures (Pink, Blue, Green, Yellow, Purple, Orange) with dark (#2C3E50) outlines.
- English labels: font-size="22px", fill="#1A1A2E", font-weight="600".
- Sinhala labels: font-size="20px", fill="#16213E", font-weight="500".

**OUTPUT FORMAT**:
<<<CAPTION>>>
English Title (Short, without suffixes like "- Educational Diagram")
Sinhala Title (Short, without suffixes like "- උසස් පෙළ") + Space + [2-3 scientific emojis]
<<<END_CAPTION>>>

<<<SVG>>>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1200" width="1600" height="1200">
<defs>...</defs>
<rect width="1600" height="1200" fill="#ffffff"/>
...
</svg>
<<<END_SVG>>>
"""

# ================= MEMBERSHIP CHECK FUNCTIONS =================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE, channel_username: str) -> bool:
    """Check if user is a member of a given channel"""
    try:
        member = await context.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except:
        return False

async def is_user_exempt(user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Check if user is exempt from membership check (by ID or admin)"""
    if user_id in EXEMPT_USER_IDS:
        return True
    # Check if user is an admin in the group (if this is a group chat)
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ['creator', 'administrator']:
            return True
    except:
        pass
    return False

# ================= JOIN MESSAGE AND CALLBACK =================
async def send_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the join channels message with buttons"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("අපේ Main Channel එක 🤍🌝", url=MAIN_CHANNEL_LINK)],
        [InlineKeyboardButton("අපේ Backup Channel එක 🤍🌝", url=BACKUP_CHANNEL_LINK)],
        [InlineKeyboardButton("මම දෙකටම join වෙලා ඉන්නේ ✅", callback_data="check_join")]
    ])
    await update.message.reply_text(
        MESSAGES["not_a_member"],
        reply_markup=keyboard
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback when user clicks 'I have joined both'"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # Check membership in both channels
    in_main = await check_membership(user_id, context, MAIN_CHANNEL_USERNAME)
    in_backup = await check_membership(user_id, context, BACKUP_CHANNEL_USERNAME)

    if in_main and in_backup:
        # User is in both, now we proceed to process the original message
        original_query = context.user_data.get('pending_query')
        if original_query:
            # Delete the join message and proceed
            await query.message.delete()
            fake_update = update._replace(message=query.message)
            fake_update.effective_user = query.from_user
            fake_update.effective_chat = query.message.chat
            await process_diagram_request(fake_update, context, original_query)
        else:
            await query.message.reply_text("කරුණාකර නැවත ඔබගේ ප්‍රශ්නය ටයිප් කරන්න.")
    else:
        # Still not in both, show the join message again
        await query.message.reply_text(
            "Channel දෙකටම join වෙලා නැහැ..🙃 join වෙලා 'join වෙලා ඉන්නේ ✅' ඔබන්න.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("අපේ Main Channel එක 🤍🌝", url=MAIN_CHANNEL_LINK)],
                [InlineKeyboardButton("අපේ Backup Channel එක 🤍🌝", url=BACKUP_CHANNEL_LINK)],
                [InlineKeyboardButton("මම දෙකටම join වෙලා ඉන්නේ ✅", callback_data="check_join")]
            ])
        )

async def process_diagram_request(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    """Process the diagram generation (used after membership pass)"""
    waiting_msg = await update.message.reply_text(MESSAGES["waiting"])
    
    png_bytes, caption = None, ""
    for attempt in range(3):
        try:
            caption, svg_code = generate_diagram(query_text, attempt)
            if not svg_code: raise ValueError("No SVG")
            png_bytes = await convert_svg_to_png_bytes(svg_code)
            break
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            if attempt == 2:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=waiting_msg.message_id)
                await update.message.reply_text(MESSAGES["error"])
                return
    
    if png_bytes:
        await update.message.reply_photo(photo=io.BytesIO(png_bytes), caption=caption, parse_mode="HTML")
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=waiting_msg.message_id)

# ================= GENERATE DIAGRAM FUNCTIONS =================
def sanitize_unwanted_characters(text: str) -> str:
    cleaned = re.sub(r'[^\u0000-\u007F\u0D80-\u0DFF\u00A0-\u00FF\u2000-\u206F\u2600-\u27BF\U0001F000-\U0001FFFF]', '', text)
    cleaned = fix_ai_sinhala_mistakes(cleaned)
    return unicodedata.normalize('NFC', cleaned)

def force_close_xml_tags(svg_code: str) -> str:
    svg_code = svg_code.replace("```xml", "").replace("```svg", "").replace("```", "")
    svg_code = re.sub(r"<<<END_SVG>>>[\s\S]*$", "", svg_code, flags=re.IGNORECASE)
    svg_code = sanitize_unwanted_characters(svg_code)
    last_bracket = svg_code.rfind('>')
    if last_bracket != -1: svg_code = svg_code[:last_bracket+1]
    stack = []
    for match in re.finditer(r'<\s*(/?)\s*([a-zA-Z0-9_\-]+)[^>]*?(/?)>', svg_code):
        is_closing = match.group(1) == '/'
        tag_name = match.group(2)
        is_self_closing = match.group(3) == '/'
        if is_self_closing or tag_name.lower() in ['xml', 'doctype']: continue
        if not is_closing: stack.append(tag_name)
        else:
            for i in range(len(stack)-1, -1, -1):
                if stack[i] == tag_name: stack = stack[:i]; break
    for tag in reversed(stack): svg_code += f"\n</{tag}>"
    return svg_code

def generate_diagram(query: str, attempt: int = 0):
    prompt = build_gemini_prompt(query)
    temp = min(0.1 + (attempt * 0.2), 0.7)
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=genai.types.GenerateContentConfig(temperature=temp, top_p=0.95, max_output_tokens=8192)
    )
    raw_text = response.text if response else ""
    caption_match = re.search(r"<<<CAPTION>>>\s*([\s\S]*?)\s*<<<END_CAPTION>>>", raw_text, re.IGNORECASE)
    raw_caption = caption_match.group(1).strip() if caption_match else f"Diagram: {query} 🧬"
    
    clean_caption = clean_final_caption(raw_caption)
    clean_caption = sanitize_unwanted_characters(clean_caption)

    start_idx = raw_text.find("<svg")
    if start_idx == -1: return clean_caption, None
    raw_svg = raw_text[start_idx:]
    return clean_caption, force_close_xml_tags(raw_svg)

# ================== STRICT PLAYWRIGHT RENDERING ENGINE ==================
async def render_svg_with_playwright(svg_code: str) -> bytes:
    try:
        from playwright.async_api import async_playwright
        
        # Updated font style to strictly cover both text and tspan tags
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
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--single-process'
                ]
            )
            page = await browser.new_page(viewport={'width': 1600, 'height': 1200})
            
            await page.set_content(svg_code, wait_until="networkidle")
            await page.wait_for_function("document.fonts.ready")
            
            png_bytes = await page.screenshot(type='png', full_page=True)
            await browser.close()
            return png_bytes
            
    except Exception as e:
        logger.error(f"Playwright crashed: {e}")
        raise e

async def convert_svg_to_png_bytes(svg_code: str) -> bytes:
    ensure_fonts_downloaded()
    svg_code = unicodedata.normalize('NFC', svg_code)
    svg_code = inject_watermark(svg_code)
    return await render_svg_with_playwright(svg_code)

# ================= MESSAGE HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat: return
    text = message.text or message.caption or ""

    # Private chat handling
    if chat.type == "private":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Join Group 🌿🤍", url=GROUP_LINK)
        ]])
        try:
            await context.bot.send_sticker(chat_id=chat.id, sticker=STICKER_FILE_ID)
        except Exception as e:
            logger.warning(f"Sticker sending failed: {e}")
            
        await message.reply_text(MESSAGES["private_chat_not_allowed"], reply_markup=keyboard)
        return

    # Check if bot is mentioned or replied
    has_mention = bool(re.search(rf"@{BOT_USERNAME}(\s|$|\?|\.|,)", text, re.IGNORECASE))
    is_reply = message.reply_to_message and message.reply_to_message.from_user.username and message.reply_to_message.from_user.username.lower() == BOT_USERNAME.lower()
    if not has_mention and not is_reply:
        return

    # Extract query
    cleaned_query = re.sub(rf"@{BOT_USERNAME}\s*", "", text, flags=re.IGNORECASE).strip()
    if not cleaned_query:
        cleaned_query = "general science diagram"

    # Check exemption (user ID or admin)
    if await is_user_exempt(user.id, context, chat.id):
        # Exempt, proceed directly
        await process_diagram_request(update, context, cleaned_query)
        return

    # Check membership in both channels
    in_main = await check_membership(user.id, context, MAIN_CHANNEL_USERNAME)
    in_backup = await check_membership(user.id, context, BACKUP_CHANNEL_USERNAME)

    if in_main and in_backup:
        # User is in both, proceed
        await process_diagram_request(update, context, cleaned_query)
    else:
        # Store the query in context for later use after joining
        context.user_data['pending_query'] = cleaned_query
        await send_join_message(update, context)

# ================= APPLICATION START =================
async def post_init(application: Application):
    """
    Workaround for python-telegram-bot ExtBot initialization bug.
    Forces the bot to fetch its identity before starting the updater task.
    """
    await application.bot.get_me()

async def main():
    global bot_app
    
    # Ensure fonts are downloaded
    try:
        ensure_fonts_downloaded()
    except Exception as e:
        logger.warning(f"Font download issue: {e}")
    
    # Create application with the post_init fix
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Add handlers
    bot_app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))
    bot_app.add_handler(CallbackQueryHandler(join_callback, pattern="check_join"))
    
    # Set webhook (Render URL එකට change කරන්න)
    webhook_url = "https://myrepforteelgrambot.onrender.com/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook set to: {webhook_url}")
    
    logger.info(f"⚡ {BOT_NAME} Bot is running... (Webhook Mode 🔥)")
    
    # Start Flask server
    flask_app.run(host='0.0.0.0', port=7860)

if __name__ == "__main__":
    asyncio.run(main())
