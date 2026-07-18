# Learn Anything 🧸 — Buddy, the offline AI teacher

A friendly website where students pick their **class** (Preschool–Class 12),
pick a **subject** — or upload their own **PDF textbook** — and learn by
chatting with **Buddy**, an AI tutor that runs **100% on your own computer**.
No internet needed while teaching, no accounts, no fees, and nothing a
student types ever leaves the room.

Built for classrooms with one computer: the teacher runs Buddy, the whole
class connects from their own phones/tablets over the school Wi-Fi.

---

## ✅ What you NEED

| Requirement | Details |
|---|---|
| **A computer for the teacher** | Windows, Mac, or Linux. **8 GB RAM minimum** (Buddy will think slowly), **16 GB recommended** (comfortable). ~10 GB free disk space. |
| **[Ollama](https://ollama.com)** (free) | The engine that runs Buddy's AI brain locally. One-time install. |
| **The AI model** (free) | After installing Ollama, run once: `ollama pull llama3.1:8b` (~5 GB download). |
| **Python 3.10+** | Macs and most Linux systems already have it. **Windows:** install from [python.org](https://www.python.org/downloads/) and tick **"Add Python to PATH"**. |
| **Internet — ONCE** | Only for the downloads above. After setup, Buddy works with the internet cable unplugged, forever. |

## ❌ What you DON'T need

- **No internet while teaching** — everything runs on the teacher's computer.
- **No accounts, API keys, subscriptions, or payments** — ever.
- **No GPU / gaming computer** — a normal office computer works (a GPU just makes Buddy faster).
- **No installation on student devices** — students only need a web browser.
  They can optionally "Add to Home Screen" to get a Buddy app icon.
- **No student data collection** — chats live in the computer's memory and
  vanish when the lesson ends. Nothing is stored, nothing is sent anywhere.
- **Optional:** `ollama pull nomic-embed-text` (~270 MB) makes searching inside
  uploaded PDF books smarter. Without it, Buddy automatically falls back to a
  built-in keyword search — everything still works.

---

## 🚀 Setup (teacher, one time, ~15 minutes)

1. **Install Ollama** from [ollama.com](https://ollama.com) (Download → install like any app).
2. **Get the model** — open a terminal (Windows: press Start, type `cmd`) and run:
   ```
   ollama pull llama3.1:8b
   ```
   Optional but recommended: `ollama pull nomic-embed-text`
3. **Download this project** — green **Code** button above → **Download ZIP** → unzip anywhere
   (or `git clone` if you know git).
4. **Start Buddy:**
   - **Windows:** double-click **`start.bat`**
   - **Mac / Linux:** double-click **`start.sh`** (or run `./start.sh` in a terminal)

   The first start sets things up and takes a minute. When you see
   *"🧸 Buddy is ready!"*, open **http://localhost:8000**.

> **Mac note:** if macOS blocks the script, right-click → Open → Open anyway.
> **Windows note:** if SmartScreen appears, click "More info" → "Run anyway".

## 🏫 Daily classroom use

1. Double-click `start.bat` / `start.sh` and leave that window open.
2. Find the teacher computer's address on the local network:
   - Windows: `ipconfig` → "IPv4 Address" (e.g. `192.168.1.5`)
   - Mac: `ipconfig getifaddr en0`
3. Students on the **same Wi-Fi** open `http://192.168.1.5:8000` (your IP) in
   any browser. Each student gets their own private lesson — own class,
   subject, book, and chat.
4. That's it. No internet required — only the local network.

If student devices can't connect, allow port 8000 through the teacher
computer's firewall.

**Try it without a class:** there's a tiny `buddy_agent/sample_book.pdf` you
can upload to see the book-teaching flow.

## 📱 On the page

- **🎓 Class** — Preschool/KG to Class 12. Buddy changes how simply (or how
  deeply) he explains based on this.
- **📚 Subject** — Science, Maths, English, EVS, GK, Space, Animals, Story
  Time, or type your own.
- **📖 Upload a PDF** — Buddy gives a fun "movie trailer" of the book, then
  teaches it part by part (**▶ Continue lesson**), and always says when an
  answer comes from outside the book.
- **🎯 Quiz me!** — 3 easy questions about what was just taught. Buddy only
  asks things he has already clearly explained — answers are always in the
  lesson, kids never have to guess.
- **🔄 New lesson** — fresh start.

On phones, these controls are behind the **⚙️** button. Students can install
the site as an app: **"Add to Home Screen"** (iPhone/iPad Safari) or
**"Install app"** (Android Chrome).

## 🧠 About the model (hidden from students)

Students never see or choose the AI model. The server picks automatically:
`llama3.1` if you pulled it, otherwise the first chat model in Ollama.

- **Slow computer (8 GB RAM)?** Use a smaller, faster model:
  ```
  ollama pull llama3.2:3b
  BUDDY_MODEL=llama3.2:3b ./start.sh
  ```
  (Windows: `set BUDDY_MODEL=llama3.2:3b` then run `start.bat`.)
- Any chat model in Ollama works the same way via `BUDDY_MODEL`.

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| Red "Buddy's brain isn't running" banner | Start Ollama (`ollama serve`, or just open the Ollama app) and refresh |
| Buddy errors about the model | `ollama pull llama3.1:8b`, or set `BUDDY_MODEL` to a model you have |
| Students can't open the site | Same Wi-Fi? Right IP? Port 8000 allowed through the firewall? |
| Answers are very slow | Computer has too little RAM — try the `llama3.2:3b` model (see above) |
| Windows: "Python is not installed" | Install from python.org **with "Add Python to PATH" ticked**, reopen `start.bat` |
| UI changes don't show after an update | The page is cached — hard-refresh (Ctrl+Shift+R), or bump `CACHE` in `static/sw.js` |

---

## 👩‍💻 For developers

```
learn_anything/
├── server.py            FastAPI web layer: sessions, streaming chat, PDF upload
├── static/index.html    the whole UI — one hand-written file, no frameworks, no CDN
├── static/sw.js         service worker (PWA/offline shell; bump CACHE on UI changes)
├── static/manifest.webmanifest + static/icons/
├── buddy_agent/         bundled copy of the agent (tutor.py, prompts.py, knowledge.py)
├── start.sh / start.bat one-click launchers (create venv, wake Ollama, serve 0.0.0.0)
└── requirements.txt
```

- **Agent code resolution** (`server.py`): `BUDDY_AGENT_DIR` env var →
  a live dev checkout at `../agents/offline_teaching_agent` → the bundled
  `buddy_agent/`. So on a dev machine with the agent repo next door, edits
  there take effect immediately; the bundled copy is what teachers run.
  **If you change the agent, re-sync the bundle before pushing:**
  ```bash
  cp ../agents/offline_teaching_agent/{knowledge,prompts,tutor,teach}.py buddy_agent/
  ```
- **Sessions live in memory** — each browser tab gets its own `Tutor`; idle
  sessions expire after 6 h, capped at 100.
- **Streaming** — `/api/chat` streams plain text token by token.
- **Uploaded PDFs are read once and deleted** — only extracted text stays in memory.
- **PWA caveat** — browsers only run service workers on `localhost` or HTTPS,
  so on plain `http://<ip>:8000` the offline shell-caching is skipped (the
  site still works; it just needs the server reachable).
- Run manually: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python server.py`
