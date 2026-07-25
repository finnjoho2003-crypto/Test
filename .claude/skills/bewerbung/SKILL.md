---
name: bewerbung
description: >-
  Erstellt vollstaendige, individuell zugeschnittene Bewerbungsunterlagen aus
  einer Stellenanzeige: Analyse der Anzeige, massgeschneiderter Lebenslauf und
  Anschreiben als PDF, optisch an das Design der Firma angepasst (Farben und
  Typografie werden von der Firmenwebsite abgeleitet), dazu eine
  Gespraechsvorbereitung mit konkreten Formulierungen fuer das
  Vorstellungsgespraech. Sucht auf Wunsch auch passende Stellen im Web. Nutze
  diesen Skill immer, wenn ein Link zu einer Stellenanzeige geschickt wird oder
  wenn von Bewerbung, Anschreiben, Lebenslauf, CV, Cover Letter, Motivations-
  schreiben, Stellenanzeige, Jobsuche, Vorstellungsgespraech oder
  Bewerbungsunterlagen die Rede ist - auch dann, wenn nur nach einem Teil davon
  gefragt wird (etwa nur nach dem Anschreiben oder nur nach Interview-Tipps).
---

# Bewerbungsassistent

Aus einer Stellenanzeige und dem Profil der Person entstehen vier Dinge:

1. **`analyse.md`** - was die Anzeige wirklich verlangt
2. **`Lebenslauf.pdf`** - auf die Stelle zugeschnitten, im Design der Firma
3. **`Anschreiben.pdf`** - dieselbe Optik, individuell argumentiert
4. **`gespraech.md`** - was im Gespraech gesagt werden sollte und was nicht

## Die eine Regel, die alles andere schlaegt

**Nichts erfinden.** Keine Station, kein Jahr, keine Zahl, kein Zertifikat, keine
Sprachkenntnis, die nicht aus dem Profil der Person stammt.

Das ist keine Formalie. Eine erfundene Angabe faellt spaetestens im Gespraech oder
bei den Zeugnissen auf, und dann ist nicht nur die Stelle weg, sondern bei
Anstellung auch die Anfechtbarkeit des Arbeitsvertrags im Raum. Erlaubt und
erwuenscht ist das Gegenteil: auswaehlen, umsortieren, gewichten, praezise
formulieren, Begriffe der Anzeige aufgreifen - solange die Substanz gedeckt ist.

Fehlt etwas Wichtiges, wird es benannt, nicht ueberspielt: als Luecke in der
Analyse und als vorbereitete Antwort im Gespraechsbriefing. Bei Unsicherheit, ob
eine Formulierung noch gedeckt ist, lieber kurz nachfragen als grosszuegig
auslegen.

## Ablauf

### Schritt 0 - Profil beschaffen

Nach `bewerbung/profil.md` oder aehnlichen Dateien im Arbeitsverzeichnis suchen
(auch nach vorhandenen Lebenslaeufen als PDF oder DOCX - daraus laesst sich das
Profil gut vorbefuellen).

Ist nichts vorhanden: `assets/profil-vorlage.md` nach `bewerbung/profil.md`
kopieren, der Person sagen, dass sie es ausfuellen soll, und anbieten, die Daten
stattdessen im Gespraech aufzunehmen. Ohne Profil keine Unterlagen - alles andere
liefe auf Erfinden hinaus.

Bei einem bereits vorhandenen Profil fehlende Angaben gebuendelt erfragen, nicht
einzeln nacheinander.

### Schritt 1 - Anzeige analysieren

Die Anzeige mit WebFetch laden. Kommt man nicht heran (Portale sperren
gelegentlich), die Person um den Text bitten.

Dann `references/stellenanalyse.md` lesen und `analyse.md` erstellen. Das ist die
Grundlage fuer alles Weitere; hier entscheidet sich, ob die Bewerbung individuell
oder generisch wird. Muss- und Kann-Anforderungen trennen, gewichten,
Schluesselbegriffe woertlich notieren, Ansprechpartner suchen.

Anschliessend Profil gegen Anforderungen spiegeln: Was ist belegt? Was ist
teilweise belegt? Was fehlt ganz?

### Schritt 2 - Firmendesign ableiten

Die Firmenwebsite bestimmen (nicht die Job-Boerse - `stepstone.de` ist nicht die
Firma) und auswerten:

```bash
python3 scripts/extract_brand.py https://firma.de -o brand.json --emit-css theme.css
```

Ergebnis kurz pruefen: Passt `primary` zu dem, was die Website zeigt? Details und
das Vorgehen bei nicht erreichbaren Seiten stehen in `references/design.md`.

### Schritt 3 - Unterlagen erstellen

`assets/lebenslauf.html` und `assets/anschreiben.html` ins Arbeitsverzeichnis
kopieren, `theme.css` danebenlegen und die Platzhalter fuellen.

Vorher die passende Referenz lesen: `references/lebenslauf.md` fuer den
Lebenslauf, `references/anschreiben.md` fuer das Anschreiben. Dort steht das
Handwerk - Aufbau, Formulierungsmuster, Floskeln, die schaden, Umgang mit
Luecken.

Dann rendern:

```bash
python3 scripts/render_pdf.py anschreiben.html lebenslauf.html
```

Das Skript gibt die Seitenzahl mit aus. **Anschreiben: genau eine Seite.
Lebenslauf: eine bis zwei.** Passt es nicht, wird gekuerzt - nicht die Schrift
verkleinert.

Dateien sprechend benennen: `Nachname_Vorname_Anschreiben.pdf`,
`Nachname_Vorname_Lebenslauf.pdf`.

### Schritt 4 - Gespraech vorbereiten

`references/gespraech.md` lesen und `gespraech.md` erstellen: die drei
Botschaften, was unbedingt gesagt werden sollte, was unbedingt vermieden werden
muss (beides mit Begruendung), wahrscheinliche Fragen mit Antwortgeruest aus dem
echten Material, heikle Punkte, Gehalt, eigene Rueckfragen.

Dieser Schritt gehoert zum Auftrag, auch wenn nur nach den Unterlagen gefragt
wurde - er ist der Teil, der spaeter am meisten traegt. Bei der Uebergabe kurz
erwaehnen, dass es die Datei gibt.

### Schritt 5 - Uebergeben

Kurz zusammenfassen: erstellte Dateien, uebernommene Hausfarbe, die zwei bis drei
staerksten Argumente, **ehrlich die Luecken** und was die Person noch pruefen
sollte. Erstellte PDFs mit SendUserFile schicken, falls verfuegbar.

## Stellensuche

Wird nach passenden Stellen gefragt statt nach Unterlagen zu einer bestimmten
Anzeige: `references/jobsuche.md` lesen und danach vorgehen. Ergebnis ist eine
begruendete Auswahl mit gepruefen Links, keine Trefferliste. Danach fragen, fuer
welche Stelle die Unterlagen erstellt werden sollen.

## Teilauftraege

Wird nur ein Teil verlangt ("schreib mir nur das Anschreiben", "gib mir
Interview-Tipps"), auch nur diesen Teil liefern - aber die Schritte 0 bis 2
trotzdem ausfuehren, soweit sie dafuer gebraucht werden. Ein Anschreiben ohne
Stellenanalyse ist genau das generische Schreiben, das vermieden werden soll.

Am Ende einen Satz zu dem anbieten, was sonst noch entstehen koennte - aber es
nicht ungefragt mitliefern.

## Sprache

Die Unterlagen folgen der Sprache der Anzeige: deutsche Anzeige → deutsche
Bewerbung, englische Anzeige → englische Bewerbung. Bei englischsprachigen
Bewerbungen gelten andere Konventionen (kein Foto, kein Geburtsdatum, keine
Angaben zu Familienstand; "Resume"/"CV" statt Lebenslauf) - siehe
`references/lebenslauf.md`.

Analyse und Gespraechsvorbereitung immer in der Sprache der Person.

## Dateien

| Datei | Zweck |
|---|---|
| `references/stellenanalyse.md` | Anzeige auswerten, zwischen den Zeilen lesen |
| `references/anschreiben.md` | Aufbau, Formulierungen, Floskelliste, Beispiel |
| `references/lebenslauf.md` | Aufbau, Zuschnitt, Luecken, Maschinenlesbarkeit |
| `references/design.md` | Hausfarben anwenden, Grenzen, Branchenunterschiede |
| `references/gespraech.md` | Briefing: sagen / nicht sagen, Fragen, Gehalt |
| `references/jobsuche.md` | Suchstrategie und Bewertung der Treffer |
| `scripts/extract_brand.py` | Website → `brand.json` + `theme.css` |
| `scripts/render_pdf.py` | HTML → PDF (Chromium), meldet Seitenzahl |
| `assets/lebenslauf.html` | Vorlage, faerbt sich ueber `theme.css` |
| `assets/anschreiben.html` | Vorlage nach DIN 5008 |
| `assets/profil-vorlage.md` | Datenvorlage fuer die Person |

## Umgang mit den Daten

Das Profil enthaelt Adresse, Telefonnummer und Werdegang. Diese Daten bleiben im
Arbeitsverzeichnis und werden nirgends hochgeladen. Beim Recherchieren werden
Firmenseiten abgerufen - dabei werden keine Daten der Person uebertragen.
