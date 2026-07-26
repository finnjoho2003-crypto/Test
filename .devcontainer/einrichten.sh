#!/usr/bin/env bash
# Einmalige Einrichtung des Codespace. Laeuft automatisch beim Erzeugen.
#
# Absichtlich winzig: Alles, was hier laeuft, blockiert den Aufbau des
# Codespace - und wer wartet, sieht nur einen Ladebalken ohne Erklaerung.
# Deshalb steht hier nur das Noetigste (wenige Sekunden). Chromium fuer die
# PDF-Ausgabe ist gross und langsam und wird spaeter im Hintergrund geholt,
# waehrend die Oberflaeche schon benutzbar ist - siehe starten.sh.
#
# Ohne "set -e": Ein Fehlschlag hier darf den Codespace nicht unbrauchbar
# machen.

echo "  Bewerbungsassistent: Grundeinrichtung …"

if timeout 180 pip install --quiet --upgrade anthropic 2>/dev/null; then
  echo "  Fertig. Der Assistent startet gleich."
else
  echo "  Hinweis: 'anthropic' konnte nicht installiert werden."
  echo "  Wird beim Start erneut versucht."
fi

exit 0
