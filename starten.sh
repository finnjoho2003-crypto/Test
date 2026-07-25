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

if ! python3 -c "import anthropic" 2>/dev/null; then
  echo "  Bibliothek 'anthropic' fehlt - wird nachinstalliert …"
  pip install --quiet anthropic >>"$PROTOKOLL" 2>&1 \
    && echo "  erledigt." \
    || echo "  FEHLGESCHLAGEN - die Oberflaeche laeuft trotzdem, das Texten nicht."
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
