#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then echo 'Python 3 fehlt. Bitte Python 3 von python.org oder über Homebrew installieren.'; read -r -p 'Enter zum Beenden ...' _; exit 1; fi
if [[ ! -f .venv/bin/python ]]; then python3 -m venv .venv; fi
if [[ ! -f .venv/.requirements-installed ]] || [[ requirements.txt -nt .venv/.requirements-installed ]]; then
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.requirements-installed
fi
exec .venv/bin/python main.py "$@"