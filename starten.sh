#!/usr/bin/env bash
# Startet den Bewerbungsassistenten - im Codespace wie auf dem eigenen Rechner.
#
#   bash starten.sh
#
# Holt fehlende Bausteine nach und startet. Bewusst ohne "set -e": Ein
# fehlgeschlagener Zwischenschritt soll nicht den Start verhindern - die
# Oberflaeche laeuft auch dann, nur einzelne Funktionen fehlen.

cd "$(dirname "$0")" || exit 1
PROTOKOLL=/tmp/bewerbung-start.log
: > "$PROTOKOLL"

echo ""
echo "  Bewerbungsassistent wird gestartet …"
echo ""

# Eine noch laufende aeltere Fassung beenden. Ohne das scheitert jeder zweite
# Start an einem belegten Port - und nach einem "git pull" liefe ausserdem
# weiter der alte Programmstand, waehrend die Oberflaeche schon die neue ist.
# Das ergibt einen 404 auf Aufrufe, die es erst in der neuen Fassung gibt.
#
# Ueber die Prozessnummer, die der Dienst beim Start hinterlegt - nicht ueber
# eine Mustersuche in Kommandozeilen. Die trifft naemlich auch jeden fremden
# Prozess, der das Muster zufaellig enthaelt, bis hin zu der Shell, die die
# Suche selbst ausfuehrt.
PORT="${PORT:-8765}"
PID_DATEI="${BEWERBUNG_DATA:-bewerbung}/dienst.pid"

# Gegenprobe vor jedem kill: Gehoert die Nummer wirklich zu unserem Dienst?
# Nach einem Absturz kann sie laengst an ein fremdes Programm neu vergeben sein.
ist_unser_dienst() {
  [ -n "$1" ] && grep -qs "webapp/server.py" "/proc/$1/cmdline" 2>/dev/null
}

beende() {
  kill "$1" 2>/dev/null || return 1
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$1" 2>/dev/null || return 0
    sleep 0.3
  done
  kill -9 "$1" 2>/dev/null
  return 0
}

ALT=""
[ -f "$PID_DATEI" ] && ALT=$(cat "$PID_DATEI" 2>/dev/null)

# Ohne PID-Datei: Der laufende Dienst wurde von einer Fassung gestartet, die
# noch keine angelegt hat. Genau der Fall nach einem Update - und der
# hartnaeckigste: Die alte Fassung lauscht womoeglich nur auf 127.0.0.1, ist
# also von aussen gar nicht erreichbar, blockiert aber den Port. Von innen
# sieht dann alles in Ordnung aus, waehrend sich die Seite nicht oeffnen
# laesst. Deshalb wird sie hier ueber den belegten Port aufgespuert.
if ! ist_unser_dienst "$ALT"; then
  for KANDIDAT in $( { fuser -n tcp "$PORT" 2>/dev/null \
                     || ss -lptnH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 \
                     || lsof -ti "tcp:$PORT" 2>/dev/null; } ); do
    if ist_unser_dienst "$KANDIDAT"; then ALT="$KANDIDAT"; break; fi
  done
fi

if ist_unser_dienst "$ALT" && beende "$ALT"; then
  echo "  Laufende Fassung auf Port $PORT beendet."
fi
rm -f "$PID_DATEI"

if ! python3 -c "import anthropic" 2>/dev/null; then
  echo "  Bibliothek 'anthropic' fehlt - wird nachinstalliert …"
  pip install --quiet anthropic >>"$PROTOKOLL" 2>&1 \
    && echo "  erledigt." \
    || echo "  FEHLGESCHLAGEN - die Oberflaeche laeuft trotzdem, das Texten nicht."
  echo ""
fi

# Chromium wird nur fuer die PDF-Ausgabe gebraucht, ist aber gross und langsam.
# Deshalb im Hintergrund, waehrend die Oberflaeche schon benutzbar ist.
if [ -n "${CODESPACES:-}" ] && ! command -v chromium >/dev/null 2>&1 \
   && [ ! -x /usr/bin/chromium ]; then
  (
    export DEBIAN_FRONTEND=noninteractive
    sudo -E apt-get update -qq \
      && sudo -E apt-get install -y -qq --no-install-recommends \
           chromium fonts-liberation fonts-dejavu-core \
      && echo "PDF-Ausgabe ist jetzt bereit."
  ) >>"$PROTOKOLL" 2>&1 &
  echo "  PDF-Ausgabe wird im Hintergrund vorbereitet -"
  echo "  die Oberflaeche kannst du sofort benutzen."
  echo ""
fi

# Im Codespace muss auf allen Adressen gelauscht werden, damit die
# Weiterleitung von GitHub den Dienst zuverlaessig erreicht. Lokal bleibt es
# beim strengen Standard, damit nichts ungefragt im Netz steht.
if [ -n "${CODESPACES:-}" ]; then
  BINDUNG=(--host 0.0.0.0)
  echo "  Codespace erkannt - die Oberflaeche erscheint gleich unter 'PORTS'."
else
  BINDUNG=()
fi

# -u (ungepuffert) ist hier wichtig: Sonst haengt die Startmeldung mit der
# Adresse im Puffer fest, und man sitzt vor einem leeren Fenster, obwohl der
# Dienst laengst laeuft. tee schreibt zusaetzlich ein Protokoll fuer pruefen.sh.
python3 -u webapp/server.py "${BINDUNG[@]}" "$@" 2>&1 | tee -a "$PROTOKOLL"
