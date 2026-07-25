# Stellenanzeige analysieren

Ziel: aus der Anzeige herausholen, was tatsaechlich ueber die Stelle entscheidet -
und zwar getrennt nach dem, was dasteht, und dem, was zwischen den Zeilen steht.
Alles Weitere (Anschreiben, Lebenslauf, Gespraechsvorbereitung) baut auf dieser
Analyse auf. Wird hier ungenau gearbeitet, wird die Bewerbung generisch.

## Ergebnis: `analyse.md`

Diese Struktur verwenden:

```markdown
# Stellenanalyse: {Position} bei {Firma}

## Eckdaten
- Position / Referenznummer:
- Firma, Standort, Remote-Anteil:
- Ansprechpartner (Name, Funktion, Anrede):
- Bewerbungsfrist / Eintrittstermin:
- Gehaltsangabe (falls genannt):
- Quelle (URL, Abrufdatum):

## Muss-Anforderungen
| # | Anforderung | Woertlich in der Anzeige | Gewicht |

## Kann-Anforderungen
| # | Anforderung | Woertlich | Gewicht |

## Implizite Anforderungen
Was die Anzeige nicht sagt, aber verlangt.

## Schluesselbegriffe
Begriffe, die woertlich in die Unterlagen gehoeren.

## Tonalitaet
Du/Sie, formell/locker, Fachsprache. Bestimmt den Stil der Unterlagen.

## Firmenkontext
Groesse, Branche, Eigentuemer, aktuelle Lage, Produkt.

## Auffaelligkeiten
Unklarheiten, Warnsignale, Gespraechsstoff.
```

## Muss und Kann trennen

Die Anzeige markiert das meist sprachlich, und die Formulierung ist verlaesslicher
als die Ueberschrift des Absatzes:

| Signal | Einordnung |
|---|---|
| "zwingend", "Voraussetzung", "setzen wir voraus", "mindestens X Jahre" | Muss |
| "abgeschlossenes Studium der ..." | Muss, oft formal gefiltert |
| "idealerweise", "von Vorteil", "wuenschenswert", "Plus" | Kann |
| "erste Erfahrung", "Grundkenntnisse" | Kann, niedrige Huerde |
| Punkt steht **an erster Stelle** der Liste | hoeheres Gewicht, unabhaengig vom Wortlaut |
| Punkt wird an zwei Stellen wiederholt | hoeheres Gewicht |

Gewicht auf einer Skala 1-3 vergeben. Die Reihenfolge der Argumente im Anschreiben
folgt spaeter genau diesem Gewicht - das ist der Grund, warum die Bewertung hier
sorgfaeltig passieren muss.

## Zwischen den Zeilen lesen

Im deutschsprachigen Raum sind einige Wendungen ziemlich eindeutig codiert. Sie
gehoeren nicht in die Bewerbung, sondern in die Gespraechsvorbereitung und in die
Entscheidung, ob die Stelle ueberhaupt passt:

| Formulierung | Wahrscheinliche Bedeutung |
|---|---|
| "Hands-on-Mentalitaet" | kleines Team, wenig Zuarbeit, viel selbst machen |
| "hohe Belastbarkeit", "Einsatzbereitschaft" | Ueberstunden sind eingeplant |
| "wachsendes, dynamisches Umfeld" | Prozesse sind im Aufbau, vieles ist unfertig |
| "Allrounder", "vielseitige Aufgaben" | Rolle ist nicht scharf geschnitten |
| "Kommunikationsstaerke" bei technischer Rolle | viel Abstimmung, Stakeholder-Arbeit |
| "Wir sind ein Familienunternehmen" | flache Hierarchie, aber lange Entscheidungswege |
| "Duz-Kultur", "Obstkorb", "Kicker" | eher junges Team; Benefits ersetzen teils Gehalt |
| "Erfahrung in der Fuehrung von ..." ohne Personalverantwortung im Titel | fachliche, nicht disziplinarische Fuehrung |
| Gehaltsspanne fehlt trotz Tarifbindung | Verhandlung ist vorgesehen |
| "Neu geschaffene Position" | kein Vorgaenger, viel Gestaltung, wenig Einarbeitung |
| "Nachbesetzung" / "aufgrund von Wachstum" | eingespielte Strukturen vorhanden |

Diese Deutungen sind Hypothesen, keine Fakten. Genau so auch benennen - im
Gespraech werden daraus gute Rueckfragen.

## Schluesselbegriffe fuer die Unterlagen

Viele Unternehmen filtern Bewerbungen vor der menschlichen Sichtung, und auch
Menschen suchen beim Ueberfliegen nach den Begriffen aus der eigenen Anzeige.
Deshalb: Begriffe **woertlich so uebernehmen, wie sie in der Anzeige stehen**,
wenn die Erfahrung tatsaechlich vorhanden ist.

- Steht dort "Warenwirtschaftssystem", nicht "ERP" schreiben - beides nennen.
- Steht dort "SAP S/4HANA", nicht nur "SAP".
- Abkuerzung und ausgeschriebene Form einmal zusammen nennen: "Qualitaetsmanagement (QM)".

Die Grenze ist klar: Begriffe uebernehmen ja, sich Erfahrung zuschreiben nein.
Fehlt eine Anforderung, wird sie nicht durch geschickte Wortwahl ersetzt, sondern
in der Luecken-Liste vermerkt.

## Firmenkontext recherchieren

Zwei bis vier Fakten reichen, aber sie muessen konkret sein. Nuetzlich sind:
Produkt und Geschaeftsmodell, Groesse und Standorte, Eigentuemerverhaeltnisse,
juengste Meldungen (Uebernahme, neues Werk, neues Produkt, Jahreszahlen),
Karriereseite und Unternehmenswerte, Bewertungen von Beschaeftigten.

Was davon in die Bewerbung darf, entscheidet ein einfacher Test: Ein Fakt taugt
nur dann, wenn er sich mit der eigenen Erfahrung verbinden laesst. "Ihr neues Werk
in Leipzig" allein ist Schmuck; "Ihr neues Werk in Leipzig - Serienanlauf ist genau
das, was ich bei X zweimal begleitet habe" ist ein Argument.

## Ansprechpartner

Nach Name und korrekter Anrede suchen (Anzeige, Karriereseite, Impressum,
LinkedIn). Eine namentliche Anrede ist der billigste erkennbare Unterschied zu
einer Massenbewerbung. Ist niemand genannt, "Sehr geehrte Damen und Herren"
verwenden - erfundene oder geratene Namen sind schlimmer als gar keiner.

Bei der Anrede auf die tatsaechlich gefuehrte Form achten (Titel wie Dr. oder
Prof. gehoeren dazu). Ist das Geschlecht aus dem Namen nicht eindeutig ableitbar,
nicht raten: dann die vollstaendige Namensform ohne Herr/Frau verwenden
("Guten Tag, Kim Berger") oder auf die allgemeine Anrede ausweichen.

## Warnsignale

Notieren, nicht verschweigen - die Entscheidung trifft der Mensch, nicht das Tool:

- keine Angaben zu Vertragsart, Befristung oder Umfang
- Gehalt "nach Vereinbarung" bei gleichzeitig sehr langer Anforderungsliste
- Anforderungsprofil passt nicht zur ausgeschriebenen Berufserfahrung
  (z. B. "Berufseinsteiger" plus "mindestens 5 Jahre Erfahrung")
- Personalvermittlung ohne Nennung des Kunden
- auffaellig viele Superlative, keine konkreten Aufgaben
- Anzeige laeuft seit Monaten unveraendert
