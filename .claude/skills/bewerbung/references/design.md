# Optische Anpassung an die Firma

Die Idee: Die Unterlagen sollen aussehen, als koennten sie aus dem Haus der Firma
stammen - vertrautes Farbklima, verwandte Typografie. Beim Durchblaettern eines
Stapels faellt so etwas auf, noch bevor ein Wort gelesen wurde.

Die Grenze ist genauso wichtig: Es entsteht **keine Nachbildung der Website**.
Ein Lebenslauf ist ein Geschaeftsdokument, kein Werbemittel. Wird es zu bunt,
kippt der Eindruck von "hat sich Muehe gegeben" zu "unseriös" - und das ist
schwerer zu reparieren als ein blasses Layout.

## Ablauf

```bash
python3 scripts/extract_brand.py https://firma.de -o brand.json --emit-css theme.css
```

`theme.css` neben die HTML-Dateien legen - die Vorlagen binden sie bereits ein und
faerben sich damit selbst. Ohne die Datei bleibt eine seriöse Standardpalette
stehen, die Dokumente sind also nie kaputt.

## Ergebnis pruefen, nicht blind uebernehmen

Das Skript arbeitet mit Heuristiken. Zwei Minuten Kontrolle lohnen sich:

1. **Stimmt `primary` mit dem ueberein, was die Website zeigt?** Im Zweifel die
   Seite mit WebFetch ansehen oder `evidence.top_colors` in `brand.json`
   durchgehen und eine andere Farbe eintragen.
2. **`contrast.primary_on_white` unter 4.5?** Dann ist die Farbe fuer Text zu
   hell. `--primary-text` benutzt automatisch eine abgedunkelte Variante - die
   Flaechenfarbe bleibt das Original.
3. **Passt `secondary`?** Das Skript setzt sie bewusst oft auf `null`, wenn keine
   klare zweite Hausfarbe erkennbar ist. Eine falsche Zweitfarbe faellt staerker
   auf als eine fehlende - im Zweifel bei einer Farbe plus Abstufungen bleiben.
4. **Schrift:** `fonts.heading_original` zeigt, was die Firma einsetzt,
   `heading_stack` die lokal verfuegbare Entsprechung. Webfonts der Firma sind
   lokal fast nie installiert und werden auch nicht nachgeladen - die
   Klassifikation (Serif, Grotesk, geometrisch) traegt den Wiedererkennungswert.

## Wo Farbe eingesetzt wird

Sparsam und immer an derselben Logik: Farbe markiert Struktur, nie Inhalt.

| Element | Farbe |
|---|---|
| Name im Kopf | `--primary-text` |
| Linie unter dem Kopf | `--primary` |
| Abschnittsueberschriften | `--primary-text` |
| Trennlinien | `--rule` |
| Firmenname in Stationen | `--primary-text` |
| Aufzaehlungspunkte (Marker) | `--primary` |
| Zeitangaben, Nebeninfos | `--muted` |
| Flaechen (Chips) | `--wash` |
| **Fliesstext** | **immer `--ink` auf Weiss** |

Faustregel: Auf einer Seite hoechstens etwa ein Zehntel der Flaeche farbig. Wenn
das Dokument beim Zusammenkneifen der Augen bunt wirkt statt strukturiert, ist es
zu viel.

## Branchen

Der Farbwert allein macht es nicht - der Zuschnitt muss zur Branche passen:

- **Bank, Versicherung, Kanzlei, oeffentlicher Dienst** → sehr zurueckhaltend.
  Farbe nur in Linien und Ueberschriften, keine Flaechen, keine Chips.
- **Industrie, Mittelstand, Handwerk** → klar und funktional, ruhige Palette,
  Lesbarkeit vor Gestaltung.
- **Startup, Agentur, Tech, Design** → mehr Freiheit; Chips, kraeftigere
  Akzente und eine markantere Kopfzeile sind hier erwuenscht. Bei
  Gestaltungsberufen ist ein zu braves Dokument ein echter Nachteil.
- **Gesundheit, Pflege, Bildung, Soziales** → ruhig und warm, keine grellen
  Signalfarben.

Bei sehr dunklen Hausfarben (viele Banken und Konzerne fuehren ein fast
schwarzes Navy) wirkt das Dokument schnell schwer. Dann Linien duenner setzen und
Flaechen ganz weglassen.

## Feste Grenzen

- **Kein Firmenlogo in den eigenen Unterlagen.** Das ist eine fremde Marke; es
  wirkt anmassend und beruehrt Kennzeichenrecht. Farb- und Schriftsprache
  adaptieren ist voellig in Ordnung - das Zeichen selbst uebernehmen nicht.
- **Keine Farbverlaeufe, keine farbigen Vollflaechen ueber die ganze Seite.**
  Sie fressen Toner, verschlechtern Ausdrucke und stoeren beim Lesen.
- **Fliesstext nie in Markenfarbe.** Auch bei gutem Kontrast bleibt farbiger
  Fliesstext anstrengend.
- **Nicht unter 10 pt.** Wenn der Inhalt nicht passt, wird gekuerzt, nicht
  verkleinert.
- **Anschreiben und Lebenslauf tragen dieselbe Palette und dieselbe Schrift.**
  Zwei unterschiedlich gestaltete Dokumente im selben Umschlag wirken
  zusammengewuerfelt.

## Wenn die Website nicht erreichbar ist

Manche Seiten blockieren automatisierte Zugriffe oder rendern erst per
JavaScript. Dann der Reihe nach:

1. Andere Einstiegsseite versuchen: `karriere.firma.de`, `firma.de/karriere`,
   `firma.de/impressum` - Karriereseiten sind oft schlanker als die Startseite.
2. Seite mit WebFetch ansehen und die Farben aus der Beschreibung ableiten.
3. Die Palette von Hand in `theme.css` eintragen.
4. Notfalls bei der Standardpalette bleiben. Ein sauberes, neutrales Dokument ist
   deutlich besser als eines mit falsch geratenen Hausfarben.
