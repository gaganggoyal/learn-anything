"""The interactive tutor: chat loop, streaming replies, and commands."""

from __future__ import annotations

import os

import ollama

import prompts
from knowledge import KnowledgeBase

MAX_HISTORY_MESSAGES = 12  # user+assistant turns kept in context
CHAT_OPTIONS = {"num_ctx": 8192, "temperature": 0.6}

HELP_TEXT = """
Commands you can type any time:
  /next          - continue the lesson: I teach the next part of your book
  /quiz          - get a fun 3-question quiz
  /pdf <path>    - load a PDF book to learn from (I teach from it first)
  /nopdf         - put the book away and use my own knowledge again
  /topic <name>  - switch to a new subject
  /help          - show this help
  quit / exit    - say goodbye
"""


class Tutor:
    def __init__(
        self,
        model: str,
        subject: str,
        client: ollama.Client | None = None,
        grade: str = prompts.DEFAULT_GRADE,
    ):
        self.model = model
        self.subject = subject
        self.grade = grade if grade in prompts.GRADE_LEVELS else prompts.DEFAULT_GRADE
        self.client = client or ollama.Client()
        self.kb: KnowledgeBase | None = None
        self.history: list[dict] = []  # raw user/assistant turns, no injected context
        self.lesson_pos = 0  # how far through the book's chunks the lesson has gone

    # ----- knowledge base -------------------------------------------------

    def load_pdf(self, path: str) -> None:
        path = os.path.expanduser(path.strip().strip("'\""))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Can't find a file at: {path}")
        print("📖 Reading your book, one moment...")
        self.kb = KnowledgeBase(self.client, path)
        self.history = []  # fresh start: old chat may contain outside knowledge
        self.lesson_pos = 0
        print(
            f"✅ Loaded {os.path.basename(path)} "
            f"({self.kb.page_count} pages, using {self.kb.mode}). "
            "I'll teach from this book, and tell you when an answer comes from outside it!"
        )

    def unload_pdf(self) -> None:
        self.kb = None
        self.history = []
        self.lesson_pos = 0
        print("📚 Book closed! I'm back to using my own knowledge.")

    def next_lesson(self, n: int = 2) -> list[str] | None:
        """The next `n` unread chunks of the book, in order. None when finished."""
        if not self.kb or self.lesson_pos >= len(self.kb.chunks):
            return None
        chunks = self.kb.chunks[self.lesson_pos : self.lesson_pos + n]
        self.lesson_pos += n
        return chunks

    def start_overview(self) -> list[str]:
        """Chunks for the 'movie trailer' + first topic; marks the first chunk taught."""
        assert self.kb is not None
        self.lesson_pos = max(self.lesson_pos, 1)
        return self.kb.sample_across()

    # ----- prompt assembly ------------------------------------------------

    def _system_prompt(self) -> str:
        audience = prompts.GRADE_LEVELS[self.grade]
        if self.kb:
            return prompts.PDF_TUTOR_SYSTEM.format(audience=audience)
        return prompts.TUTOR_SYSTEM.format(subject=self.subject, audience=audience)

    def _build_messages(self, user_text: str, context_chunks: list[str] | None) -> list[dict]:
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(self.history[-MAX_HISTORY_MESSAGES:])
        if self.kb:
            chunks = context_chunks if context_chunks is not None else self.kb.retrieve(user_text)
            turn = prompts.PDF_TURN_TEMPLATE.format(
                context="\n\n---\n\n".join(chunks), question=user_text
            )
        else:
            turn = user_text
        messages.append({"role": "user", "content": turn})
        return messages

    # ----- talking to the model -------------------------------------------

    def reply_stream(self, user_text: str, context_chunks: list[str] | None = None):
        """Yield the reply token by token, then record the turn in history."""
        messages = self._build_messages(user_text, context_chunks)
        reply_parts: list[str] = []
        stream = self.client.chat(
            model=self.model, messages=messages, stream=True, options=CHAT_OPTIONS
        )
        for part in stream:
            token = part["message"]["content"]
            reply_parts.append(token)
            yield token
        # History stores the plain question, not the injected study material,
        # so old retrieved chunks don't pile up in the context window.
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": "".join(reply_parts)})

    def ask(self, user_text: str, context_chunks: list[str] | None = None) -> str:
        """Send one message and stream the reply to the terminal."""
        print("\n🧸 Buddy: ", end="", flush=True)
        reply_parts: list[str] = []
        for token in self.reply_stream(user_text, context_chunks):
            reply_parts.append(token)
            print(token, end="", flush=True)
        print("\n")
        return "".join(reply_parts)

    # ----- main loop ------------------------------------------------------

    def run(self) -> None:
        if self.kb:
            self.ask(prompts.OVERVIEW_REQUEST, context_chunks=self.start_overview())
        else:
            print(f"\n🧸 Buddy: Hi friend! Today we can learn about {self.subject}. "
                  "What would you like to know? (Type /help to see my tricks!)\n")

        while True:
            try:
                user_text = input("🙋 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n🧸 Buddy: Bye bye! Keep being curious! 👋")
                return
            if not user_text:
                continue

            lower = user_text.lower()
            if lower in {"quit", "exit", "bye", "/quit", "/exit"}:
                print("\n🧸 Buddy: Bye bye! You did great today! 🌟")
                return
            if lower == "/help":
                print(HELP_TEXT)
                continue
            if lower.startswith("/pdf"):
                path = user_text[4:].strip()
                if not path:
                    print("Tell me where the book is, like: /pdf ~/Downloads/science.pdf")
                    continue
                try:
                    self.load_pdf(path)
                    self.ask(prompts.OVERVIEW_REQUEST, context_chunks=self.start_overview())
                except Exception as exc:
                    print(f"😕 I couldn't read that book: {exc}")
                continue
            if lower == "/next":
                if not self.kb:
                    print("Load a book first, like: /pdf ~/Downloads/science.pdf")
                    continue
                chunks = self.next_lesson()
                if chunks is None:
                    print(f"\n🧸 Buddy: {prompts.BOOK_DONE_MESSAGE}\n")
                    continue
                self.ask(prompts.LESSON_REQUEST, context_chunks=chunks)
                continue
            if lower == "/nopdf":
                self.unload_pdf()
                continue
            if lower.startswith("/topic"):
                new_topic = user_text[6:].strip()
                if not new_topic:
                    print("Tell me the new subject, like: /topic dinosaurs")
                    continue
                self.subject = new_topic
                self.history = []
                print(f"🎨 New subject: {self.subject}! Ask me anything about it.")
                continue
            if lower == "/quiz":
                if self.kb:
                    self.ask(prompts.QUIZ_REQUEST, context_chunks=self.kb.sample_across())
                else:
                    self.ask(prompts.QUIZ_REQUEST)
                continue

            try:
                self.ask(user_text)
            except Exception as exc:
                print(f"\n😕 Something went wrong talking to the model: {exc}")
                print("Is Ollama still running? Try: ollama serve")
