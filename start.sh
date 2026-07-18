#!/usr/bin/env bash
# One-command start for the Learn Anything site (Buddy).
#
#   ./start.sh                 # serve to the whole classroom network on port 8000
#   ./start.sh --port 9000     # any extra flags are passed to server.py
#
# First run sets up the Python environment; every run makes sure Ollama
# (Buddy's brain) is awake before starting the site.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "🔧 First run: setting up the Python environment…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

if ! curl -sf http://localhost:11434/api/version >/dev/null 2>&1; then
  if command -v ollama >/dev/null 2>&1; then
    echo "🧠 Waking up Ollama…"
    (ollama serve >/dev/null 2>&1 &)
    for _ in $(seq 1 20); do
      curl -sf http://localhost:11434/api/version >/dev/null 2>&1 && break
      sleep 0.5
    done
  else
    echo "⚠️  Ollama isn't installed. Get it from https://ollama.com then run:"
    echo "     ollama pull llama3.1:8b"
    echo "   Starting the site anyway — it will show 'Buddy is asleep' until then."
  fi
fi

exec ./.venv/bin/python server.py --host 0.0.0.0 "$@"
