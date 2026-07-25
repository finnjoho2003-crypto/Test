#!/usr/bin/env bash
# Diagnose: sammelt alles, was zur Fehlersuche gebraucht wird.
#
#   bash pruefen.sh
#
# Gibt einen Block aus, der sich kopieren und weitergeben laesst. Enthaelt
# bewusst keine persoenlichen Daten und keinen API-Schluessel - nur ob einer
# vorhanden ist.

cd "$(dirname "$0")" || exit 1
PORT="${1:-8765}"

echo "===== BEWERBUNGSASSISTENT: PRUEFBERICHT ====="
echo

echo "-- Umgebung"
echo "   Codespace      : ${CODESPACES:-nein}"
echo "   Verzeichnis    : $(pwd)"
echo "   Python         : $(python3 --version 2>&1)"
echo

echo "-- Projektstand"
echo "   Branch         : $(git rev-parse --abbrev-ref HEAD 2>&1)"
echo "   Letzter Commit : $(git log -1 --format='%h %s' 2>&1)"
echo "   Aenderungen    : $(git status --porcelain 2>/dev/null | wc -l) Datei(en)"
echo

echo "-- Bausteine"
python3 -c "import anthropic; print('   anthropic      : vorhanden', anthropic.__version__)" 2>/dev/null \
  || echo "   anthropic      : FEHLT  ->  pip install anthropic"

if command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1 \
   || [ -n "${CHROMIUM_BIN:-}" ]; then
  echo "   Chromium       : vorhanden (nur fuer PDF noetig)"
else
  echo "   Chromium       : FEHLT  ->  sudo apt-get install -y chromium"
fi

if [ -f bewerbung/schluessel.txt ] || [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "   API-Schluessel : hinterlegt"
else
  echo "   API-Schluessel : noch keiner (die Oberflaeche fragt danach)"
fi
echo

echo "-- Laeuft der Dienst auf Port $PORT?"
if python3 - "$PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(3)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
then
  echo "   Port $PORT      : jemand lauscht"
  python3 - "$PORT" <<'PY'
import sys, urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with op.open(f"http://127.0.0.1:{sys.argv[1]}/api/uebersicht", timeout=6) as r:
        print(f"   Antwort        : HTTP {r.status} - der Assistent laeuft korrekt")
except Exception as fehler:
    print(f"   Antwort        : FEHLER - {fehler}")
PY
else
  echo "   Port $PORT      : niemand lauscht - der Assistent laeuft nicht"
  echo "                    Starten mit:  bash starten.sh"
fi

echo
echo "-- Letzte Startmeldungen"
if [ -f /tmp/bewerbung-start.log ]; then
  tail -n 15 /tmp/bewerbung-start.log | sed 's/^/   /'
else
  echo "   (keine - der Assistent wurde noch nicht ueber starten.sh gestartet)"
fi

echo
echo "===== ENDE ====="
