#!/usr/bin/env bash
# Einmalige Einrichtung des Codespace. Laeuft automatisch beim Erzeugen.
#
# Bewusst OHNE "set -e": Bricht hier ein Schritt ab, wuerde sonst der komplette
# Aufbau des Codespace scheitern - und man saehe minutenlang einen
# Ladebildschirm, ohne zu erfahren warum. Jeder Schritt darf hier fehlschlagen;
# die Oberflaeche laeuft auch dann, nur einzelne Funktionen fehlen.

echo ""
echo "  Bewerbungsassistent wird eingerichtet …"
echo ""

# Ohne diese Variable kann apt-get auf eine Rueckfrage warten, die im
# Codespace niemand beantworten kann - der Aufbau haengt dann endlos.
export DEBIAN_FRONTEND=noninteractive

echo "  [1/2] Chromium fuer die PDF-Ausgabe …"
if timeout 300 sudo -E apt-get update -qq \
   && timeout 600 sudo -E apt-get install -y -qq --no-install-recommends \
        chromium fonts-liberation fonts-dejavu-core > /dev/null 2>&1; then
  echo "        erledigt."
else
  echo "        FEHLGESCHLAGEN - die Oberflaeche laeuft trotzdem,"
  echo "        aber es entstehen keine PDF-Dateien."
  echo "        Nachholen im Terminal:  sudo apt-get install -y chromium"
fi

echo "  [2/2] Python-Bibliothek fuer die Claude-API …"
if timeout 300 pip install --quiet --upgrade anthropic; then
  echo "        erledigt."
else
  echo "        FEHLGESCHLAGEN - nachholen im Terminal:  pip install anthropic"
fi

echo ""
echo "  Einrichtung beendet. Der Assistent startet gleich von allein."
echo ""
exit 0
