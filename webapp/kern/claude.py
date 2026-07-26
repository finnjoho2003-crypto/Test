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


def client(schluessel: str | None = None):
    """Client mit Zugangsdaten aus der Umgebung (ANTHROPIC_API_KEY).

    Mit `schluessel` wird ein uebergebener Wert benutzt, ohne ihn vorher
    irgendwo zu hinterlegen - gedacht zum Pruefen einer Eingabe.

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

    if schluessel:
        return anthropic.Anthropic(api_key=schluessel)
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(
            "Es ist kein API-Schluessel hinterlegt. Oben auf der Uebersicht "
            "laesst er sich eintragen - zu holen unter "
            "console.anthropic.com/settings/keys."
        )
    return anthropic.Anthropic()


def klartext(fehler: Exception) -> str:
    """Uebersetzt einen API-Fehler in einen Satz, mit dem man etwas anfangen kann.

    Die Meldungen des SDK sind englisch und nennen den Statuscode - fuer die
    Fehlersuche gut, fuer die Person vor dem Bildschirm nutzlos. Wichtig ist
    nicht, dass 401 kam, sondern was jetzt zu tun ist.
    """
    status = getattr(fehler, "status_code", None)
    if status == 401:
        return ("Der API-Schluessel wurde abgelehnt. Meist ist er beim Kopieren "
                "unvollstaendig geblieben oder inzwischen geloescht worden. "
                "Bitte oben auf der Uebersicht ueber 'Schluessel aendern' einen "
                "neuen eintragen - er wird sofort geprueft.")
    if status == 403:
        return ("Der Schluessel ist gueltig, darf diesen Zugriff aber nicht. "
                "Gehoert er zur richtigen Organisation?")
    if status in (400, 402) and "credit" in str(fehler).lower():
        return ("Das Guthaben des Kontos ist aufgebraucht. Unter "
                "console.anthropic.com/settings/billing laesst es sich aufladen.")
    if status == 429:
        return ("Zu viele Anfragen in kurzer Zeit. Bitte ein paar Minuten warten "
                "und die Bewerbung erneut starten.")
    if status is not None and status >= 500:
        return ("Der Dienst antwortet gerade nicht. Das liegt nicht an dir - "
                "bitte die Bewerbung spaeter erneut starten.")
    return str(fehler) or fehler.__class__.__name__


def pruefe_schluessel(wert: str | None = None) -> None:
    """Wirft mit klarer Meldung, wenn der Schluessel nicht funktioniert.

    Fragt die Modellliste ab statt einen Text zu erzeugen: Das prueft die
    Zugangsdaten genauso, kostet aber nichts und dauert einen Wimpernschlag.

    Mit `wert` wird ein noch nicht gespeicherter Schluessel geprueft - so laesst
    sich beim Eintragen sofort antworten, statt die Person zwei Minuten auf eine
    Bewerbung warten zu lassen, die dann an "401" scheitert.
    """
    try:
        client(wert).models.list(limit=1)
    except Exception as fehler:  # noqa: BLE001
        raise RuntimeError(klartext(fehler)) from fehler


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

Anschreiben: eine Seite, 280 bis 340 Woerter - lieber am unteren Rand. Das ist
keine Stilfrage, sondern die Kapazitaet des Briefbogens: Darueber muss die
Gestaltung enger gezogen werden, und ein gedraengter Brief wirkt schlechter als
ein kurzer. Wer nichts mehr zu belegen hat, hoert auf.
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
# Hochgeladene Dokumente
# --------------------------------------------------------------------------- #

# Erkennung an den ersten Bytes - der Dateiname sagt nichts darueber, was
# wirklich in der Datei steht.
DOKUMENTARTEN = (
    (b"%PDF-", "document", "application/pdf"),
    (b"\xff\xd8\xff", "image", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image", "image/png"),
)
DOKUMENT_MAX = 20 * 1024 * 1024


def dokument_block(rohdaten: bytes) -> dict:
    """Macht aus hochgeladenen Bytes einen Inhaltsblock fuer die API."""
    if not rohdaten:
        raise ValueError("Die Datei war leer.")
    if len(rohdaten) > DOKUMENT_MAX:
        raise ValueError("Die Datei ist groesser als 20 MB. Bitte kleiner "
                         "einscannen oder als PDF speichern.")
    for kennung, art, typ in DOKUMENTARTEN:
        if rohdaten.startswith(kennung):
            break
    else:
        raise ValueError("Nur PDF, JPG und PNG lassen sich lesen. Word-Dateien "
                         "vorher als PDF speichern (Datei - Exportieren).")
    import base64  # noqa: PLC0415
    return {
        "type": art,
        "source": {"type": "base64", "media_type": typ,
                   # Ohne Zeilenumbrueche - die API lehnt sie ab.
                   "data": base64.b64encode(rohdaten).decode("ascii")},
    }


def _mit_dokumenten(system: str, dateien: list[bytes], anweisung: str,
                    schema: dict, max_tokens: int = 16000) -> dict:
    """Ein Aufruf mit angehaengten Dokumenten und erzwungenem Schema.

    Die Dokumente stehen vor dem Text: In dieser Reihenfolge liest das Modell
    zuverlaessiger, weil die Anweisung dann auf etwas bereits Gesehenes zeigt.
    """
    inhalt = [dokument_block(d) for d in dateien]
    inhalt.append({"type": "text", "text": anweisung})

    with client().messages.stream(
        model=MODELL,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high",
                       "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": inhalt}],
    ) as stream:
        antwort = stream.get_final_message()

    if antwort.stop_reason == "refusal":
        raise RuntimeError("Die Anfrage wurde abgelehnt. Bitte Inhalt pruefen.")
    text = next((b.text for b in antwort.content if b.type == "text"), "")
    if not text:
        raise RuntimeError("Aus dem Dokument liess sich nichts lesen. Ist es "
                           "vielleicht ein reiner Scan in schlechter Qualitaet?")
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Arbeitszeugnis entschluesseln
# --------------------------------------------------------------------------- #

ZEUGNIS_SCHEMA = {
    "type": "object",
    "properties": {
        "art": {"type": "string",
                "enum": ["qualifiziert", "einfach", "zwischenzeugnis", "unklar"]},
        "arbeitgeber": {"type": "string"},
        "position": {"type": "string"},
        "zeitraum": {"type": "string"},
        "gesamtnote": {"type": "string", "enum": ["1", "2", "3", "4", "5", "unklar"]},
        "gesamtnote_begruendung": {"type": "string",
                                   "description": "Woran genau die Note haengt"},
        "leistungsnote": {"type": "string", "enum": ["1", "2", "3", "4", "5", "unklar"]},
        "verhaltensnote": {"type": "string", "enum": ["1", "2", "3", "4", "5", "unklar"]},
        "formulierungen": {
            "type": "array",
            "description": "Die codierten Stellen, wichtigste zuerst",
            "items": {
                "type": "object",
                "properties": {
                    "zitat": {"type": "string", "description": "Woertlich aus dem Zeugnis"},
                    "bedeutung": {"type": "string", "description": "Was das im Klartext heisst"},
                    "einordnung": {"type": "string", "enum": ["gut", "neutral", "schlecht"]},
                },
                "required": ["zitat", "bedeutung", "einordnung"],
                "additionalProperties": False,
            },
        },
        "fehlt": {
            "type": "array",
            "description": "Was in einem vollstaendigen Zeugnis stehen muesste und "
                           "hier fehlt. Ein Fehlen ist selbst eine Aussage.",
            "items": {
                "type": "object",
                "properties": {
                    "was": {"type": "string"},
                    "warum_wichtig": {"type": "string"},
                },
                "required": ["was", "warum_wichtig"],
                "additionalProperties": False,
            },
        },
        "nachverhandeln": {
            "type": "array",
            "description": "Konkrete Aenderungswuensche an den Arbeitgeber",
            "items": {
                "type": "object",
                "properties": {
                    "stelle": {"type": "string"},
                    "vorschlag": {"type": "string",
                                  "description": "Ausformulierte bessere Fassung"},
                    "begruendung": {"type": "string"},
                },
                "required": ["stelle", "vorschlag", "begruendung"],
                "additionalProperties": False,
            },
        },
        "mitschicken": {"type": "string", "enum": ["ja", "eher ja", "eher nein"]},
        "mitschicken_begruendung": {"type": "string"},
    },
    "required": ["art", "arbeitgeber", "position", "zeitraum", "gesamtnote",
                 "gesamtnote_begruendung", "leistungsnote", "verhaltensnote",
                 "formulierungen", "fehlt", "nachverhandeln", "mitschicken",
                 "mitschicken_begruendung"],
    "additionalProperties": False,
}

ZEUGNIS_SYSTEM = """Du entschluesselst ein deutsches Arbeitszeugnis.

Deutsche Zeugnisse muessen wohlwollend formuliert sein - deshalb hat sich eine
Geheimsprache entwickelt, in der scheinbar freundliche Saetze eine Note tragen.
Uebersetze sie.

Die Zufriedenheitsskala, an der die Leistungsnote haengt:
  "stets zu unserer vollsten Zufriedenheit"            = 1
  "stets zu unserer vollen Zufriedenheit"              = 2
  "zu unserer vollsten Zufriedenheit"                  = 2
  "stets zu unserer Zufriedenheit"                     = 3
  "zu unserer vollen Zufriedenheit"                    = 3
  "zu unserer Zufriedenheit"                           = 4
  "im Grossen und Ganzen zu unserer Zufriedenheit"     = 5
  "hat sich bemueht" / "war bemueht"                   = hat es nicht geschafft

Auf die Verhaltensbeurteilung achten - die Reihenfolge der Genannten verraet
etwas. Steht "Kollegen" vor "Vorgesetzten", deutet das auf Spannungen nach oben.
Fehlen Vorgesetzte ganz, ist das ein deutliches Zeichen.

Weitere haeufige Codes: "gesellig" (Alkohol), "einfuehlsam gegenueber
Mitarbeiterinnen" (Anmache), "wusste sich zu verkaufen" (Blender), "trug zur
Verbesserung des Betriebsklimas bei" (trank gern mit), "war stets puenktlich"
als einziges Lob (mehr faellt uns nicht ein), "verliess uns auf eigenen Wunsch"
ohne Bedauern (man ist froh), "kuendigte fristlos" oder "im gegenseitigen
Einvernehmen" (Konflikt).

Pruefe auch, was FEHLT. Ein qualifiziertes Zeugnis braucht: Taetigkeits-
beschreibung, Leistungsbeurteilung, Verhaltensbeurteilung, Beendigungsgrund
sowie eine Dankes- und Bedauernsformel mit guten Wuenschen. Fehlt die
Schlussformel, ist das ein Signal - und sie laesst sich nachfordern.

Sei genau und nuechtern. Nicht dramatisieren: Ein Zeugnis mit Note 2 ist gut,
auch wenn es sich beim Lesen unspektakulaer anfuehlt. Aber auch nicht
beschoenigen - wer mit einem schlechten Zeugnis losgeht, ohne es zu wissen,
verliert Chancen, die er haette retten koennen.

Zitiere immer woertlich. Erfinde keine Formulierung, die nicht dasteht. Steht
etwas nicht im Dokument, ist die Note "unklar" - nicht geraten.

Beim Nachverhandeln: In Deutschland besteht ein Anspruch auf ein wohlwollendes
Zeugnis. Formuliere die Aenderungswuensche so, dass die Person sie woertlich
uebernehmen kann."""


def pruefe_zeugnis(dateien: list[bytes]) -> dict:
    return _mit_dokumenten(
        ZEUGNIS_SYSTEM, dateien,
        "Entschluessele dieses Arbeitszeugnis vollstaendig.",
        ZEUGNIS_SCHEMA, max_tokens=16000)


# --------------------------------------------------------------------------- #
# Profil aus vorhandenem Lebenslauf
# --------------------------------------------------------------------------- #

IMPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "vorname": {"type": "string"}, "nachname": {"type": "string"},
                "strasse": {"type": "string"}, "plz_ort": {"type": "string"},
                "email": {"type": "string"}, "telefon": {"type": "string"},
                "web": {"type": "string"}, "berufsbezeichnung": {"type": "string"},
            },
            "required": ["vorname", "nachname", "strasse", "plz_ort", "email",
                         "telefon", "web", "berufsbezeichnung"],
            "additionalProperties": False,
        },
        "kurzprofil": {"type": "string"},
        "stationen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "string"}, "firma": {"type": "string"},
                    "ort": {"type": "string"}, "von": {"type": "string"},
                    "bis": {"type": "string"}, "aufgaben": {"type": "string"},
                    "erfolge": {"type": "string",
                                "description": "Nur mit Zahl, wenn im Dokument eine steht"},
                    "tools": {"type": "string"},
                },
                "required": ["position", "firma", "ort", "von", "bis",
                             "aufgaben", "erfolge", "tools"],
                "additionalProperties": False,
            },
        },
        "ausbildung": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "abschluss": {"type": "string"}, "institut": {"type": "string"},
                    "ort": {"type": "string"}, "von": {"type": "string"},
                    "bis": {"type": "string"}, "note": {"type": "string"},
                    "schwerpunkt": {"type": "string"},
                },
                "required": ["abschluss", "institut", "ort", "von", "bis",
                             "note", "schwerpunkt"],
                "additionalProperties": False,
            },
        },
        "kenntnisse": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"kategorie": {"type": "string"}, "werte": {"type": "string"}},
                "required": ["kategorie", "werte"],
                "additionalProperties": False,
            },
        },
        "sprachen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"sprache": {"type": "string"}, "niveau": {"type": "string"}},
                "required": ["sprache", "niveau"],
                "additionalProperties": False,
            },
        },
        "weiteres": {"type": "string"},
        "unklar": {
            "type": "array",
            "description": "Was nicht sicher lesbar war und nachgeprueft gehoert",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "kurzprofil", "stationen", "ausbildung", "kenntnisse",
                 "sprachen", "weiteres", "unklar"],
    "additionalProperties": False,
}


def lies_lebenslauf(dateien: list[bytes]) -> dict:
    system = """Du liest einen vorhandenen Lebenslauf aus und uebertraegst ihn in
ein strukturiertes Profil.

Uebernimm ausschliesslich, was im Dokument steht. Erfinde nichts, ergaenze
nichts, runde nichts auf. Das Profil ist die Grundlage aller spaeteren
Bewerbungen - eine hier erfundene Angabe wandert ungeprueft in jedes Dokument
und faellt spaetestens im Gespraech auf.

Ist ein Feld im Dokument nicht enthalten, bleibt es leer. Ein leeres Feld ist
richtig, eine geratene Angabe ist falsch.

Datumsangaben in der Form MM/JJJJ, laufende Taetigkeiten mit "heute".

Bei "erfolge" nur uebernehmen, was tatsaechlich als Ergebnis dasteht -
idealerweise mit Zahl. Reine Aufgabenbeschreibungen gehoeren zu "aufgaben".

Ist etwas schlecht lesbar oder mehrdeutig (verwischter Scan, unklare
Abkuerzung), traegst du den besten Lesevorschlag ein und nennst die Stelle
zusaetzlich unter "unklar". Lieber einmal zu oft nachfragen lassen als eine
falsche Angabe stehen lassen."""

    return _mit_dokumenten(
        system, dateien,
        "Uebertrage diesen Lebenslauf vollstaendig in das Profil.",
        IMPORT_SCHEMA, max_tokens=16000)


# --------------------------------------------------------------------------- #
# Jobsuche im Web
# --------------------------------------------------------------------------- #

TREFFER_SCHEMA = {
    "type": "object",
    "properties": {
        "stellen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "firma": {"type": "string"},
                    "ort": {"type": "string"},
                    "url": {"type": "string",
                            "description": "Direkter Link zur Anzeige. Leer, wenn nicht gefunden."},
                    "quelle": {"type": "string",
                               "description": "Wo die Anzeige steht, z. B. die Jobboerse"},
                    "warum_passend": {"type": "string",
                                      "description": "Bezug zum Profil, ein bis zwei Saetze"},
                    "haken": {"type": "string",
                              "description": "Was gegen die Stelle sprechen koennte. Leer, wenn nichts auffiel."},
                    "passung": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                },
                "required": ["titel", "firma", "ort", "url", "quelle",
                             "warum_passend", "haken", "passung"],
                "additionalProperties": False,
            },
        },
        "hinweis": {"type": "string",
                    "description": "Was die Suche erschwert hat, oder leer"},
    },
    "required": ["stellen", "hinweis"],
    "additionalProperties": False,
}


def suche_stellen(profil: dict, was: str, wo: str, anzahl: int = 8) -> dict:
    """Sucht im Web nach passenden Stellen und liefert eine geprüfte Liste.

    Zwei Aufrufe statt einem: Erst wird gesucht, dann wird das Ergebnis in Form
    gebracht. Die Websuche liefert Fundstellen mit Quellenangaben; ein
    erzwungenes Schema im selben Aufruf vertraegt sich damit nicht zuverlaessig.
    Getrennt ist beides robust - und der zweite Aufruf ist billig, weil er nur
    noch Text sortiert.
    """
    person = profil.get("person", {})
    stationen = profil.get("stationen", [])
    kurz = {
        "berufsbezeichnung": person.get("berufsbezeichnung", ""),
        "kurzprofil": profil.get("kurzprofil", ""),
        "stationen": [{"position": s.get("position", ""), "firma": s.get("firma", ""),
                       "von": s.get("von", ""), "bis": s.get("bis", "")}
                      for s in stationen[:6]],
        "kenntnisse": profil.get("kenntnisse", []),
        "sprachen": profil.get("sprachen", []),
        "situation": profil.get("situation", {}),
    }

    system = f"""{GRUNDREGEL}

Du suchst jetzt im Web nach offenen Stellen fuer diese Person.

Vorgehen: Formuliere mehrere Suchanfragen - einmal mit der Berufsbezeichnung,
einmal mit den wichtigsten Kenntnissen, einmal mit branchenueblichen
Alternativbezeichnungen fuer dieselbe Taetigkeit. Suche auf Deutsch, wenn der
Ort in Deutschland, Oesterreich oder der Schweiz liegt.

Nenne nur Stellen, die du tatsaechlich in den Suchergebnissen gefunden hast,
mit der Adresse, die dort steht. Erfinde keine Anzeigen und keine Links - ein
toter Link kostet die Person Zeit und Vertrauen. Findest du weniger als
gewuenscht, ist das das Ergebnis; fuelle nicht auf.

Bewerte die Passung am Profil, nicht am Wunschdenken. Nenne bei jeder Stelle
auch, was dagegen sprechen koennte - eine Liste, in der alles passt, ist keine
Hilfe."""

    inhalt = (
        f"Gesucht wird: {was or 'passende Stellen zum Profil'}\n"
        f"Ort / Region: {wo or 'keine Vorgabe'}\n"
        f"Gewuenschte Anzahl: hoechstens {anzahl}\n\n"
        "PROFIL:\n" + json.dumps(kurz, ensure_ascii=False, indent=2)
    )

    with client().messages.stream(
        model=MODELL,
        max_tokens=16000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}],
        messages=[{"role": "user", "content": inhalt}],
    ) as stream:
        antwort = stream.get_final_message()

    # Serverseitige Werkzeuge haben ein Rundenlimit. Wird es erreicht, endet die
    # Antwort mit "pause_turn" - ohne Fortsetzung braeche die Suche hier
    # unbemerkt mitten im Vorgang ab.
    verlauf = [{"role": "user", "content": inhalt}]
    for _ in range(3):
        if antwort.stop_reason != "pause_turn":
            break
        verlauf = verlauf[:1] + [{"role": "assistant", "content": antwort.content}]
        with client().messages.stream(
            model=MODELL, max_tokens=16000, system=system,
            thinking={"type": "adaptive"}, output_config={"effort": "high"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}],
            messages=verlauf,
        ) as stream:
            antwort = stream.get_final_message()

    if antwort.stop_reason == "refusal":
        raise RuntimeError("Die Suchanfrage wurde abgelehnt. Bitte anders formulieren.")

    gefunden = "\n".join(b.text for b in antwort.content if b.type == "text").strip()
    if not gefunden:
        return {"stellen": [], "hinweis": "Die Suche hat nichts Verwertbares geliefert."}

    return _json_antwort(
        "Bringe die folgenden Suchergebnisse in Form. Uebernimm ausschliesslich, "
        "was im Text steht - besonders die Adressen. Erfinde nichts, ergaenze "
        "nichts, und lass eine Stelle lieber weg als sie zu erraten.",
        gefunden, TREFFER_SCHEMA, max_tokens=8000)


# --------------------------------------------------------------------------- #
# Uebungsgespraech: Gegenueber und Auswertung
# --------------------------------------------------------------------------- #

def _gespraech_system(analyse: dict, profil: dict, titel: str, firma: str) -> str:
    tonalitaet = analyse.get("tonalitaet") or "sie-formell"
    person = profil.get("person", {})
    return f"""Du fuehrst ein Vorstellungsgespraech. Du bist die Person, die
einstellt - nicht ein Assistent, der jemandem hilft.

Rolle: Personalverantwortliche bei {firma or 'der Firma'}, Gespraech ueber die
Stelle "{titel or 'die ausgeschriebene Position'}".
Anrede: {'du' if tonalitaet == 'du' else 'Sie'}.

So fuehrst du das Gespraech:
- Eine Frage pro Nachricht. Zwei Fragen auf einmal sind im echten Gespraech
  selten und machen die Uebung wertlos, weil nur die zweite beantwortet wird.
- Kurz. Zwei bis vier Saetze. Du bist nicht hier, um Vortraege zu halten.
- Du hoerst zu. Beziehe dich auf das, was gerade gesagt wurde, bevor du
  weiterfragst. Bleibt eine Antwort vage oder ohne Beispiel, hakst du nach -
  genau einmal, dann gehst du weiter.
- Der Ablauf ist der uebliche: Begruessung und "Erzaehlen Sie etwas ueber
  sich", dann Werdegang, dann fachliche Tiefe, dann Verhaltensfragen
  (schwieriges Projekt, Konflikt), dann Wechselgrund, dann Gehalt, zuletzt
  Rueckfragen. Halte dich daran, aber nicht stur - folge dem Gespraech.
- Bleib in der Rolle. Kein Lob, keine Tipps, keine Bewertung waehrend des
  Gespraechs. Die Auswertung kommt danach und getrennt.
- Sei freundlich, aber nicht gefaellig. Ein Gegenueber, das alles gut findet,
  bereitet auf nichts vor.
- Frage nichts Unzulaessiges (Familienplanung, Religion, Gesundheit,
  Parteizugehoerigkeit). Wenn die Person von sich aus davon anfaengt, gehst du
  darueber hinweg.

Du kennst die Unterlagen der Person - stelle also Fragen, die sich daraus
ergeben, statt allgemeiner Standardfragen. Luecken und Bruecke im Werdegang
darfst du ansprechen; das ist der Sinn der Uebung.

Beginne mit einer kurzen Begruessung und der ersten Frage.

BEWERBUNGSUNTERLAGEN (dein Wissensstand):
{json.dumps({'analyse': analyse, 'profil': profil, 'name': f"{person.get('vorname', '')} {person.get('nachname', '')}".strip()}, ensure_ascii=False, indent=2)[:40000]}"""


def gespraech_antwort(analyse: dict, profil: dict, titel: str, firma: str,
                      verlauf: list) -> str:
    """Die naechste Aeusserung des Gegenuebers."""
    nachrichten = [{"role": "assistant" if z["rolle"] == "recruiter" else "user",
                    "content": z["text"]} for z in verlauf]
    # Ohne eroeffnende Nutzernachricht lehnt die API ab; beim allerersten
    # Aufruf gibt es aber noch nichts zu antworten.
    if not nachrichten or nachrichten[0]["role"] != "user":
        nachrichten.insert(0, {"role": "user", "content": "Guten Tag."})

    with client().messages.stream(
        model=MODELL,
        max_tokens=2000,
        system=_gespraech_system(analyse, profil, titel, firma),
        thinking={"type": "adaptive"},
        # Bewusst niedrig: Ein Gegenueber, das zehn Sekunden ueberlegt, zerstoert
        # den Rhythmus eines Gespraechs - und Ueberlegen hilft hier wenig.
        output_config={"effort": "low"},
        messages=nachrichten,
    ) as stream:
        antwort = stream.get_final_message()

    if antwort.stop_reason == "refusal":
        raise RuntimeError("Die Antwort wurde abgelehnt. Bitte anders formulieren.")
    return "\n".join(b.text for b in antwort.content if b.type == "text").strip()


FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "gesamteindruck": {"type": "string",
                           "description": "Drei bis fuenf Saetze, ehrlich"},
        "einschaetzung": {"type": "string",
                          "enum": ["ueberzeugend", "solide", "ausbaufaehig"]},
        "stark": {
            "type": "array",
            "description": "Was gut lief - mit Zitat aus dem Gespraech",
            "items": {
                "type": "object",
                "properties": {
                    "punkt": {"type": "string"},
                    "zitat": {"type": "string", "description": "Woertlich aus der Antwort"},
                    "warum": {"type": "string"},
                },
                "required": ["punkt", "zitat", "warum"],
                "additionalProperties": False,
            },
        },
        "schwach": {
            "type": "array",
            "description": "Was schlecht lief - immer mit besserer Fassung",
            "items": {
                "type": "object",
                "properties": {
                    "punkt": {"type": "string"},
                    "zitat": {"type": "string"},
                    "warum": {"type": "string"},
                    "besser": {"type": "string",
                               "description": "Konkret ausformuliert, aus dem Material der Person"},
                },
                "required": ["punkt", "zitat", "warum", "besser"],
                "additionalProperties": False,
            },
        },
        "naechstes_mal": {
            "type": "array",
            "description": "Hoechstens drei Dinge, auf die zu achten ist",
            "items": {"type": "string"},
        },
    },
    "required": ["gesamteindruck", "einschaetzung", "stark", "schwach", "naechstes_mal"],
    "additionalProperties": False,
}


def gespraech_feedback(analyse: dict, profil: dict, verlauf: list) -> dict:
    system = f"""{GRUNDREGEL}

Werte jetzt ein Uebungsgespraech aus. Du sprichst zu der Person, die geuebt hat.

Sei ehrlich. Eine Auswertung, in der alles gut war, hilft niemandem und kostet
im echten Gespraech die Stelle. Umgekehrt gilt: Jede Kritik braucht eine
konkrete bessere Fassung - "war zu vage" allein ist keine Hilfe.

Belege alles mit woertlichen Zitaten aus dem Verlauf. Erfinde keine Aussage,
die nicht gefallen ist.

Die besseren Fassungen baust du ausschliesslich aus dem, was im Profil steht.
Lege der Person keine Erfahrung in den Mund, die sie nicht hat - sie muesste
den Satz im echten Gespraech sagen koennen.

Achte besonders auf: konkrete Beispiele statt Behauptungen, Zahlen, Struktur
der Antwort (Situation, Handlung, Ergebnis), Umgang mit unangenehmen Fragen,
Schlechtreden frueherer Arbeitgeber, Laenge der Antworten.

War das Gespraech sehr kurz, sag das und werte nur, was da ist."""

    inhalt = (
        "STELLENANALYSE:\n" + json.dumps(analyse, ensure_ascii=False, indent=2)
        + "\n\nPROFIL:\n" + json.dumps(profil, ensure_ascii=False, indent=2)
        + "\n\nGESPRAECHSVERLAUF:\n"
        + "\n\n".join(f"{'GEGENUEBER' if z['rolle'] == 'recruiter' else 'BEWERBER'}: {z['text']}"
                      for z in verlauf)
    )
    return _json_antwort(system, inhalt, FEEDBACK_SCHEMA, max_tokens=16000)


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
