#!/usr/bin/env bash
# Bewerbungsassistent starten - zum Doppelklicken auf macOS und Linux.
#
# macOS: doppelklicken. Beim ersten Mal meldet sich eventuell die
#        Sicherheitsabfrage - dann Rechtsklick > Oeffnen waehlen.
#
# Absichtlich nur eine Huelle um starten.sh: Diese Datei hatte frueher eine
# eigene Startlogik und rief den Dienst ohne --host auf. Im Codespace lauscht
# er dann nur auf 127.0.0.1, die Weiterleitung von GitHub kommt nicht heran,
# und die Seite oeffnet sich nie - waehrend im Terminal "laeuft" steht. Zwei
# fast gleich heissende Startdateien mit unterschiedlichem Verhalten sind eine
# Falle; es gibt jetzt nur noch einen Weg.
cd "$(dirname "$0")" || exit 1
exec bash starten.sh "$@"
