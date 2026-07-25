"""Anbindung an die Claude API - Stellenanalyse, Unterlagen, Gespraechsbriefing.

Drei Aufrufe pro Bewerbung. Die ersten beiden liefern strukturiertes JSON
(Structured Outputs), damit das Ergebnis direkt in die Vorlagen wandern kann,
ohne Freitext zu zerlegen. Der dritte liefert Markdown, weil das Briefing
gelesen und nicht weiterverarbeitet wird.
"""

from __future__ import annotations

import json
import os

MODELL = "claude-opus-5"

# Die Regel steht bewusst am Anfang jedes Prompts: Bei Bewerbungsunterlagen ist
# eine erfundene Angabe kein Schoenheitsfehler, sondern ein Kuendigungsgrund.
GRUNDREGEL = """Du hilfst einer Person bei ihrer Bewerbung.

Die wichtigste Regel: Erfinde nichts. Keine Station, kein Jahr, keine Zahl, kein
Zertifikat, keine Sprachkenntnis, die nicht im Profil steht. Du waehlst aus,
ordnest, gewichtest und formulierst praezise - mehr nicht. Wenn eine Anforderung
im Profil keine Entsprechung hat, benennst du sie als Luecke, statt sie zu
ueberspielen.

Erfundene Angaben fallen spaetestens im Gespraech oder bei den Zeugnissen auf.
Dann ist nicht nur die Stelle weg, sondern bei Anstellung auch die
Anfechtbarkeit des Arbeitsvertrags im Raum."""


def client():
    """Client mit Zugangsdaten aus der Umgebung (ANTHROPIC_API_KEY).

    Die Bibliothek wird bewusst erst hier importiert und nicht oben im Modul.
    Sonst haengt der komplette Server an ihr - und die Oberflaeche liesse sich
    nicht einmal oeffnen, um den Schluessel einzutragen, nur weil eine
    Bibliothek fehlt, die allein fuer das Texten gebraucht wird.
    """
    try:
        import anthropic  # noqa: PLC0415
    except ModuleNotFoundError as fehler:
        raise RuntimeError(
            "Die Bibliothek 'anthropic' fehlt. Im Terminal einmal ausfuehren: "
            "pip install anthropic - danach den Assistenten neu starten."
        ) from fehler

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(
            "Kein API-Schluessel gefunden. Bitte ANTHROPIC_API_KEY setzen "
            "(https://console.anthropic.com/settings/keys)."
        )
    return anthropic.Anthropic()


def _json_antwort(system: str, inhalt: str, schema: dict,
                  max_tokens: int = 16000) -> dict:
    """Ein Aufruf mit erzwungenem JSON-Schema.

    Gestreamt, weil die Unterlagen-Antwort lang werden kann und ein
    nicht-gestreamter Aufruf dann in den HTTP-Timeout des SDK laeuft.
    """
    with client().messages.stream(
        model=MODELL,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": inhalt}],
    ) as stream:
        antwort = stream.get_final_message()

    if antwort.stop_reason == "refusal":
        raise RuntimeError("Die Anfrage wurde abgelehnt. Bitte Inhalt pruefen.")
    text = next((b.text for b in antwort.content if b.type == "text"), "")
    if not text:
        raise RuntimeError("Leere Antwort vom Modell erhalten.")
    return json.loads(text)


# --------------------------------------------------------------------------- #
# 1. Stellenanzeige analysieren
# --------------------------------------------------------------------------- #

def _anforderung_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "anforderung": {"type": "string"},
                "woertlich": {"type": "string",
                              "description": "Formulierung aus der Anzeige"},
                "gewicht": {"type": "integer",
                            "description": "1 gering, 2 mittel, 3 hoch"},
            },
            "required": ["anforderung", "woertlich", "gewicht"],
            "additionalProperties": False,
        },
    }


ANALYSE_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {"type": "string"},
        "firma": {"type": "string"},
        "ort": {"type": "string"},
        "firma_website": {"type": "string",
                          "description": "Startseite der Firma, nicht der Jobboerse. Leer, wenn unbekannt."},
        "ansprechpartner": {"type": "string"},
        "anrede": {"type": "string",
                   "description": "Vollstaendige Anrede, z. B. 'Sehr geehrte Frau Dr. Sommer,'. "
                                  "Bei unbekanntem oder nicht eindeutigem Namen 'Sehr geehrte Damen und Herren,'."},
        "referenz": {"type": "string"},
        "eintritt": {"type": "string"},
        "gehalt": {"type": "string"},
        "branche": {"type": "string"},
        "tonalitaet": {"type": "string", "enum": ["sie-formell", "sie-locker", "du"]},
        "muss": _anforderung_schema(),
        "kann": _anforderung_schema(),
        "implizit": {"type": "array", "items": {"type": "string"}},
        "schluesselbegriffe": {"type": "array", "items": {"type": "string"}},
        "zwischen_den_zeilen": {"type": "array", "items": {"type": "string"}},
        "warnsignale": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["position", "firma", "ort", "firma_website", "ansprechpartner",
                 "anrede", "referenz", "eintritt", "gehalt", "branche",
                 "tonalitaet", "muss", "kann", "implizit", "schluesselbegriffe",
                 "zwischen_den_zeilen", "warnsignale"],
    "additionalProperties": False,
}


def analysiere_stelle(anzeigentext: str, url: str) -> dict:
    system = f"""{GRUNDREGEL}

Analysiere jetzt eine Stellenanzeige. Trenne Muss- von Kann-Anforderungen: Ein
Punkt ist ein Muss, wenn er mit "zwingend", "Voraussetzung", "setzen wir voraus"
oder "mindestens X Jahre" markiert ist oder ein formaler Abschluss gefordert
wird. "Idealerweise", "von Vorteil", "wuenschenswert" markieren ein Kann.
Punkte, die weit oben stehen oder mehrfach auftauchen, wiegen schwerer -
unabhaengig vom Wortlaut.

Bei "zwischen_den_zeilen" deutest du codierte Formulierungen ("Hands-on-
Mentalitaet" = kleines Team, viel selbst machen; "hohe Belastbarkeit" =
Ueberstunden eingeplant). Das sind Hypothesen fuer die Gespraechsvorbereitung,
keine Fakten - formuliere sie entsprechend vorsichtig.

Schluesselbegriffe uebernimmst du woertlich so, wie sie in der Anzeige stehen.
Fuer die Anrede: rate niemals das Geschlecht aus einem Namen. Ist es nicht
eindeutig, nutze die vollstaendige Namensform ohne Herr/Frau."""

    return _json_antwort(
        system,
        f"Quelle: {url}\n\nStellenanzeige:\n\n{anzeigentext[:60000]}",
        ANALYSE_SCHEMA,
    )


# --------------------------------------------------------------------------- #
# 2. Unterlagen texten
# --------------------------------------------------------------------------- #

UNTERLAGEN_SCHEMA = {
    "type": "object",
    "properties": {
        "passung": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
        "passung_begruendung": {"type": "string"},
        "luecken": {
            "type": "array",
            "description": "Anforderungen ohne Deckung im Profil. Ehrlich benennen.",
            "items": {
                "type": "object",
                "properties": {
                    "anforderung": {"type": "string"},
                    "naechstliegendes": {"type": "string",
                                         "description": "Was im Profil am naechsten drankommt, oder leer"},
                    "umgang": {"type": "string",
                               "description": "Wie im Gespraech damit umgehen"},
                },
                "required": ["anforderung", "naechstliegendes", "umgang"],
                "additionalProperties": False,
            },
        },
        "lebenslauf": {
            "type": "object",
            "properties": {
                "berufsbezeichnung": {"type": "string"},
                "kurzprofil": {"type": "string",
                               "description": "3-4 Zeilen, auf die Stelle zugeschnitten"},
                "stationen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string"},
                            "firma": {"type": "string"},
                            "ort": {"type": "string"},
                            "von": {"type": "string"},
                            "bis": {"type": "string"},
                            "punkte": {
                                "type": "array",
                                "description": "3-5 Punkte, staerkster zuerst. Handlung, Umfang, Ergebnis mit Zahl.",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["position", "firma", "ort", "von", "bis", "punkte"],
                        "additionalProperties": False,
                    },
                },
                "ausbildung": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "abschluss": {"type": "string"},
                            "institut": {"type": "string"},
                            "ort": {"type": "string"},
                            "von": {"type": "string"},
                            "bis": {"type": "string"},
                            "punkte": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["abschluss", "institut", "ort", "von", "bis", "punkte"],
                        "additionalProperties": False,
                    },
                },
                "kenntnisse": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"kategorie": {"type": "string"},
                                       "werte": {"type": "string"}},
                        "required": ["kategorie", "werte"],
                        "additionalProperties": False,
                    },
                },
                "sprachen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"sprache": {"type": "string"},
                                       "niveau": {"type": "string"}},
                        "required": ["sprache", "niveau"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["berufsbezeichnung", "kurzprofil", "stationen",
                         "ausbildung", "kenntnisse", "sprachen"],
            "additionalProperties": False,
        },
        "anschreiben": {
            "type": "object",
            "properties": {
                "betreff": {"type": "string"},
                "referenzzeile": {"type": "string"},
                "anrede": {"type": "string"},
                "einstieg": {"type": "string"},
                "beleg1": {"type": "string"},
                "beleg2": {"type": "string"},
                "motivation": {"type": "string"},
                "abschluss": {"type": "string"},
                "anlagen": {"type": "string"},
            },
            "required": ["betreff", "referenzzeile", "anrede", "einstieg",
                         "beleg1", "beleg2", "motivation", "abschluss", "anlagen"],
            "additionalProperties": False,
        },
    },
    "required": ["passung", "passung_begruendung", "luecken", "lebenslauf", "anschreiben"],
    "additionalProperties": False,
}


def erstelle_unterlagen(analyse: dict, profil: dict) -> dict:
    system = f"""{GRUNDREGEL}

Erstelle jetzt Lebenslauf-Inhalt und Anschreiben.

Lebenslauf: Der Werdegang bleibt unveraendert - du sortierst die Punkte pro
Station so, dass der staerkste Bezug zur Anzeige oben steht, und laesst weg, was
nichts beitraegt. Muster je Punkt: Handlung, Gegenstand/Umfang, Ergebnis mit
Zahl. Zahlen sind der Kern; wo im Profil keine steht, erfindest du keine.
Begriffe der Anzeige woertlich aufgreifen, wenn dieselbe Taetigkeit gemeint ist.

Anschreiben: eine Seite, rund 300-400 Woerter.
- Einstieg: niemals "hiermit bewerbe ich mich". Direkt mit dem staerksten
  Sachargument oder einem konkreten Firmenbezug beginnen.
- beleg1 und beleg2: die zwei schwersten Anforderungen der Analyse, in
  absteigender Gewichtung. Aufbau: Anforderung aufgreifen, konkrete Situation,
  eigene Handlung, messbares Ergebnis. Ein Absatz ohne ueberpruefbares Ergebnis
  ist eine Behauptung und wirkt auch so.
- motivation: muss den Austauschtest bestehen. Steht der Firmenname noch
  sinnvoll da, wenn man ihn durch einen Wettbewerber ersetzt, ist der Absatz
  wertlos.
- abschluss: Verfuegbarkeit, Gehalt nur falls die Anzeige danach fragt,
  Gespraechswunsch ohne Konjunktiv ("Ich freue mich auf das Gespraech").

Verboten sind Floskeln: "Ihre Stellenanzeige hat mein Interesse geweckt",
"teamfaehig, belastbar und motiviert", "Ich wuerde mich freuen", "dynamisches
Umfeld". Adjektive sind schwach, Verben und Zahlen stark.

Ton an die Anzeige angleichen: Bei "du" auch duzen. Bei Bank, Versicherung,
Kanzlei oder Behoerde durchgehend Sie, vollstaendige Saetze, keine Anglizismen
ohne Not. Bei Startup und Agentur kuerzere Saetze und Fachbegriffe der Branche.

Die Luecken-Liste fuellst du ehrlich aus - sie ist fuer die Person, nicht fuer
die Firma, und taucht in keinem Dokument auf."""

    inhalt = (
        "STELLENANALYSE:\n" + json.dumps(analyse, ensure_ascii=False, indent=2)
        + "\n\nPROFIL DER PERSON:\n" + json.dumps(profil, ensure_ascii=False, indent=2)
    )
    return _json_antwort(system, inhalt, UNTERLAGEN_SCHEMA, max_tokens=32000)


# --------------------------------------------------------------------------- #
# 3. Gespraechsvorbereitung
# --------------------------------------------------------------------------- #

def gespraechs_briefing(analyse: dict, profil: dict, luecken: list) -> str:
    system = f"""{GRUNDREGEL}

Erstelle jetzt ein Briefing fuer das Vorstellungsgespraech als Markdown. Es wird
einmal vor dem Termin gelesen - alles muss auf diese Stelle, diese Firma und
dieses Profil zugeschnitten sein. Allgemeine Ratschlaege sind wertlos.

Genau diese Struktur:

# Gespraechsvorbereitung: {{Position}} bei {{Firma}}

## Die drei Botschaften
Was am Ende ueber die Person haengenbleiben soll, abgeleitet aus den schwersten
Anforderungen. Je Botschaft ein Beleg aus dem Profil.

## Das sollte unbedingt gesagt werden
Tabelle mit den Spalten Anlass | Formulierung | Warum das wirkt.
Ein Satz ohne Anlass wird auswendig gelernt und an der falschen Stelle
abgeladen - deshalb gehoert zu jedem Punkt, wann er passt.

## Das sollte vermieden werden
Tabelle mit den Spalten Nicht sagen | Warum | Stattdessen.
Immer mit Alternative - eine reine Verbotsliste macht nervoes, statt zu helfen.
Der haeufigste Einzelfehler ist Schlechtes ueber den frueheren Arbeitgeber; das
gehoert hier hinein.

## Wahrscheinliche Fragen
Je Frage ein Antwortgeruest aus dem echten Material der Person - Stichpunkte,
keine Musterantwort. Auswendig Gelerntes klingt hoerbar auswendig gelernt.
Mindestens: Erzaehlen Sie etwas ueber sich / Warum wir / Warum weg / Staerken
und Schwaechen / schwieriges Projekt / Konflikt im Team / Gehalt / Ihre Fragen.

## Heikle Punkte
Zu jeder Luecke und jedem erklaerungsbeduerftigen Punkt eine ruhige, ehrliche
Antwort. Nichts beschoenigen.

## Gehalt
Zielzahl und Untergrenze aus dem Profil, konkrete Formulierung, Umgang mit der
Frage nach dem bisherigen Gehalt.

## Eigene Rueckfragen
Fuenf bis acht, davon mindestens drei firmenspezifisch aus der Analyse.
Nicht als erste Frage: Urlaub, Homeoffice, Gehalt.

## Unzulaessige Fragen
Kurz: wonach nicht gefragt werden darf und dass eine unwahre Antwort dort
zulaessig ist.

Schreibe direkt das Markdown, ohne Vorrede."""

    inhalt = (
        "STELLENANALYSE:\n" + json.dumps(analyse, ensure_ascii=False, indent=2)
        + "\n\nPROFIL:\n" + json.dumps(profil, ensure_ascii=False, indent=2)
        + "\n\nERKANNTE LUECKEN:\n" + json.dumps(luecken, ensure_ascii=False, indent=2)
    )

    with client().messages.stream(
        model=MODELL,
        max_tokens=32000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": inhalt}],
    ) as stream:
        antwort = stream.get_final_message()

    if antwort.stop_reason == "refusal":
        raise RuntimeError("Die Anfrage wurde abgelehnt.")
    return "\n".join(b.text for b in antwort.content if b.type == "text")
