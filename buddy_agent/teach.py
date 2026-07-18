#!/usr/bin/env python3
"""Buddy — an offline teaching agent for kids, powered by Llama 3.1 8B via Ollama.

Usage:
  python3 teach.py                          # pick a subject, learn from Buddy's own knowledge
  python3 teach.py --subject "space"        # jump straight into a subject
  python3 teach.py --pdf my_book.pdf        # Buddy teaches from your PDF first
"""

import argparse
import sys

import ollama

import prompts
from tutor import Tutor

DEFAULT_MODEL = "llama3.1"

BANNER = r"""
  ____            _     _
 | __ ) _   _  __| | __| |_   _
 |  _ \| | | |/ _` |/ _` | | | |
 | |_) | |_| | (_| | (_| | |_| |
 |____/ \__,_|\__,_|\__,_|\__, |
   your friendly teacher  |___/
"""


def check_model(client: ollama.Client, model: str) -> None:
    """Fail fast with a helpful message if Ollama or the model is missing."""
    try:
        models = [m.model for m in client.list().models]
    except Exception:
        sys.exit(
            "❌ I can't reach Ollama. Is it running?\n"
            "   Start it with:  ollama serve\n"
            "   Install it from: https://ollama.com/download"
        )
    if not any(name == model or name.split(":")[0] == model for name in models):
        sys.exit(
            f"❌ The model '{model}' isn't downloaded yet.\n"
            f"   Download it once with:  ollama pull {model}\n"
            "   After that, everything runs fully offline."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline teaching agent for kids")
    parser.add_argument("--pdf", help="path to a PDF to teach from (book first, own knowledge as backup)")
    parser.add_argument("--subject", help="subject to teach (asked interactively if omitted)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--grade",
        default=prompts.DEFAULT_GRADE,
        choices=list(prompts.GRADE_LEVELS),
        help=f"student's class, adjusts Buddy's language (default: {prompts.DEFAULT_GRADE})",
    )
    args = parser.parse_args()

    print(BANNER)
    client = ollama.Client()
    check_model(client, args.model)

    subject = args.subject
    if not subject and not args.pdf:
        try:
            subject = input("📚 What should we learn about today? ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nBye bye! 👋")
    subject = subject or "anything you're curious about"

    tutor = Tutor(model=args.model, subject=subject, client=client, grade=args.grade)
    if args.pdf:
        try:
            tutor.load_pdf(args.pdf)
        except Exception as exc:
            sys.exit(f"❌ Couldn't read that PDF: {exc}")

    tutor.run()


if __name__ == "__main__":
    main()
