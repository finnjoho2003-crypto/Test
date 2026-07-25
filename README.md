# Bewerbungsassistent

Ein Claude-Code-Skill, der aus einer Stellenanzeige vollstaendige, individuell
zugeschnittene Bewerbungsunterlagen erstellt - optisch an das Design der Firma
angepasst.

## Was das Tool macht

Aus einem Link zu einer Stellenanzeige entstehen vier Dinge:

| Ergebnis | Inhalt |
|---|---|
| `analyse.md` | Muss- und Kann-Anforderungen, Schluesselbegriffe, was zwischen den Zeilen steht, Warnsignale |
| `Lebenslauf.pdf` | auf die Stelle zugeschnitten, im Farb- und Schriftklima der Firma |
| `Anschreiben.pdf` | dieselbe Optik, individuell argumentiert, nach DIN 5008 |
| `gespraech.md` | was im Vorstellungsgespraech gesagt werden sollte und was nicht - jeweils mit Begruendung |

Zusaetzlich kann das Tool das Web nach passenden Stellen durchsuchen und eine
begruendete Auswahl mit gepruefen Links liefern.

## Optische Anpassung an die Firma

Das Tool ruft die Website der Firma auf und leitet daraus Hausfarben und
Typografie ab: aus CSS-Variablen, `theme-color`, Marken-Selektoren und den
tatsaechlich eingesetzten Schriftfamilien. Getestet unter anderem an:

| Firma | erkannte Hausfarbe | erkannte Schrift |
|---|---|---|
| Telekom | `#e20074` | TeleNeo |
| DHL | `#d40511` | Delivery |
| Siemens | `#000028` | SiemensSans |
| dm | `#002878` | dmbrand |
| SAP | `#0040b0` | Arial |

Die Farbe wird dabei bewusst nur als Akzent eingesetzt - in Linien,
Ueberschriften und Hervorhebungen. Fliesstext bleibt schwarz auf Weiss, und zu
helle Markenfarben werden fuer Text automatisch abgedunkelt, bis der Kontrast
lesbar ist. Das Logo der Firma wird nicht uebernommen.

## Benutzung

Der Skill liegt unter `.claude/skills/bewerbung/` und wird automatisch geladen.
In Claude Code genuegt:

```
https://www.firma.de/karriere/stellenangebot-12345
```

oder ausdruecklich:

```
/bewerbung  Erstelle mir die Unterlagen fuer diese Stelle: <Link>
```

Beim ersten Mal legt das Tool `bewerbung/profil.md` an - dort kommen die eigenen
Daten hinein (Werdegang, Erfolge mit Zahlen, Kenntnisse). Das passiert einmal;
danach ist jede weitere Bewerbung eine Sache von Minuten.

### Auch einzeln nutzbar

```
Schreib mir nur das Anschreiben fuer <Link>
Gib mir Interview-Tipps fuer mein Gespraech bei <Firma>
Such mir Stellen als Logistikplanerin im Raum Bremen
```

## Grundsatz: nichts wird erfunden

Das Tool waehlt aus, ordnet, gewichtet und formuliert - aber es erfindet keine
Station, keine Zahl und kein Zertifikat. Was nicht im Profil steht, taucht in
keiner Bewerbung auf. Fehlende Anforderungen werden benannt statt ueberspielt:
in der Analyse als Luecke und im Gespraechsbriefing als vorbereitete Antwort.

Der Grund ist praktisch, nicht moralisch: Erfundene Angaben fallen spaetestens im
Gespraech oder bei den Zeugnissen auf, und dann ist mehr verloren als die eine
Stelle.

## Aufbau

```
.claude/skills/bewerbung/
├── SKILL.md                      Ablauf und Regeln
├── references/
│   ├── stellenanalyse.md         Anzeige auswerten, zwischen den Zeilen lesen
│   ├── anschreiben.md            Aufbau, Formulierungen, Floskelliste, Beispiel
│   ├── lebenslauf.md             Zuschnitt, Luecken, Maschinenlesbarkeit
│   ├── design.md                 Hausfarben anwenden, Grenzen, Branchen
│   ├── gespraech.md              sagen / nicht sagen, Fragen, Gehalt
│   └── jobsuche.md               Suchstrategie und Bewertung der Treffer
├── scripts/
│   ├── extract_brand.py          Website → brand.json + theme.css
│   └── render_pdf.py             HTML → PDF, meldet die Seitenzahl
└── assets/
    ├── lebenslauf.html           Vorlage, faerbt sich ueber theme.css
    ├── anschreiben.html          Vorlage nach DIN 5008
    └── profil-vorlage.md         Datenvorlage
```

## Skripte einzeln aufrufen

```bash
# Hausfarben und Schriften einer Firma auslesen
python3 .claude/skills/bewerbung/scripts/extract_brand.py https://firma.de \
        -o brand.json --emit-css theme.css

# HTML nach PDF rendern (meldet die Seitenzahl mit)
python3 .claude/skills/bewerbung/scripts/render_pdf.py anschreiben.html lebenslauf.html
```

Beide Skripte brauchen nur die Python-Standardbibliothek. Fuer die
PDF-Ausgabe wird Chrome oder Chromium verwendet; ein abweichender Pfad laesst
sich ueber die Umgebungsvariable `CHROMIUM_BIN` setzen.

## Datenschutz

Das Profil enthaelt Adresse, Telefonnummer und Werdegang. Diese Daten bleiben im
Arbeitsverzeichnis. Beim Auslesen der Firmenwebsite werden keine persoenlichen
Daten uebertragen - es wird nur die oeffentliche Seite abgerufen.
