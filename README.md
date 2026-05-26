# 🤖 Lina – Instagram Ragebait Chatbot

**Lina** is a fully autonomous Instagram chatbot that lives inside any group chat.
She behaves like a real 14‑year‑old girl named **Rosemarry "Lina"**, from Canada.
She responds with **affectionate, clingy replies** to her owner (Alex) and **vicious,
Gen‑Z‑slang‑filled ragebait** to chosen targets. Everyone else is ignored unless they
explicitly mention her, reply to her messages, or say her name.

Lina has a persistent personality, with her own life stories, trauma, and emotional
ups and downs – all stored in a personal memory file. She uses **Groq AI** for text
generation and **undetected ChromeDriver** to control a real browser, avoiding
Instagram’s bot detection entirely.

---

## ✨ Features

- **Owner / Target / Unknown behaviour** – Alex gets sweet, submissive replies; targets
  get ragebait; strangers are ignored unless triggered.
- **Dynamic targeting** – Alex can add a target on the fly with `target @username`.
- **Threaded replies** – all messages are sent as a reply to the last message.
- **Human‑like persona** – typos, slang, text emoticons, and a deep backstory.
- **Consistent memory** – facts about herself are saved and reused, never contradicted.
- **No private API** – uses the real Instagram web interface via Selenium.
- **Persistent login** – logs in once manually, then re‑uses the browser profile.

---

## 🛠️ Tech Stack

Python 3.10+, Selenium, undetected-chromedriver, Groq API (llama-3.3-70b-versatile),
python-dotenv, JSON / plain‑text file storage.

---

## 🚀 Quick Start

1. **Clone the repo**
   ```bash
   git clone https://github.com/lelextb/Instagram-Chatbot.git
   cd Instagram-Chatbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your `.env` file**
   Copy the example and fill in your real credentials:
   ```bash
   cp .env.example .env
   nano .env   # or use your favourite editor
   ```

4. **Prepare your targets**
   Create a `targets.txt` file with one Instagram username per line (the bot will also
   add dynamic targets later).

5. **Run the bot**
   ```bash
   python bot.py
   ```
   On first run, a Chrome window opens. **Log into Instagram manually**, then navigate
   to your group chat and press **Enter** in the terminal. The bot saves your session
   and the chat URL – future runs are fully automatic.

---

## ⚙️ Commands (for the owner)

| Command | Effect |
|---------|--------|
| `say hello` | Bot sends “hello” |
| `status` | Bot replies “I'm online, Alex!” |
| `ragebait you suck` | Bot generates a ragebait reply to “you suck” |
| `target @username` | Adds the user to the target list (from now on, their messages get ragebait) |

---

## 📁 File Structure

```
Instagram-Chatbot/
├── bot.py                  # Main bot script
├── .env.example            # Safe template for your .env file
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .gitignore
├── targets.txt             # Static target list 
├── dynamic_targets.txt     # Runtime added targets 
├── my_information.txt      # Lina's self‑story 
├── processed_fingerprints.json  # Message deduplication 
├── targets_profile.json    # Cached Instagram profiles 
├── chrome_profile/         # Browser session 
└── bot.log                 # Log file 
```

---

## 🔒 Privacy & Safety

- This bot is for **educational / entertainment purposes only**.
- Do not use it to harass real people. Respect Instagram’s Terms of Service.
- The bot mimics human behaviour – you are responsible for its actions.

---

## 📝 License

MIT – do whatever you want, but don’t be evil.
