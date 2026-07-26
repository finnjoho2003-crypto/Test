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
PID_DATEI="${BEWERBUNG_DATA:-bewerbung}/dienst.pid"
if [ -f "$PID_DATEI" ]; then
  ALT=$(cat "$PID_DATEI" 2>/dev/null)
  # Gegenprobe: Nach einem Absturz kann die Nummer laengst neu vergeben sein.
  if [ -n "$ALT" ] && grep -qs "server.py" "/proc/$ALT/cmdline" 2>/dev/null; then
    kill "$ALT" 2>/dev/null && echo "  Aeltere Fassung beendet." && sleep 1
  fi
  rm -f "$PID_DATEI"
fi

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
