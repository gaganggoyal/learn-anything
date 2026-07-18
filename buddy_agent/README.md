# Buddy — Offline Teaching Agent for Kids 🧸

A friendly tutor that runs **100% offline** on your own computer, powered by the
**Llama 3.1 8B** model through [Ollama](https://ollama.com). Buddy explains any
subject in easy, simple language that young kids (around 6–10 years old) can
understand — short sentences, everyday examples, and a tiny check-question after
every explanation.

It has two teaching modes:

| Mode | When | What Buddy does |
|---|---|---|
| **PDF mode** | You give a PDF (`--pdf book.pdf` or `/pdf` in chat) | Teaches from that PDF first. If the answer isn't in the book, Buddy says so — *"that's not in your book, but I know about it!"* — and then answers from its own knowledge. |
| **Own knowledge** | No PDF given | Teaches any subject from the model's own knowledge. |

This project is the **agent only** (a terminal chat plus importable Python
modules). A student-friendly website that runs on top of it lives in the
separate `learn_anything` project, which imports `tutor.py` from here.

---

## 1. Setup (needs internet only once)

After these steps, everything runs **fully offline** — no internet, no API keys,
no data leaving your computer.

**Step 1 — Install Ollama** (the app that runs AI models locally):
https://ollama.com/download

**Step 2 — Download the Llama 3.1 8B model** (~4.9 GB, one time only):

```bash
ollama pull llama3.1:8b
```

**Step 3 — Download the embedding model** (~270 MB, one time only):

```bash
ollama pull nomic-embed-text
```

This small model turns text into numbers ("embeddings") so Buddy can find the
right pages of your PDF by **meaning**, not just matching words. Example: if
your book says "how plants make their own food" and you ask "what is
photosynthesis?", embeddings still find the right page.
*(If you skip this step, Buddy still works — it automatically falls back to a
built-in keyword search called BM25, which needs no download at all.)*

**Step 4 — Install the two Python packages** (in a virtual environment, so
nothing touches your system Python):

```bash
cd offline_teaching_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The only packages are `ollama` (talks to the local model) and `pypdf` (reads
PDF files).

---

## 2. How to use it

Always activate the virtual environment first:

```bash
source .venv/bin/activate
```

**Learn from Buddy's own knowledge:**

```bash
python3 teach.py                          # Buddy asks what you want to learn
python3 teach.py --subject "the solar system"
```

**Learn ONLY from your PDF** (textbook, class notes, a story...):

```bash
python3 teach.py --pdf ~/Downloads/science_book.pdf

# Try it right now with the included 3-page sample book about the water cycle:
python3 teach.py --pdf sample_book.pdf
```

When a PDF is loaded, Buddy first gives a fun "movie trailer" overview of the
book, then answers questions from what's inside it. If a question goes beyond
the book, Buddy says so and answers from its own knowledge instead.

**Use a different model or class level:**

```bash
python3 teach.py --model llama3.2
python3 teach.py --grade class-8        # preschool | class-1 | class-2 | ... | class-12
```

### Commands during a lesson

Type these any time in the chat:

| Command | What it does |
|---|---|
| `/quiz` | A fun 3-question quiz on what you're learning (in PDF mode, questions come only from the book) |
| `/pdf <path>` | Load a PDF book mid-chat — Buddy then teaches only from it |
| `/nopdf` | Close the book and go back to Buddy's own knowledge |
| `/topic <name>` | Switch to a new subject, e.g. `/topic dinosaurs` |
| `/help` | Show all commands |
| `quit` / `exit` / `bye` | Say goodbye |

### Example session

```
python3 teach.py --pdf sample_book.pdf

🧸 Buddy: Yay! Your book is like an adventure movie about water! ...

🙋 You: What is evaporation?
🧸 Buddy: Evaporation is when the sun heats up water in oceans, lakes, and
rivers, and it turns into an invisible gas called water vapor! ...

🙋 You: Who was the first president of America?
🧸 Buddy: Hmm, that's not in your book, but I know about it! The first
president of America was George Washington. ...
```

---

## 3. How we made it

The whole agent is 4 small Python files. Here is what each one does and how
they fit together. (The `learn_anything` website project plugs into the same
place `teach.py` does: it imports `Tutor` and streams from `reply_stream()`.)

```
you type a question
        │
        ▼
   teach.py      starts the app, checks Ollama + model are ready
        │
        ▼
   tutor.py      the tutor brain: history, prompt assembly, streaming answers
        │
        ├── no PDF?  → question goes straight to the model
        │
        └── PDF loaded?
                │
                ▼
          knowledge.py   finds the 4 most relevant pieces of the PDF
                │        and attaches them to your question
                ▼
          prompts.py     wraps everything in the "kid teacher" instructions
                │
                ▼
        Llama 3.1 8B (running locally in Ollama) → streamed answer
```

### `teach.py` — the front door

- Parses command-line options (`--pdf`, `--subject`, `--model`).
- Before starting, calls Ollama's model list to **fail fast with a helpful
  message** if Ollama isn't running (`ollama serve`) or the model isn't
  downloaded (`ollama pull llama3.1`), instead of crashing mid-chat.

### `prompts.py` — the teacher's personality

The "training" of the agent is done through **system prompts** (instructions
the model reads before every conversation). There are two:

- **`TUTOR_SYSTEM`** (own-knowledge mode): use very simple words and short
  sentences, one idea at a time, fun examples from everyday life (toys, food,
  animals), keep answers 3–6 sentences, always end with one tiny
  check-question, never say "wrong" — say "Good try!" and re-explain more
  simply, and keep everything kid-safe.
- **`PDF_TUTOR_SYSTEM`** (PDF mode): the same personality, **plus strict
  rules**: answer from the study material attached to each message when the
  answer is there. If it isn't, first say *"Hmm, that's not in your book, but
  I know about it!"* and then answer from the model's own knowledge — so the
  kid always knows whether an answer came from the book or from Buddy. It
  also tells the model to call it "your book" and never mention technical
  words like "chunks" or "PDF" to the kid.

This is why no fine-tuning/training of the model itself is needed — Llama 3.1
8B is already capable; the prompts shape *how* it teaches.

### `knowledge.py` — the PDF brain (a mini RAG pipeline)

An 8B model can't just "read" a whole textbook for every question, so we use
**RAG** (Retrieval-Augmented Generation): find the few relevant pieces first,
then let the model answer from only those pieces.

1. **Extract** — `pypdf` pulls the raw text out of every page of the PDF.
   (Scanned/image-only PDFs have no text, so they're detected and rejected
   with a clear message.)
2. **Chunk** — the text is split into overlapping pieces of ~900 characters
   (150 characters of overlap so a sentence cut at a boundary still appears
   whole in the next chunk). Splitting prefers paragraph boundaries.
3. **Index** — each chunk is turned into an embedding vector using
   `nomic-embed-text` via Ollama. If that model isn't installed, we build a
   **BM25** keyword index instead (implemented in pure Python right in this
   file — no extra dependency).
4. **Retrieve** — when you ask something, your question is scored against
   every chunk (cosine similarity for embeddings, BM25 score for keywords)
   and the **top 4 chunks** are attached to your question as "STUDY
   MATERIAL".
5. For overviews and quizzes there's no real "question" to search with, so
   `sample_across()` instead picks chunks spread evenly through the book
   (beginning, middle, end) so the whole book is covered.

### `tutor.py` — the conversation

- **Chat loop** — reads your input, handles the `/commands`, and sends
  everything else to the model.
- **Streaming** — answers print word-by-word as the model generates them, so
  it feels alive instead of freezing for 20 seconds.
- **Smart history** — the conversation history keeps your **plain questions**,
  not the big study-material blocks that were attached to them. Otherwise
  retrieved book text would pile up and overflow the model's context window
  (set to 8192 tokens). Only the last 12 messages are sent each turn.
- **Clean mode switches** — loading or closing a PDF clears the history, so
  outside knowledge from an earlier chat can't leak into PDF-only answers.

### Design choices, briefly

- **Ollama** instead of raw model files: it handles downloading, GPU/CPU
  setup, and serving the model with one command, and works the same on
  Mac/Linux/Windows.
- **Prompting instead of fine-tuning**: shaping behavior with a system prompt
  is free, instant, and easy to tweak (just edit `prompts.py`); fine-tuning an
  8B model would need a GPU cluster and a dataset for marginal gain here.
- **Only 2 dependencies**: retrieval math (cosine similarity, BM25) is a few
  lines of pure Python, so there's no numpy/langchain/vector-database to
  install or break.

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| `I can't reach Ollama` | Start it: `ollama serve` (or open the Ollama app) |
| `The model 'llama3.1' isn't downloaded` | `ollama pull llama3.1:8b` |
| First answer is very slow | Normal — the model is loading into memory; later answers are faster |
| `No readable text found in ...` | The PDF is scanned images, not text — run OCR on it first |
| Buddy uses keyword search for PDFs | Run `ollama pull nomic-embed-text` once to enable semantic search |
| Want a smarter/faster model | Any Ollama model works: `python3 teach.py --model <name>` |
