#!/usr/bin/env bash
# Oeffnet den Assistenten - notfalls ohne die Port-Weiterleitung von GitHub.
#
#   bash oeffnen.sh
#
# Gedacht fuer den Fall, dass die weitergeleitete Adresse im Browser nicht
# laedt. Der eingebaute Browser von VS Code laeuft innerhalb derselben
# Umgebung wie der Dienst und erreicht ihn deshalb ueber 127.0.0.1 direkt -
# ohne Tunnel, ohne Anmeldeseite, ohne Browser-Einstellungen dazwischen.
#
# Startet den Dienst mit, falls er nicht laeuft, damit ein Befehl genuegt.

cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8765}"

laeuft() {
  python3 - "$PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(2)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

if ! laeuft; then
  echo "  Der Assistent laeuft noch nicht - er wird jetzt gestartet."
  echo ""
  # Im Hintergrund und abgekoppelt, damit dieses Fenster frei bleibt und der
  # Dienst nicht mitstirbt, sobald das Terminal geschlossen wird.
  #
  # Nicht in /tmp/bewerbung-start.log umleiten: Dort schreibt starten.sh
  # bereits selbst hinein. Zwei Schreiber auf einer Datei ergeben ein
  # doppeltes, verwirrendes Protokoll.
  nohup bash starten.sh --kein-browser >/dev/null 2>&1 &
  for _ in $(seq 1 40); do
    laeuft && break
    sleep 0.5
  done
fi

if ! laeuft; then
  echo "  Der Dienst antwortet nicht. Letzte Meldungen:"
  echo ""
  tail -n 20 /tmp/bewerbung-start.log 2>/dev/null | sed 's/^/    /'
  exit 1
fi

echo "  Der Assistent laeuft."
echo ""

# "code" ist in Codespaces und in VS Code immer da; ohne die Erweiterung
# fuer den eingebauten Browser passiert nichts Schlimmes - dann bleibt der
# Weg ueber den Reiter PORTS, der unten ohnehin genannt wird.
if command -v code >/dev/null 2>&1; then
  echo "  Er wird jetzt direkt hier im Editor geoeffnet …"
  code --open-url "http://127.0.0.1:$PORT" 2>/dev/null \
    || code --goto "http://127.0.0.1:$PORT" 2>/dev/null \
    || true
  echo ""
fi

echo "  Oeffnet sich nichts, gibt es zwei Wege von Hand:"
echo ""
echo "  1) Im Editor:  Taste F1 druecken, 'Simple Browser' eintippen,"
echo "     'Simple Browser: Show' waehlen und diese Adresse eingeben:"
echo ""
echo "         http://127.0.0.1:$PORT"
echo ""
if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
  echo "  2) Im eigenen Browser:"
  echo ""
  echo "         https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  echo ""
fi
