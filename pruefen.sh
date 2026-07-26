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

if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
  echo "-- Adresse zum Anklicken (NICHT 127.0.0.1)"
  echo "   https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  echo
fi

echo "-- Laeuft der Dienst auf Port $PORT?"
if python3 - "$PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(3)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
then
  echo "   Port $PORT      : jemand lauscht"
  # Auf welcher Adresse, ist im Codespace der entscheidende Punkt: Lauscht der
  # Dienst nur auf 127.0.0.1, sieht von innen alles richtig aus - HTTP 200,
  # keine Fehlermeldung -, waehrend die Weiterleitung von GitHub ihn nicht
  # erreicht und sich die Seite schlicht nicht oeffnet.
  # Ueber /proc statt ueber "ss": Das Werkzeug fehlt in schlanken Abbildern,
  # Python ist dagegen immer da - und ohne diese Angabe bliebe genau der Fall
  # unerkannt, der sich am schwersten erklaeren laesst.
  python3 - "$PORT" "${CODESPACES:-}" <<'PY'
import sys
port, im_codespace = int(sys.argv[1]), bool(sys.argv[2])
adressen = []
for datei, breite in (("/proc/net/tcp", 8), ("/proc/net/tcp6", 32)):
    try:
        zeilen = open(datei).read().splitlines()[1:]
    except OSError:
        continue
    for zeile in zeilen:
        teile = zeile.split()
        # 0A = LISTEN. Alles andere sind bestehende Verbindungen.
        if len(teile) < 4 or teile[3] != "0A":
            continue
        roh, hafen = teile[1].rsplit(":", 1)
        if int(hafen, 16) != port:
            continue
        # Little-Endian, byteweise umgedreht - fuer die Anzeige genuegt es,
        # "ueberall" von "nur hier" zu unterscheiden.
        ueberall = set(roh) == {"0"}
        adressen.append("alle Adressen (0.0.0.0)" if ueberall else "nur 127.0.0.1")
if adressen:
    print("   Gebunden an    :", ", ".join(sorted(set(adressen))))
    if im_codespace and not any("alle" in a for a in adressen):
        print("                    ACHTUNG: nur lokal erreichbar. Die Weiter-")
        print("                    leitung von GitHub kommt so nicht heran -")
        print("                    die Seite oeffnet sich dann nicht.")
        print("                    Beheben mit:  bash starten.sh")
PY
  python3 - "$PORT" <<'PY'
import sys, urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with op.open(f"http://127.0.0.1:{sys.argv[1]}/api/uebersicht", timeout=6) as r:
        # Bewusst nicht "laeuft korrekt": Geprueft ist nur der Zugriff von
        # diesem Rechner aus. Ob die Weiterleitung herankommt, sagt die Zeile
        # "Gebunden an" darueber.
        print(f"   Antwort intern : HTTP {r.status} - der Dienst antwortet")
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
