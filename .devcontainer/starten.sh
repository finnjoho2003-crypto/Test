#!/usr/bin/env bash
# Startet den Assistenten im Codespace. Laeuft bei jedem Oeffnen.
cd "$(dirname "$0")/.." || exit 1

PROTOKOLL=/tmp/bewerbung-start.log
: > "$PROTOKOLL"

# Selbstheilend: Wurde der Codespace vor dieser Konfiguration angelegt oder ist
# die Einrichtung abgebrochen, fehlt die Bibliothek.
if ! python3 -c "import anthropic" 2>/dev/null; then
  echo "  Bibliothek wird nachinstalliert (einen Moment) …"
  pip install --quiet anthropic >>"$PROTOKOLL" 2>&1 \
    || echo "  (Fehlgeschlagen - die Oberflaeche laeuft trotzdem.)"
fi

# Chromium im HINTERGRUND holen. Es wird nur fuer die PDF-Ausgabe gebraucht,
# ist aber gross und langsam. Im Vordergrund - erst recht in
# postCreateCommand - blockiert es den Aufbau des Codespace, und man sitzt
# minutenlang vor einem Ladebalken, ohne die Oberflaeche je zu sehen.
if ! command -v chromium >/dev/null 2>&1 && [ ! -x /usr/bin/chromium ]; then
  (
    export DEBIAN_FRONTEND=noninteractive
    sudo -E apt-get update -qq \
      && sudo -E apt-get install -y -qq --no-install-recommends \
           chromium fonts-liberation fonts-dejavu-core \
      && echo "PDF-Ausgabe ist jetzt bereit."
  ) >>"$PROTOKOLL" 2>&1 &
  echo "  PDF-Ausgabe wird im Hintergrund vorbereitet -"
  echo "  die Oberflaeche kannst du sofort benutzen."
fi

echo ""

# -u (ungepuffert): Sonst haengt die Startmeldung mit der Adresse im Puffer,
# waehrend der Dienst laengst laeuft. 0.0.0.0, weil die Weiterleitung von
# GitHub den Dienst je nach Umgebung nicht auf 127.0.0.1 erreicht.
python3 -u webapp/server.py --host 0.0.0.0 --kein-browser 2>&1 | tee -a "$PROTOKOLL"
