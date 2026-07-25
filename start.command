#!/usr/bin/env bash
# Bewerbungsassistent starten - macOS und Linux.
#
# macOS: doppelklicken. Beim ersten Mal meldet sich eventuell die
#        Sicherheitsabfrage - dann Rechtsklick > Oeffnen waehlen.
# Linux: ./start.command  (oder aus dem Dateimanager ausfuehren)

cd "$(dirname "$0")" || exit 1

echo ""
echo "  Bewerbungsassistent"
echo "  ==================="
echo ""

# --- Python finden -----------------------------------------------------------
PY=""
for kandidat in python3 python; do
  if command -v "$kandidat" >/dev/null 2>&1; then
    if "$kandidat" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$kandidat"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "  Python 3 wurde nicht gefunden."
  echo "  Bitte einmalig installieren: https://www.python.org/downloads/"
  echo ""
  read -r -p "  Mit Enter schliessen." _
  exit 1
fi

# --- Abhaengigkeit sicherstellen ---------------------------------------------
# Nur beim ersten Start noetig; danach ist der Aufruf still und schnell.
if ! "$PY" -c "import anthropic" >/dev/null 2>&1; then
  echo "  Einmalige Einrichtung laeuft (das dauert einen Moment) …"
  "$PY" -m pip install --quiet --user anthropic || {
    echo ""
    echo "  Die Installation ist fehlgeschlagen. Bitte von Hand ausfuehren:"
    echo "      $PY -m pip install anthropic"
    echo ""
    read -r -p "  Mit Enter schliessen." _
    exit 1
  }
  echo "  Fertig eingerichtet."
  echo ""
fi

# --- Chromium/Chrome pruefen (fuer die PDF-Ausgabe) --------------------------
if ! command -v chromium >/dev/null 2>&1 \
   && ! command -v google-chrome >/dev/null 2>&1 \
   && [ ! -d "/Applications/Google Chrome.app" ] \
   && [ -z "$CHROMIUM_BIN" ]; then
  echo "  Hinweis: Chrome oder Chromium wurde nicht gefunden."
  echo "  Alles funktioniert, nur die PDF-Ausgabe braucht einen davon."
  echo ""
fi

exec "$PY" webapp/server.py "$@"
