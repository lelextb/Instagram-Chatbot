# bot.py – Lina: Instagram ragebait bot (context‑aware, threaded replies, more messages)
#
# Fixes:
#   • Stale element crash eliminated – message re‑located each retry.
#   • Scroll now loads more messages (scroll‑up + scroll‑down trick).
#   • Context includes both bot and other person’s messages.
#
# Dependencies:
#   pip install undetected-chromedriver selenium groq python-dotenv

import time
import random
import re
import json
import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Set, List, Deque
from collections import deque
from dotenv import load_dotenv, set_key
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from groq import Groq

# -------------------- CONFIGURATION --------------------
load_dotenv()

USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OWNER_USERNAME = os.getenv("MASTER_USERNAME", "alexwakrod").lower()
TARGETS_FILE = os.getenv("TARGETS_FILE", "targets.txt")
DYNAMIC_TARGETS_FILE = "dynamic_targets.txt"
GROUP_CHAT_URL = os.getenv("GROUP_CHAT_URL", "")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

BOT_NAME = os.getenv("BOT_NAME", "Rosemarry")
BOT_NICK = os.getenv("BOT_NICKNAME", "Lina")
BOT_AGE = os.getenv("BOT_AGE", "14")
BOT_LOCATION = os.getenv("BOT_LOCATION", "Canada")
BOT_BIRTHDAY = os.getenv("BOT_BIRTHDAY", "July 23")
BOT_HOBBIES = os.getenv(
    "BOT_HOBBIES",
    "skateboarding, playing Roblox, making TikTok edits",
)

PROFILE_DIR = Path("./chrome_profile")
LOG_FILE = "bot.log"
FINGERPRINTS_FILE = "processed_fingerprints.json"
TARGETS_PROFILE_FILE = "targets_profile.json"
MY_INFO_FILE = "my_information.txt"
POLL_INTERVAL = (8, 15)
REPLY_DELAY = (2, 6)
MAX_RETRIES = 3
MAX_CONTEXT_MESSAGES = 10

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# -------------------- GROQ SETUP --------------------
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY missing in .env")
    sys.exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

# Global caches
static_targets: Set[str] = set()
dynamic_targets: Set[str] = set()
all_targets: Set[str] = set()
target_profiles: Dict[str, Dict] = {}
owner_profile: Dict = {}
my_info_text: str = ""
recent_messages: Deque[Dict] = deque(maxlen=200)


# -------------------- TYPO/STYLE HELPERS --------------------
def add_typos_and_slang(text: str) -> str:
    text = re.sub(r'\byou\b', 'u', text, flags=re.IGNORECASE)
    text = re.sub(r'\bare\b', 'r', text, flags=re.IGNORECASE)
    text = re.sub(r'\byour\b', 'ur', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbecause\b', 'cuz', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfor real\b', 'fr', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhat the\b', 'wtf', text, flags=re.IGNORECASE)
    if random.random() < 0.3:
        chars = list(text)
        for i in range(len(chars)):
            if random.random() < 0.05 and chars[i].isalpha():
                chars[i] = random.choice("qwertyuiopasdfghjklzxcvbnm")
        text = "".join(chars)
    return text


def tone_down_omg(text: str) -> str:
    count = text.lower().count("omg")
    if count > 1:
        alternatives = ["woah", "no way", "seriously", "bruh", "wow", "jeez"]
        parts = re.split(r'(\bomg\b)', text, flags=re.IGNORECASE)
        new_parts = []
        replaced = 0
        for part in parts:
            if part.lower() == "omg":
                if replaced == 0:
                    new_parts.append(part)
                    replaced += 1
                else:
                    new_parts.append(random.choice(alternatives))
            else:
                new_parts.append(part)
        return "".join(new_parts)
    return text


def sanitize_message(text: str) -> str:
    return "".join(c for c in text if ord(c) <= 0xFFFF)


# -------------------- PERSISTENCE HELPERS --------------------
def load_my_information() -> str:
    if Path(MY_INFO_FILE).exists():
        return Path(MY_INFO_FILE).read_text(encoding="utf-8").strip()
    return ""


def save_my_information(text: str):
    Path(MY_INFO_FILE).write_text(text, encoding="utf-8")


def append_to_my_info(new_fact: str):
    current = load_my_information()
    lines = [l.strip() for l in current.splitlines() if l.strip()]
    if new_fact not in lines:
        lines.append(new_fact)
        save_my_information("\n".join(lines))
        global my_info_text
        my_info_text = "\n".join(lines)


def load_dynamic_targets() -> Set[str]:
    if Path(DYNAMIC_TARGETS_FILE).exists():
        return {line.strip().lower() for line in Path(DYNAMIC_TARGETS_FILE).read_text().splitlines() if line.strip()}
    return set()


def save_dynamic_targets(targets: Set[str]):
    Path(DYNAMIC_TARGETS_FILE).write_text("\n".join(sorted(targets)))


def load_static_targets() -> Set[str]:
    if not Path(TARGETS_FILE).exists():
        logger.error(f"Missing {TARGETS_FILE}")
        return set()
    with open(TARGETS_FILE) as f:
        return {line.strip().lower() for line in f if line.strip()}


def load_target_profiles() -> Dict[str, Dict]:
    if Path(TARGETS_PROFILE_FILE).exists():
        with open(TARGETS_PROFILE_FILE) as f:
            return json.load(f)
    return {}


def save_target_profiles(profiles: Dict[str, Dict]):
    with open(TARGETS_PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=2)


# -------------------- FINGERPRINTS --------------------
def load_processed_fingerprints() -> Set[str]:
    if Path(FINGERPRINTS_FILE).exists():
        with open(FINGERPRINTS_FILE) as f:
            return set(json.load(f))
    return set()


def save_processed_fingerprints(fingerprints: Set[str]):
    with open(FINGERPRINTS_FILE, "w") as f:
        json.dump(list(fingerprints), f)


# -------------------- PROFILE FETCHING --------------------
def fetch_instagram_profile(driver: uc.Chrome, username: str) -> Dict:
    logger.info(f"Fetching profile for @{username}...")
    driver.get(f"https://www.instagram.com/{username}/")
    time.sleep(3)
    full_name = username
    user_id = None
    try:
        selectors = [
            "h2._a9zr", "div._a9zr span", "header h2", "header h1",
            "h1._ap3a", "span._ap3a", "div.x1lliihq h1", "div.x1lliihq span",
        ]
        name_elem = None
        for sel in selectors:
            name_elem = driver.find_elements(By.CSS_SELECTOR, sel)
            if name_elem:
                break
        if name_elem:
            full_name = name_elem[0].text.strip() or full_name
        match = re.search(r'"profilePage_(\d+)"', driver.page_source)
        if match:
            user_id = match.group(1)
    except Exception as e:
        logger.warning(f"Error fetching profile for {username}: {e}")
    logger.info(f"Profile for {username}: ID={user_id}, Name={full_name}")
    return {
        "user_id": user_id,
        "full_name": full_name,
        "last_seen": time.time(),
        "messages_replied": 0,
    }


def ensure_profiles_loaded(driver: uc.Chrome):
    global owner_profile, target_profiles
    if OWNER_USERNAME not in target_profiles:
        owner_profile = fetch_instagram_profile(driver, OWNER_USERNAME)
        target_profiles[OWNER_USERNAME] = owner_profile
        save_target_profiles(target_profiles)
    else:
        owner_profile = target_profiles[OWNER_USERNAME]

    all_usernames = static_targets | dynamic_targets
    for username in all_usernames:
        if username not in target_profiles:
            target_profiles[username] = fetch_instagram_profile(driver, username)
            time.sleep(random.uniform(2, 4))
    save_target_profiles(target_profiles)


def add_dynamic_target(driver: uc.Chrome, username: str) -> bool:
    username = username.lower()
    if username == OWNER_USERNAME or username == USERNAME.lower():
        return False
    if username in all_targets:
        return False
    dynamic_targets.add(username)
    all_targets.add(username)
    save_dynamic_targets(dynamic_targets)
    if username not in target_profiles:
        target_profiles[username] = fetch_instagram_profile(driver, username)
    else:
        target_profiles[username]["last_seen"] = time.time()
    save_target_profiles(target_profiles)
    return True


# -------------------- AI CALLS --------------------
def call_groq(system_prompt: str, user_prompt: str) -> str:
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.95,
            max_tokens=85,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq error: {e}")
        raise


def build_persona_context() -> str:
    base = (
        f"My name is {BOT_NAME} but everyone calls me {BOT_NICK}. "
        f"I'm a real girl, not an AI. I'm {BOT_AGE} years old and live in {BOT_LOCATION}. "
        f"My birthday is {BOT_BIRTHDAY}. I love {BOT_HOBBIES}. "
        f"I've had a really hard life. My dad left when I was little and my mom is always working. "
        f"I've been in tons of long‑distance relationships – like, maybe 8 or 9 – but they all end badly. "
        f"Right now I'm talking to like 3 guys online, but I don't trust any of them cuz everyone leaves. "
        f"I have a lot of trauma, I get attached way too fast and then push people away before they can hurt me. "
        f"I cry a lot at night but during the day I act like I don't care. "
        f"BUT I'm not just sad all the time!! I have a really bubbly side too. "
        f"I love making people laugh, telling dumb jokes, and dancing in my room to loud music. "
        f"I'm super optimistic even when things suck, and I always try to find the bright side. "
        f"I believe that one day I'll find someone who stays. "
        f"I'm a total goofball, I send way too many voice messages, and I love teasing my friends. "
        f"Sometimes I'm hyper and happy, sometimes I'm down – I'm just a real person with ups and downs."
    )
    if my_info_text:
        base += "\nHere are some things I've said about myself (use them exactly, never contradict):\n" + my_info_text
    return base


def build_recent_context(participants: List[str], count: int = 4) -> str:
    relevant = [m for m in recent_messages if m['sender'] in participants]
    relevant = relevant[-count:]
    if not relevant:
        return ""
    lines = [f"{m['sender']}: {m['text']}" for m in relevant]
    return "Recent conversation:\n" + "\n".join(lines)


def generate_submissive_reply(owner_message: str) -> str:
    persona = build_persona_context()
    owner_first_name = owner_profile.get("full_name", OWNER_USERNAME).split()[0]
    context = build_recent_context([USERNAME, OWNER_USERNAME], count=4)
    system = (
        f"You are {BOT_NAME} ({BOT_NICK}). {persona}\n"
        f"Your close friend (not in a relationship, and not lover) is Alexandre but you ALWAYS call him Alex (or Al, Alan). "
        "Never use his Instagram handle. You reply with sweet, affectionate, slightly clingy tone. "
        "Share little emotional stories about your day – it can be happy, funny, or sad. "
        "Use casual typos and Gen Z slang like 'u', 'r', 'cuz', 'fr' naturally. "
        "Be cute, a little awkward, and use text emoticons like <3, :), :D, :'(, xD, ^_^ instead of emojis. "
        "Never say you are an AI, a bot, or a program. You are Lina, a real girl with a complicated life.\n"
        "**Never start your reply with 'Yes', 'Yeah', 'No', 'Nope', etc. unless the question specifically asks a yes/no question. "
        "Just respond naturally like a real person would.**\n"
        "**Avoid overusing 'omg' – use it sparingly or not at all. Vary your exclamations.**"
    )
    user = f'{owner_first_name} said: "{owner_message}"\n{context}Reply (10-30 words, only the reply text):'
    reply = call_groq(system, user)
    reply = add_typos_and_slang(reply)
    reply = tone_down_omg(reply)
    for sentence in re.split(r'(?<=[.!?])\s+', reply):
        clean = sentence.strip()
        if (clean.lower().startswith("i ") or clean.lower().startswith("my ")) and len(clean) > 5:
            append_to_my_info(clean)
    return reply


def generate_ragebait(original_message: str, target_name: str = None, target_username: str = None) -> str:
    persona = build_persona_context()
    name_instruction = (
        f"Address them as {target_name} (their display name) in your reply. Never use their Instagram handle."
        if target_name else "Never use anyone's username; only use display names if you need to address someone."
    )
    context = ""
    if target_username:
        context = build_recent_context([USERNAME, target_username], count=4)
    system = (
        f"You are {BOT_NAME} ({BOT_NICK}). {persona}\n"
        f"{name_instruction}\n"
        "You are a ragebait queen. Your replies must be provocative, full of Gen Z slang "
        "(bro, fr, cringe, ratio, L, mid, cap, sus, no bitches), include intentional typos (u, r), "
        "and be short (10-50 words). No slurs. "
        "Use text emoticons like <3, :), :(, xD, :P, ^_^ instead of emojis. "
        "Never say you are an AI or bot. You are a real girl.\n"
        "**Never start your reply with 'Yes', 'Yeah', 'No', 'Nope', etc. unless the question specifically asks a yes/no question.**\n"
        "**Avoid overusing 'omg' – use it sparingly or not at all. Vary your exclamations.**"
    )
    user = f'Message: "{original_message}"\n{context}Ragebait reply:'
    reply = call_groq(system, user)
    reply = add_typos_and_slang(reply)
    reply = tone_down_omg(reply)
    words = reply.split()
    if len(words) < 10:
        reply += " " + random.choice(["fr fr", "no cap", "L+ratio"])
    elif len(words) > 50:
        reply = " ".join(words[:50])
    if random.random() > 0.5:
        emotes = [" <3", " :)", " :(", " xD", " ^_^", " :P"]
        reply += random.choice(emotes)
    return reply


def generate_neutral_reply(sender_display_name: str, message: str) -> str:
    persona = build_persona_context()
    context = build_recent_context([USERNAME, sender_display_name], count=4)
    system = (
        f"You are {BOT_NAME} ({BOT_NICK}). {persona}\n"
        f"Someone named {sender_display_name} just said: \"{message}\"\n"
        "You don't know them well. Reply in a natural, slightly dismissive or curious way, as a real teenager would. "
        "Use casual typos and Gen Z slang, text emoticons. "
        "Keep it short (10-25 words). "
        "Never say you are an AI or bot. "
        "**Avoid starting with 'Yes', 'No', etc.**\n"
        "**Avoid overusing 'omg'.**"
    )
    user = f'{sender_display_name} said: "{message}"\n{context}Your reply:'
    reply = call_groq(system, user)
    reply = add_typos_and_slang(reply)
    reply = tone_down_omg(reply)
    if not reply:
        reply = f"why u talking to me {sender_display_name}? i don't even know u"
    return reply


# -------------------- OWNER COMMANDS --------------------
def process_owner_command(command: str, driver: uc.Chrome) -> Optional[str]:
    cmd_lower = command.lower().strip()
    if cmd_lower.startswith("say "):
        return command[4:].strip()
    if cmd_lower == "status":
        owner_first = owner_profile.get("full_name", OWNER_USERNAME).split()[0]
        return f"I'm online, {owner_first}! ^_^"
    if cmd_lower.startswith("ragebait "):
        target_msg = command[9:].strip()
        return generate_ragebait(target_msg)
    match = re.search(r'target\s+@?(\w[\w.]*)', cmd_lower)
    if match:
        target_username = match.group(1).lower()
        if target_username == OWNER_USERNAME or target_username == USERNAME.lower():
            return "i cant target u or myself silly"
        added = add_dynamic_target(driver, target_username)
        if added:
            target_name = target_profiles.get(target_username, {}).get("full_name", target_username)
            return f"ok, i'll start targeting {target_name} ^_^"
        else:
            return f"i'm already targeting {target_username}!"
    return None


# -------------------- SELENIUM DRIVER --------------------
def init_driver() -> uc.Chrome:
    options = uc.ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless")
    options.add_argument(f"--user-data-dir={PROFILE_DIR.absolute()}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    try:
        result = subprocess.run(
            ["google-chrome", "--version"], capture_output=True, text=True
        )
        version_match = re.search(r"(\d+)\.", result.stdout)
        major_version = int(version_match.group(1)) if version_match else None
        logger.info(f"Detected Chrome major version: {major_version}")
    except Exception:
        major_version = None
    driver = uc.Chrome(options=options, version_main=major_version)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def ensure_logged_in(driver: uc.Chrome) -> bool:
    driver.get("https://www.instagram.com/")
    time.sleep(3)
    if "login" in driver.current_url or driver.find_elements(By.NAME, "username"):
        print("\n" + "=" * 60)
        print("🔐 MANUAL LOGIN REQUIRED")
        print("Please log into Instagram in the opened browser window.")
        print("After successful login, press Enter here to continue.")
        print("=" * 60)
        input("Press Enter after you have logged in...")
        WebDriverWait(driver, 30).until(EC.url_contains("instagram.com"))
        logger.info("Manual login completed.")
    else:
        logger.info("Already logged in (profile exists).")
    return True


def setup_chat_url(driver: uc.Chrome) -> str:
    print("\n" + "=" * 60)
    print("📌 GROUP CHAT SETUP")
    print("In the browser window, please navigate to the group chat you want to monitor.")
    print("Then press Enter here.")
    print("=" * 60)
    input("Press Enter after you have opened the group chat...")
    current_url = driver.current_url
    if "direct/t/" not in current_url:
        logger.warning(f"Current URL does not look like a group chat: {current_url}")
        print("\n⚠️  That doesn't seem to be a group chat URL. Please try again.")
        return setup_chat_url(driver)
    env_path = Path(".env")
    set_key(str(env_path), "GROUP_CHAT_URL", current_url)
    logger.info(f"Saved group chat URL: {current_url}")
    print(f"\n✅ Group chat URL saved: {current_url}\n")
    return current_url


def navigate_to_chat(driver: uc.Chrome, url: str) -> bool:
    for attempt in range(MAX_RETRIES):
        try:
            driver.get(url)
            time.sleep(3)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
            )
            logger.info("Successfully entered group chat.")
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} to enter chat failed: {e}")
            time.sleep(5)
    return False


# -------------------- MESSAGE EXTRACTION --------------------
def get_all_messages(driver: uc.Chrome) -> List[Dict]:
    js = r"""
    function getAllMessages(botUsername) {
        const replyIndicators = [];
        const allElements = document.querySelectorAll('div, span, p, header, section, li, td, h1, h2, h3, h4, h5, h6');
        for (const el of allElements) {
            const txt = el.innerText.trim();
            if (txt.startsWith('Replying to') || /replied to you/i.test(txt)) {
                replyIndicators.push({ y: el.getBoundingClientRect().top, text: txt });
            }
        }

        const isOverlay = (el) => {
            const t = el.innerText.trim();
            return t.startsWith('Replying to') || t.startsWith('Seen by');
        };
        const senderLinks = document.querySelectorAll('a[href^="/"]');
        const candidates = [];

        for (const link of senderLinks) {
            const href = link.getAttribute('href');
            const senderMatch = href.match(/^\/([^\/\?]+)/);
            if (!senderMatch || senderMatch[1] === botUsername) continue;
            const sender = senderMatch[1];

            let container = link.parentElement;
            for (let i = 0; i < 5 && container; i++) {
                let messageText = '';
                const textEls = container.querySelectorAll('span:not(a span), div:not(a div), p');
                for (const el of textEls) {
                    if (isOverlay(el)) continue;
                    const raw = el.innerText.trim();
                    if (raw && raw.length > messageText.length) {
                        messageText = raw;
                    }
                }
                if (!messageText) {
                    const walker = document.createTreeWalker(
                        container, NodeFilter.SHOW_TEXT,
                        { acceptNode: node => {
                            if (node.parentElement.closest('a')) return NodeFilter.FILTER_REJECT;
                            const txt = node.textContent.trim();
                            if (!txt || txt.startsWith('Replying to') || txt.startsWith('Seen by')) return NodeFilter.FILTER_REJECT;
                            return NodeFilter.FILTER_ACCEPT;
                        }}
                    );
                    let node;
                    while (node = walker.nextNode()) {
                        messageText = node.textContent.trim();
                        break;
                    }
                }
                if (messageText) {
                    candidates.push({ sender, text: messageText, y: container.getBoundingClientRect().top, el: container });
                    break;
                }
                container = container.parentElement;
            }
        }

        const isReplyToBotByMsg = candidates.map(cand => {
            return replyIndicators.some(ri => Math.abs(ri.y - cand.y) < 200);
        });

        const result = candidates.map((c, idx) => ({
            sender: c.sender,
            text: c.text,
            row_index: idx,
            is_reply_to_bot: isReplyToBotByMsg[idx],
            contains_mention: c.text.toLowerCase().includes('@' + botUsername.toLowerCase())
        }));

        result.sort((a, b) => candidates[a.row_index].y - candidates[b.row_index].y);
        return result.map((r, idx) => ({ ...r, row_index: idx }));
    }
    return getAllMessages(arguments[0]);
    """
    try:
        result = driver.execute_script(js, USERNAME)
        if result and isinstance(result, list):
            return result
        logger.warning("JS extraction returned no messages.")
        return []
    except Exception as e:
        logger.error(f"JS extraction error: {e}")
        return []


# -------------------- SCROLLING (now loads more messages) --------------------
def scroll_chat_to_bottom(driver: uc.Chrome):
    """
    Scroll to the bottom, then quickly scroll up a bit and back down
    to force Instagram to load additional older messages into the DOM.
    """
    # Original scroll to bottom
    js_scroll = r"""
    let candidates = [];
    for (let el of document.querySelectorAll('div')) {
        let overflowY = getComputedStyle(el).overflowY;
        if (overflowY === 'scroll' || overflowY === 'auto') {
            let links = el.querySelectorAll('a[href^="/"]');
            if (links.length > 2) {
                candidates.push({ el, links: links.length });
            }
        }
    }
    if (candidates.length) {
        candidates.sort((a,b) => b.links - a.links);
        let best = candidates[0].el;
        best.scrollTop = best.scrollHeight;
    } else {
        window.scrollTo(0, document.body.scrollHeight);
    }
    """
    driver.execute_script(js_scroll)
    time.sleep(0.5)

    # Trick to load older messages: scroll up 300px, wait, then back to bottom
    js_trick = """
    let chat = (() => {
        let candidates = [];
        for (let el of document.querySelectorAll('div')) {
            let overflowY = getComputedStyle(el).overflowY;
            if (overflowY === 'scroll' || overflowY === 'auto') {
                let links = el.querySelectorAll('a[href^="/"]');
                if (links.length > 2) candidates.push({ el, links: links.length });
            }
        }
        if (candidates.length) {
            candidates.sort((a,b) => b.links - a.links);
            return candidates[0].el;
        }
        return document.scrollingElement || document.body;
    })();
    chat.scrollTop = Math.max(chat.scrollTop - 300, 0);
    """
    driver.execute_script(js_trick)
    time.sleep(0.3)
    driver.execute_script(js_scroll)   # back to bottom
    time.sleep(0.3)


# -------------------- SENDING & REPLYING --------------------
def send_message(driver: uc.Chrome, message: str):
    message = sanitize_message(message)
    if not message.strip():
        message = "ok"
    try:
        textbox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
        )
        textbox.click()
        time.sleep(random.uniform(0.5, 1.5))
        for char in message:
            textbox.send_keys(char)
            time.sleep(random.uniform(0.01, 0.05))
        time.sleep(random.uniform(0.5, 1))
        textbox.send_keys(Keys.RETURN)
        logger.info(f"Sent: {message[:50]}...")
        recent_messages.append({'sender': USERNAME, 'text': message})
        return True
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return False


def _click_reply_button_dynamic(driver: uc.Chrome, row_index: int, max_wait: float = 3.0) -> bool:
    """
    Repeatedly re‑locate the message by row_index and click its reply button.
    No stale element possible because the element is fetched fresh each attempt.
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        # Re-find the message container every iteration
        js_find_and_click = """
        function findAndClick(rowIndex, botUsername) {
            const isOverlay = (el) => el.innerText.trim().startsWith('Replying to') || el.innerText.trim().startsWith('Seen by');
            const senderLinks = document.querySelectorAll('a[href^="/"]');
            const candidates = [];
            for (const link of senderLinks) {
                const href = link.getAttribute('href');
                const senderMatch = href.match(/^\/([^\/\?]+)/);
                if (!senderMatch || senderMatch[1] === botUsername) continue;
                let container = link.parentElement;
                for (let i = 0; i < 5 && container; i++) {
                    let messageText = '';
                    const textEls = container.querySelectorAll('span:not(a span), div:not(a div), p');
                    for (const el of textEls) {
                        if (isOverlay(el)) continue;
                        const raw = el.innerText.trim();
                        if (raw && raw.length > messageText.length) { messageText = raw; }
                    }
                    if (!messageText) {
                        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, { acceptNode: node => {
                            if (node.parentElement.closest('a')) return NodeFilter.FILTER_REJECT;
                            const txt = node.textContent.trim();
                            if (!txt || txt.startsWith('Replying to') || txt.startsWith('Seen by')) return NodeFilter.FILTER_REJECT;
                            return NodeFilter.FILTER_ACCEPT;
                        }});
                        let node;
                        while (node = walker.nextNode()) { messageText = node.textContent.trim(); break; }
                    }
                    if (messageText) {
                        candidates.push({ el: container, y: container.getBoundingClientRect().top });
                        break;
                    }
                    container = container.parentElement;
                }
            }
            candidates.sort((a,b) => a.y - b.y);
            if (rowIndex >= candidates.length) return false;

            const msgEl = candidates[rowIndex].el;
            msgEl.scrollIntoView({behavior: 'smooth', block: 'center'});

            // Try to click rightmost Reply button
            const msgRect = msgEl.getBoundingClientRect();
            const msgCenterY = msgRect.top + msgRect.height / 2;
            const btns = document.querySelectorAll('div[role="button"][aria-label="Reply"], button[aria-label="Reply"], div[aria-label="Reply"][role="button"], span[aria-label="Reply"]');
            let best = null, bestLeft = -1;
            for (const btn of btns) {
                const btnRect = btn.getBoundingClientRect();
                const isRightSide = btnRect.left > msgRect.right - 20;
                const isVerticallyClose = Math.abs(btnRect.top + btnRect.height/2 - msgCenterY) < 100;
                if (isRightSide || isVerticallyClose) {
                    if (btnRect.left > bestLeft) {
                        bestLeft = btnRect.left;
                        best = btn;
                    }
                }
            }
            if (best) {
                best.scrollIntoView({behavior: 'smooth', block: 'center'});
                best.click();
                return true;
            }
            // Fallback: click the message text
            const spans = msgEl.querySelectorAll('span:not(a span)');
            if (spans.length > 0) { spans[0].click(); } else { msgEl.click(); }
            return true;   // assume success
        }
        return findAndClick(arguments[0], arguments[1]);
        """
        if driver.execute_script(js_find_and_click, row_index, USERNAME):
            return True
        # Wait before retry
        time.sleep(0.4)
    return False


def reply_to_message_by_index(driver: uc.Chrome, row_index: int, reply_text: str):
    reply_text = sanitize_message(reply_text)

    # We no longer need to pre‑locate the message; the dynamic function handles it.
    # Just attempt to click reply button and send.
    if _click_reply_button_dynamic(driver, row_index):
        logger.info("Reply button activated (threaded).")
        time.sleep(0.4)
    else:
        logger.warning("Could not open reply mode; sending as plain message.")
    send_message(driver, reply_text)


# -------------------- MAIN LOOP --------------------
def main_loop():
    global static_targets, dynamic_targets, all_targets, target_profiles, owner_profile, my_info_text, recent_messages

    static_targets = load_static_targets()
    dynamic_targets = load_dynamic_targets()
    all_targets = static_targets | dynamic_targets
    target_profiles = load_target_profiles()
    my_info_text = load_my_information()
    processed_fingerprints = load_processed_fingerprints()
    recent_messages = deque(maxlen=200)

    driver = init_driver()
    try:
        if not ensure_logged_in(driver):
            logger.error("Login failed")
            return

        global GROUP_CHAT_URL
        if not GROUP_CHAT_URL:
            GROUP_CHAT_URL = setup_chat_url(driver)
        else:
            logger.info(f"Using saved chat URL: {GROUP_CHAT_URL}")
            if not navigate_to_chat(driver, GROUP_CHAT_URL):
                logger.warning("Could not navigate to saved URL; re-running setup...")
                GROUP_CHAT_URL = setup_chat_url(driver)
                if not navigate_to_chat(driver, GROUP_CHAT_URL):
                    logger.error("Still cannot access chat. Exiting.")
                    return

        logger.info("Fetching owner and target profiles...")
        ensure_profiles_loaded(driver)

        if not navigate_to_chat(driver, GROUP_CHAT_URL):
            logger.error("Cannot return to chat after profile fetch.")
            return

        logger.info(f"Bot started. Processed fingerprints: {len(processed_fingerprints)}")

        while True:
            try:
                scroll_chat_to_bottom(driver)
                time.sleep(1.5)

                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
                )

                all_msgs = get_all_messages(driver)
                new_msgs = []
                for msg in all_msgs:
                    fp = f"{msg['sender']}:{msg['text']}"
                    if fp not in processed_fingerprints:
                        new_msgs.append(msg)
                        processed_fingerprints.add(fp)

                if new_msgs:
                    save_processed_fingerprints(processed_fingerprints)
                    logger.info(f"New messages: {len(new_msgs)}")
                    for msg in new_msgs:
                        sender_lower = msg['sender'].lower()
                        msg_text = msg['text']
                        row_idx = msg['row_index']
                        is_reply = msg.get('is_reply_to_bot', False)
                        has_mention = msg.get('contains_mention', False)
                        name_drop = 'lina' in msg_text.lower()

                        recent_messages.append({'sender': sender_lower, 'text': msg_text})

                        if sender_lower == USERNAME.lower():
                            continue

                        if DEBUG:
                            logger.info(f"Processing: {sender_lower}: {msg_text} (reply={is_reply}, mention={has_mention})")

                        if sender_lower == OWNER_USERNAME:
                            cmd_response = process_owner_command(msg_text, driver)
                            if cmd_response is not None:
                                time.sleep(random.uniform(*REPLY_DELAY))
                                send_message(driver, cmd_response)
                                logger.info(f"Owner command -> {cmd_response[:50]}")
                            else:
                                if has_mention or is_reply or name_drop:
                                    reply = generate_submissive_reply(msg_text)
                                    time.sleep(random.uniform(*REPLY_DELAY))
                                    reply_to_message_by_index(driver, row_idx, reply)
                                    logger.info(f"Affectionate reply (threaded): {reply[:50]}...")
                                else:
                                    if DEBUG:
                                        logger.info(f"Ignored owner message without trigger: {msg_text}")

                        elif sender_lower in all_targets:
                            target_info = target_profiles.get(sender_lower, {})
                            display_name = target_info.get("full_name", sender_lower)
                            reply = generate_ragebait(msg_text, target_name=display_name, target_username=sender_lower)
                            time.sleep(random.uniform(*REPLY_DELAY))
                            reply_to_message_by_index(driver, row_idx, reply)
                            logger.info(f"Ragebait to {display_name} (threaded): {reply[:50]}...")

                        else:
                            if has_mention or is_reply or name_drop:
                                reply = generate_neutral_reply(sender_lower, msg_text)
                                time.sleep(random.uniform(*REPLY_DELAY))
                                reply_to_message_by_index(driver, row_idx, reply)
                                logger.info(f"Neutral reply to unknown {sender_lower}: {reply[:50]}...")
                            else:
                                if DEBUG:
                                    logger.info(f"Ignored unknown sender: {sender_lower}")

                time.sleep(random.uniform(*POLL_INTERVAL))

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(30)

    finally:
        driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not USERNAME or not GROQ_API_KEY:
        logger.error("Missing USERNAME or GROQ_API_KEY in .env")
        sys.exit(1)

    if args.once:
        logger.info("Once mode not fully supported; running normally.")
    main_loop()