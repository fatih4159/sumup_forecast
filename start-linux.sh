#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ ! -f main.py ]]; then echo 'Fehler: main.py fehlt.' >&2; exit 1; fi
if ! command -v python3 >/dev/null 2>&1; then echo 'Python 3 fehlt. Auf Bazzite ggf. mit distrobox/toolbox eine Python-Umgebung verwenden.' >&2; exit 1; fi
if [[ ! -f .venv/bin/python ]]; then
  echo 'Erstelle virtuelle Python-Umgebung ...'
  python3 -m venv .venv || { echo 'venv konnte nicht erstellt werden. Python mit venv-Unterstützung installieren.' >&2; exit 1; }
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then .venv/bin/python -m ensurepip --upgrade; fi
if [[ ! -f .venv/.requirements-installed ]] || [[ requirements.txt -nt .venv/.requirements-installed ]]; then
  echo 'Installiere Abhängigkeiten ...'
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.requirements-installed
fi
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
echo 'Starte ForeCast ...'
exec .venv/bin/python main.py "$@"