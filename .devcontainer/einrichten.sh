#!/usr/bin/env bash
# Einmalige Einrichtung des Codespace. Laeuft automatisch beim Erzeugen.
set -euo pipefail

echo ""
echo "  Bewerbungsassistent wird eingerichtet …"
echo ""

# Chromium wird fuer die PDF-Ausgabe gebraucht. Ohne das laeuft alles andere,
# nur am Ende gaebe es keine fertigen Dokumente - deshalb gehoert es in die
# Einrichtung und nicht in eine spaetere Fehlermeldung.
echo "  [1/2] Chromium fuer die PDF-Ausgabe …"
sudo apt-get update -qq
sudo apt-get install -y -qq chromium fonts-liberation fonts-dejavu-core > /dev/null

echo "  [2/2] Python-Bibliothek fuer die Claude-API …"
pip install --quiet --upgrade anthropic

echo ""
echo "  Fertig. Der Assistent startet gleich von allein."
echo ""
