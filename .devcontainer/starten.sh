#!/usr/bin/env bash
# Startet den Assistenten im Codespace. Laeuft bei jedem Oeffnen.
cd "$(dirname "$0")/.." || exit 1

# Selbstheilend: Wurde der Codespace vor dieser Konfiguration angelegt oder ist
# die Einrichtung abgebrochen, fehlt die Bibliothek. Statt mit einer
# Fehlermeldung zu enden, wird sie hier einfach nachinstalliert.
if ! python3 -c "import anthropic" 2>/dev/null; then
  echo "  Bibliothek wird nachinstalliert …"
  pip install --quiet anthropic || echo "  (Fehlgeschlagen - die Oberflaeche laeuft trotzdem.)"
fi

exec python3 webapp/server.py --kein-browser
