#!/usr/bin/env python3
"""Learn Anything — the website for the Buddy offline teaching agent.

The agent itself (tutor, prompts, PDF knowledge base) lives in a separate
project: workspace/agents/offline_teaching_agent. This server only adds the
web layer on top of it.

Run:
  python3 server.py                 # http://localhost:8000
  python3 server.py --host 0.0.0.0  # reachable by other devices (classroom LAN)

Everything still runs fully offline: the browser talks to this server,
and this server talks to Ollama on the same machine.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import threading
import time
import uuid

import ollama
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Where the agent code lives. A copy ships in ./buddy_agent so the download
# is self-contained, but a live dev checkout next door wins over the bundled
# copy, and BUDDY_AGENT_DIR overrides everything.
_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENT_CANDIDATES = [
    os.environ.get("BUDDY_AGENT_DIR"),
    os.path.normpath(os.path.join(_HERE, "..", "agents", "offline_teaching_agent")),
    os.path.join(_HERE, "buddy_agent"),
]
AGENT_DIR = next((d for d in _AGENT_CANDIDATES
                  if d and os.path.isfile(os.path.join(d, "tutor.py"))), _HERE)
sys.path.insert(0, AGENT_DIR)
try:
    import prompts
    from tutor import Tutor
except ImportError:
    sys.exit(
        f"❌ Couldn't find the Buddy agent code in: {AGENT_DIR}\n"
        "   That folder must contain tutor.py, prompts.py, and knowledge.py.\n"
        "   If it lives somewhere else, point me to it:\n"
        "     BUDDY_AGENT_DIR=/path/to/offline_teaching_agent python3 server.py"
    )

DEFAULT_MODEL = os.environ.get("BUDDY_MODEL", "llama3.1")
MAX_SESSIONS = 100          # oldest session is dropped beyond this
SESSION_TTL = 6 * 3600      # seconds of inactivity before a session expires
MAX_PDF_BYTES = 50 * 1024 * 1024

STATIC_DIR = os.path.join(_HERE, "static")

app = FastAPI(title="Learn Anything — Buddy, the offline teaching agent")


class Session:
    def __init__(self, tutor: Tutor):
        self.tutor = tutor
        self.pdf_name: str | None = None
        self.last_used = time.time()
        self.lock = threading.Lock()  # one reply at a time per session


SESSIONS: dict[str, Session] = {}
_sessions_lock = threading.Lock()


def _prune_sessions() -> None:
    now = time.time()
    stale = [sid for sid, s in SESSIONS.items() if now - s.last_used > SESSION_TTL]
    for sid in stale:
        SESSIONS.pop(sid, None)
    while len(SESSIONS) > MAX_SESSIONS:
        oldest = min(SESSIONS, key=lambda sid: SESSIONS[sid].last_used)
        SESSIONS.pop(oldest, None)


def _get_session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session expired. Please start a new lesson.")
    session.last_used = time.time()
    return session


def _pick_model() -> str:
    """Choose the model to teach with. The UI never sees or chooses this:
    set BUDDY_MODEL to force one, otherwise prefer DEFAULT_MODEL, otherwise
    the first pulled chat model (embedding models are skipped)."""
    try:
        names = sorted({m.model.split(":")[0] for m in ollama.Client().list().models})
    except Exception:
        return DEFAULT_MODEL
    if DEFAULT_MODEL in names:
        return DEFAULT_MODEL
    chat_models = [n for n in names if "embed" not in n.lower()]
    return chat_models[0] if chat_models else DEFAULT_MODEL


# ----- pages ----------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# The service worker must be served from the site root so its scope covers
# the whole app, and the manifest lives beside it for the same reason.
@app.get("/sw.js")
def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"),
                        media_type="application/manifest+json")


# ----- api ------------------------------------------------------------------

@app.get("/api/health")
def health():
    """Is Ollama up? (Which model Buddy uses is deliberately not exposed.)"""
    try:
        ollama.Client().list()
        return {"ok": True, "grades": list(prompts.GRADE_LEVELS)}
    except Exception:
        return {"ok": False, "grades": list(prompts.GRADE_LEVELS)}


class NewSessionBody(BaseModel):
    subject: str = "anything you're curious about"
    grade: str = prompts.DEFAULT_GRADE


@app.post("/api/session")
def new_session(body: NewSessionBody):
    with _sessions_lock:
        _prune_sessions()
        session_id = uuid.uuid4().hex
        tutor = Tutor(model=_pick_model(), subject=body.subject.strip() or "anything you're curious about",
                      grade=body.grade)
        SESSIONS[session_id] = Session(tutor)
    return {"session_id": session_id, "subject": tutor.subject, "grade": tutor.grade}


class SettingsBody(BaseModel):
    session_id: str
    subject: str | None = None
    grade: str | None = None


@app.post("/api/settings")
def update_settings(body: SettingsBody):
    session = _get_session(body.session_id)
    tutor = session.tutor
    if body.subject is not None and body.subject.strip() and body.subject.strip() != tutor.subject:
        tutor.subject = body.subject.strip()
        tutor.history = []  # same as /topic in the CLI: fresh start for a new subject
    if body.grade is not None and body.grade in prompts.GRADE_LEVELS:
        tutor.grade = body.grade
    return {"subject": tutor.subject, "grade": tutor.grade}


@app.post("/api/upload")
def upload_pdf(session_id: str = Form(...), file: UploadFile = File(...)):
    session = _get_session(session_id)
    name = os.path.basename(file.filename or "book.pdf")
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    # The knowledge base keeps the text in memory, so the file itself is only
    # needed for a moment.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
            size = 0
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise HTTPException(status_code=400, detail="That PDF is too big (max 50 MB).")
                tmp.write(chunk)
        with session.lock:
            session.tutor.load_pdf(tmp_path)
            session.pdf_name = name
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"I couldn't read that book: {exc}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    kb = session.tutor.kb
    return {"name": name, "pages": kb.page_count, "mode": kb.mode}


class SessionOnlyBody(BaseModel):
    session_id: str


@app.post("/api/close-pdf")
def close_pdf(body: SessionOnlyBody):
    session = _get_session(body.session_id)
    with session.lock:
        session.tutor.unload_pdf()
        session.pdf_name = None
    return {"ok": True}


OVERVIEW_CLOSER = ("Whenever you're ready, press ▶ Continue lesson and I'll teach you "
                   "the next part — or just ask me anything! 🌟")


def _drop_trailing_questions(text: str) -> str:
    """Remove question-sentences from the end of a reply.

    Small local models keep tacking a check-question onto the book overview no
    matter what the prompt says, so the first message after an upload is
    cleaned up here instead.
    """
    t = text.rstrip()
    while True:
        parts = re.split(r"(?<=[.!?…])(\s+)", t)  # sentences + their separators
        if len(parts) < 3 or not parts[-1].rstrip().endswith("?"):
            break
        t = "".join(parts[:-2]).rstrip()
    return t


class ChatBody(BaseModel):
    session_id: str
    message: str = ""
    action: str = "chat"  # "chat" | "quiz" | "overview" | "lesson"


@app.post("/api/chat")
def chat(body: ChatBody):
    session = _get_session(body.session_id)
    tutor = session.tutor

    if body.action == "quiz":
        text = prompts.QUIZ_REQUEST
        chunks = tutor.kb.sample_across() if tutor.kb else None
    elif body.action == "overview":
        if not tutor.kb:
            raise HTTPException(status_code=400, detail="No book is loaded.")
        text = prompts.OVERVIEW_REQUEST
        chunks = tutor.start_overview()
    elif body.action == "lesson":
        if not tutor.kb:
            raise HTTPException(status_code=400, detail="No book is loaded.")
        chunks = tutor.next_lesson()
        if chunks is None:  # the whole book has been taught
            return StreamingResponse(iter([prompts.BOOK_DONE_MESSAGE]),
                                     media_type="text/plain; charset=utf-8")
        text = prompts.LESSON_REQUEST
    else:
        text = body.message.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Say something first!")
        chunks = None

    def token_stream():
        with session.lock:
            try:
                if body.action == "overview":
                    # Buffered, not streamed: the first message after an upload is
                    # cleaned so the lesson never starts by quizzing the student.
                    full = "".join(tutor.reply_stream(text, context_chunks=chunks))
                    cleaned = _drop_trailing_questions(full) or full
                    cleaned = f"{cleaned}\n\n{OVERVIEW_CLOSER}"
                    tutor.history[-1]["content"] = cleaned  # keep history in sync
                    yield cleaned
                else:
                    yield from tutor.reply_stream(text, context_chunks=chunks)
            except Exception as exc:
                yield (f"\n\n😕 Something went wrong talking to the model: {exc}\n"
                       "Is Ollama still running on the teacher's computer?")

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# Icons and any other assets referenced by the page.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="Learn Anything web server (Buddy)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="use 0.0.0.0 to let other devices on your network connect")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"📂 Agent code: {AGENT_DIR}")
    print(f"🧸 Buddy is ready! Open http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
