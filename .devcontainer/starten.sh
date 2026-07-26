#!/usr/bin/env bash
# Startet den Assistenten im Codespace. Laeuft bei jedem Oeffnen automatisch.
#
# Bewusst nur eine Huelle um starten.sh im Projektordner: Zwei Startwege, die
# sich langsam auseinanderentwickeln, waren schon einmal die Ursache dafuer,
# dass ein Fehler an der einen Stelle behoben war und an der anderen nicht.
# Alles Inhaltliche steht dort - hier nur, was den Codespace ausmacht.
cd "$(dirname "$0")/.." || exit 1

# --kein-browser: Im Container gibt es keinen. Das Fenster oeffnet GitHub
# selbst, sobald der Port weitergeleitet ist.
exec bash starten.sh --kein-browser
