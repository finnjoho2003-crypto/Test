#!/usr/bin/env bash
# Packt die eigenen Daten in eine einzelne Datei zum Mitnehmen.
#
#   bash sichern.sh
#
# Gedacht fuer den Umzug aus dem Codespace auf den eigenen Rechner - und als
# Sicherungskopie. Die erzeugte ZIP-Datei liegt danach im Projektordner und
# laesst sich dort mit Rechtsklick > Download herunterladen.
#
# Der API-Schluessel bleibt bewusst draussen. Er ist in Sekunden neu
# eingetragen, waehrend eine Datei mit einem gueltigen Schluessel darin
# irgendwann versehentlich irgendwo landet - und dann zahlt jemand anders
# auf deine Rechnung. Wer ihn trotzdem braucht: bash sichern.sh --mit-schluessel

cd "$(dirname "$0")" || exit 1

MIT_SCHLUESSEL=0
[ "${1:-}" = "--mit-schluessel" ] && MIT_SCHLUESSEL=1

DATEN="${BEWERBUNG_DATA:-bewerbung}"
if [ ! -d "$DATEN" ]; then
  echo "  Es gibt noch keine Daten zum Sichern ($DATEN fehlt)."
  exit 1
fi

ZIEL="bewerbung-sicherung-$(date +%Y-%m-%d).zip"

python3 - "$DATEN" "$ZIEL" "$MIT_SCHLUESSEL" <<'PY'
import sys, zipfile
from pathlib import Path

daten, ziel, mit_schluessel = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1"

# dienst.pid ist die Prozessnummer des gerade laufenden Dienstes - auf einem
# anderen Rechner ist sie nicht nur wertlos, sondern irrefuehrend.
AUSGESCHLOSSEN = {"dienst.pid"}
if not mit_schluessel:
    AUSGESCHLOSSEN.add("schluessel.txt")

anzahl = groesse = 0
with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as archiv:
    for pfad in sorted(daten.rglob("*")):
        if not pfad.is_file() or pfad.name in AUSGESCHLOSSEN:
            continue
        # Immer unter "bewerbung/" ablegen, egal wie der Ordner hier heisst -
        # beim Entpacken auf dem Zielrechner muss der Name stimmen.
        innen = Path("bewerbung") / pfad.relative_to(daten)
        archiv.write(pfad, innen)
        anzahl += 1
        groesse += pfad.stat().st_size

def zaehle(muster):
    return sum(1 for _ in daten.glob(muster))

print()
print(f"  Gesichert in: {ziel}  ({ziel.stat().st_size // 1024} KB)")
print(f"  {anzahl} Datei(en), zusammen {groesse // 1024} KB unkomprimiert")
print()
print(f"    Profile          : {zaehle('profile/*.json')}")
print(f"    Bewerbungsfotos  : {zaehle('profile/*-foto.*')}")
print(f"    Bewerbungen      : {sum(1 for p in (daten / 'bewerbungen').glob('*') if p.is_dir()) if (daten / 'bewerbungen').is_dir() else 0}")
print(f"    Uebungsgespraeche: {zaehle('gespraeche/*.json')}")
print(f"    Zeugnisse        : {zaehle('zeugnisse/*.json')}")
print()
if not mit_schluessel:
    print("  Der API-Schluessel ist NICHT enthalten - den traegst du auf dem")
    print("  neuen Rechner einmal neu ein. Das ist Absicht.")
    print()
PY

cat <<'ENDE'
  So geht es weiter:

  1. Links im Datei-Verzeichnis die ZIP-Datei suchen.
  2. Rechtsklick darauf > Download. Sie landet in deinem Download-Ordner.
  3. Auf dem eigenen Rechner: Die ZIP-Datei in den Programmordner legen -
     dorthin, wo auch start.bat liegt - und dort entpacken
     (Rechtsklick > Alle extrahieren).
  4. Danach liegt dort ein Ordner "bewerbung". Fertig.

  Gibt es dort schon einen Ordner "bewerbung", wird er ueberschrieben.
  Im Zweifel vorher umbenennen.

ENDE
