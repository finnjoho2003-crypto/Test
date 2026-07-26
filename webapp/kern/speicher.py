"""Ablage auf der Festplatte: Profil und Bewerbungen als JSON.

Bewusst keine Datenbank. Die Datenmenge ist klein, und der grosse Vorteil von
einfachen Dateien ist hier die Nachvollziehbarkeit: Wer wissen will, was das
Tool gespeichert hat, oeffnet den Ordner. Die persoenlichen Daten bleiben damit
sichtbar und loeschbar, statt in einer Binaerdatei zu verschwinden.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Alles liegt unter <projekt>/bewerbung/ - dieser Ordner steht in .gitignore.
BASIS = Path(os.environ.get("BEWERBUNG_DATA", Path(__file__).resolve().parents[2] / "bewerbung"))
PROFIL = BASIS / "profil.json"
BEWERBUNGEN = BASIS / "bewerbungen"

STATUS = ["entwurf", "gesendet", "gespraech", "zusage", "absage"]

# Schreibzugriffe laufen aus mehreren Threads (Hintergrund-Pipeline und
# HTTP-Anfragen gleichzeitig), deshalb ein Lock um die Schreibpfade.
_lock = threading.RLock()


SCHLUESSEL_DATEI = BASIS / "schluessel.txt"


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# API-Schluessel
# --------------------------------------------------------------------------- #

def schluessel_laden() -> bool:
    """Legt einen gespeicherten Schluessel in die Umgebung. True, wenn einer da ist.

    Ohne das muesste die Person bei jedem Start eine Umgebungsvariable setzen -
    fuer die meisten die groesste Huerde ueberhaupt. Einmal eintragen genuegt.

    Die eingetragene Datei hat Vorrang vor der Umgebungsvariable. Das ist kein
    Detail: Setzt die Umgebung einen alten oder unvollstaendigen Schluessel
    (etwa ein Codespace-Secret mit Tippfehler), galt frueher dieser - und die
    Oberflaeche zeigte gar kein Eingabefeld mehr an, weil ja "ein Schluessel da
    war". Der Fehler liess sich dann ueberhaupt nicht mehr korrigieren. Wer
    zuletzt bewusst etwas eingetragen hat, gewinnt.
    """
    try:
        wert = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
    except OSError:
        wert = ""
    if wert:
        os.environ["ANTHROPIC_API_KEY"] = wert
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def pruefe_form(wert: str) -> str:
    """Prueft die Gestalt des Schluessels, ohne das Netz zu bemuehen.

    Die haeufigsten Fehler beim Kopieren aus der Konsole lassen sich hier schon
    erkennen und praezise benennen. Kommt derselbe Fehler erst als "401 -
    invalid" mitten in einer Bewerbung zurueck, sagt er nichts darueber, was
    schiefging.
    """
    wert = (wert or "").strip()
    if not wert.startswith("sk-"):
        raise ValueError("Das sieht nicht nach einem API-Schluessel aus "
                         "(er beginnt mit 'sk-ant-').")
    if any(zeichen.isspace() for zeichen in wert):
        raise ValueError("Im Schluessel steht ein Leerzeichen oder Zeilenumbruch. "
                         "Bitte noch einmal vollstaendig kopieren und einfuegen.")
    if len(wert) < 40:
        raise ValueError("Der Schluessel ist zu kurz - beim Kopieren ist wohl "
                         "das Ende abgeschnitten worden. Bitte vollstaendig "
                         "einfuegen (er ist rund 100 Zeichen lang).")
    return wert


def schluessel_speichern(wert: str) -> None:
    wert = pruefe_form(wert)
    with _lock:
        SCHLUESSEL_DATEI.parent.mkdir(parents=True, exist_ok=True)
        SCHLUESSEL_DATEI.write_text(wert, encoding="utf-8")
        # Nur fuer die eigene Nutzerin lesbar - es ist ein Zugangsdatum.
        try:
            os.chmod(SCHLUESSEL_DATEI, 0o600)
        except OSError:
            pass
    os.environ["ANTHROPIC_API_KEY"] = wert
    # Sonst gewinnt ein gesetztes Bearer-Token im SDK und der gerade
    # eingetragene Schluessel wird gar nicht erst verschickt.
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


def schluessel_vorhanden() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or SCHLUESSEL_DATEI.exists())


def _lade(pfad: Path, standard):
    try:
        with open(pfad, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return standard


def _speichere(pfad: Path, daten) -> None:
    """Schreibt atomar: erst in eine Nebendatei, dann umbenennen.

    Ein abgebrochener Schreibvorgang wuerde sonst eine halbe JSON-Datei
    hinterlassen - und damit im Zweifel das gesamte Profil unlesbar machen.
    """
    pfad.parent.mkdir(parents=True, exist_ok=True)
    temp = pfad.with_suffix(pfad.suffix + ".tmp")
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, indent=2, ensure_ascii=False)
    temp.replace(pfad)


# --------------------------------------------------------------------------- #
# Profil
# --------------------------------------------------------------------------- #

LEERES_PROFIL = {
    "person": {"vorname": "", "nachname": "", "strasse": "", "plz_ort": "",
               "email": "", "telefon": "", "web": "", "berufsbezeichnung": ""},
    "situation": {"verfuegbar_ab": "", "gehaltsvorstellung": "", "umzug": "",
                  "wechselgrund": ""},
    "kurzprofil": "",
    "stationen": [],   # {position, firma, ort, von, bis, aufgaben, erfolge, tools}
    "ausbildung": [],  # {abschluss, institut, ort, von, bis, note, schwerpunkt}
    "kenntnisse": [],  # {kategorie, werte}
    "sprachen": [],    # {sprache, niveau}
    "weiteres": "",
    "luecken": "",
}


PROFILE = BASIS / "profile"
ZUSTAND = BASIS / "zustand.json"


def _profil_pfad(profil_id: str) -> Path:
    # Wie bei den Bewerbungen: Ein Dateiname aus einer Anfrage darf niemals
    # ungeprueft in einen Pfad wandern.
    if not re.fullmatch(r"[0-9a-f]{8,32}", profil_id or ""):
        raise ValueError("ungueltige Profil-ID")
    return PROFILE / f"{profil_id}.json"


def _fuelle(daten: dict) -> dict:
    """Fehlende Abschnitte auffuellen, damit das Frontend nie auf None trifft."""
    profil = json.loads(json.dumps(LEERES_PROFIL))
    for schluessel, wert in (daten or {}).items():
        if schluessel in profil and isinstance(profil[schluessel], dict):
            profil[schluessel].update(wert or {})
        else:
            profil[schluessel] = wert
    return profil


def _wandere_um() -> None:
    """Uebernimmt ein einzelnes altes profil.json als erstes benanntes Profil.

    Laeuft still und nur einmal. Wer das Tool schon benutzt hat, soll nach dem
    Update sein Profil vorfinden und nicht vor einer leeren Maske sitzen -
    Daten geraeuschlos zu verlieren waere das Schlimmste, was hier passieren
    kann.
    """
    if PROFILE.exists() and any(PROFILE.glob("*.json")):
        return
    altes = _lade(PROFIL, None)
    PROFILE.mkdir(parents=True, exist_ok=True)
    profil_id = uuid.uuid4().hex[:12]
    profil = _fuelle(altes or {})
    person = profil.get("person", {})
    profil["id"] = profil_id
    profil["name"] = (f"{person.get('vorname', '')} {person.get('nachname', '')}".strip()
                      or "Mein Profil")
    profil["erstellt"] = _jetzt()
    _speichere(_profil_pfad(profil_id), profil)
    _speichere(ZUSTAND, {"aktives_profil": profil_id})
    if altes is not None:
        # Die alte Datei bleibt als Sicherheitskopie liegen - sie kostet nichts
        # und ist die einzige Ruecklaufmoeglichkeit, falls hier etwas schieflief.
        PROFIL.replace(PROFIL.with_name("profil.json.vor-umstellung"))


def profile_liste() -> list[dict]:
    """Alle Profile, nur mit dem, was zur Auswahl noetig ist."""
    with _lock:
        _wandere_um()
    eintraege = []
    for pfad in sorted(PROFILE.glob("*.json")):
        daten = _lade(pfad, None)
        if not daten:
            continue
        person = daten.get("person", {})
        eintraege.append({
            "id": daten.get("id") or pfad.stem,
            "name": daten.get("name") or "Ohne Namen",
            "rolle": person.get("berufsbezeichnung", ""),
            "vollstaendig": not profil_vollstaendig(daten),
            "erstellt": daten.get("erstellt", ""),
        })
    eintraege.sort(key=lambda e: e.get("erstellt", ""))
    return eintraege


def aktives_profil_id() -> str:
    with _lock:
        _wandere_um()
        gewaehlt = (_lade(ZUSTAND, {}) or {}).get("aktives_profil", "")
        if gewaehlt and _profil_pfad(gewaehlt).is_file():
            return gewaehlt
        # Zeigt der Verweis ins Leere - geloeschtes Profil, von Hand
        # aufgeraeumt -, faellt die Wahl auf das erste vorhandene, statt die
        # Oberflaeche mit einem leeren Profil dastehen zu lassen.
        vorhanden = sorted(PROFILE.glob("*.json"))
        if not vorhanden:
            return ""
        neu = vorhanden[0].stem
        _speichere(ZUSTAND, {"aktives_profil": neu})
        return neu


def profil_lesen(profil_id: str = "") -> dict:
    profil_id = profil_id or aktives_profil_id()
    if not profil_id:
        return _fuelle({})
    return _fuelle(_lade(_profil_pfad(profil_id), {}))


def profil_schreiben(daten: dict, profil_id: str = "") -> dict:
    with _lock:
        profil_id = profil_id or aktives_profil_id()
        if not profil_id:
            return profil_anlegen((daten or {}).get("name") or "Mein Profil", daten)
        profil = profil_lesen(profil_id)
        for schluessel, wert in (daten or {}).items():
            if schluessel in LEERES_PROFIL:
                profil[schluessel] = wert
        if (daten or {}).get("name"):
            profil["name"] = str(daten["name"]).strip()[:60]
        profil["id"] = profil_id
        profil["aktualisiert"] = _jetzt()
        _speichere(_profil_pfad(profil_id), profil)
    return profil


def profil_anlegen(name: str, daten: dict | None = None) -> dict:
    with _lock:
        _wandere_um()
        profil_id = uuid.uuid4().hex[:12]
        profil = _fuelle(daten or {})
        profil["id"] = profil_id
        profil["name"] = (name or "").strip()[:60] or "Neues Profil"
        profil["erstellt"] = _jetzt()
        PROFILE.mkdir(parents=True, exist_ok=True)
        _speichere(_profil_pfad(profil_id), profil)
        _speichere(ZUSTAND, {"aktives_profil": profil_id})
    return profil


# --------------------------------------------------------------------------- #
# Bewerbungsfoto
# --------------------------------------------------------------------------- #

# Erkennung an den ersten Bytes statt am Dateinamen: Wie eine Datei heisst,
# sagt nichts darueber, was drinsteht. Nur diese beiden Formate, weil nur sie
# in jedem PDF-Betrachter zuverlaessig ankommen.
BILDARTEN = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
)
FOTO_MAX = 8 * 1024 * 1024


def foto_pfad(profil_id: str) -> Path | None:
    for _, endung, _ in BILDARTEN:
        pfad = PROFILE / f"{profil_id}-foto.{endung}"
        if pfad.is_file():
            return pfad
    return None


def foto_speichern(profil_id: str, rohdaten: bytes) -> str:
    """Legt das Bewerbungsfoto ab. Gibt die Endung zurueck."""
    if not rohdaten:
        raise ValueError("Es wurden keine Bilddaten empfangen.")
    if len(rohdaten) > FOTO_MAX:
        raise ValueError("Das Bild ist groesser als 8 MB. Bitte ein kleineres "
                         "waehlen - fuer den Lebenslauf genuegt eine kleine Datei.")
    for kennung, endung, _ in BILDARTEN:
        if rohdaten.startswith(kennung):
            break
    else:
        raise ValueError("Nur JPG und PNG werden unterstuetzt. Andere Formate "
                         "erscheinen im PDF nicht zuverlaessig.")
    with _lock:
        _profil_pfad(profil_id)  # Gegenprobe auf die Form der ID
        PROFILE.mkdir(parents=True, exist_ok=True)
        # Erst das alte in jedem Format entfernen, sonst liegen nach einem
        # Wechsel von PNG auf JPG beide da und es gilt das falsche.
        foto_loeschen(profil_id)
        (PROFILE / f"{profil_id}-foto.{endung}").write_bytes(rohdaten)
    return endung


def foto_loeschen(profil_id: str) -> bool:
    weg = False
    for _, endung, _ in BILDARTEN:
        pfad = PROFILE / f"{profil_id}-foto.{endung}"
        if pfad.is_file():
            pfad.unlink()
            weg = True
    return weg


def foto_als_datenadresse(profil_id: str) -> str:
    """Das Foto als eingebettete Datenadresse fuer die HTML-Vorlage.

    Eingebettet statt verlinkt, damit das Dokument eine einzelne Datei bleibt -
    ein Lebenslauf, dessen Bild beim Verschieben verschwindet, waere schlimmer
    als gar keines.
    """
    pfad = foto_pfad(profil_id)
    if not pfad:
        return ""
    typ = next(t for _, e, t in BILDARTEN if pfad.suffix.lstrip(".") == e)
    import base64  # noqa: PLC0415
    return f"data:{typ};base64," + base64.b64encode(pfad.read_bytes()).decode("ascii")


def profil_waehlen(profil_id: str) -> bool:
    with _lock:
        if not _profil_pfad(profil_id).is_file():
            return False
        _speichere(ZUSTAND, {"aktives_profil": profil_id})
    return True


def profil_loeschen(profil_id: str) -> bool:
    """Loescht ein Profil. Das letzte bleibt bestehen.

    Ohne Profil laesst sich keine Bewerbung erstellen; ein Programm, das sich
    per Klick in einen unbrauchbaren Zustand bringen laesst, ist ein
    schlechtes Programm. Bereits erstellte Bewerbungen bleiben unberuehrt -
    ihre Dokumente sind fertig und sollen es bleiben.
    """
    with _lock:
        pfad = _profil_pfad(profil_id)
        if not pfad.is_file() or len(list(PROFILE.glob("*.json"))) <= 1:
            return False
        pfad.unlink()
        foto_loeschen(profil_id)
        if (_lade(ZUSTAND, {}) or {}).get("aktives_profil") == profil_id:
            rest = sorted(PROFILE.glob("*.json"))
            _speichere(ZUSTAND, {"aktives_profil": rest[0].stem if rest else ""})
    return True


def profil_vollstaendig(profil: dict) -> list[str]:
    """Nennt die Felder, ohne die keine Bewerbung erzeugt werden kann.

    Die Pruefung ist absichtlich streng: Fehlt der Werdegang, koennte das Tool
    nur noch erfinden - und genau das soll es nie tun.
    """
    fehlt = []
    person = profil.get("person", {})
    for feld, name in (("vorname", "Vorname"), ("nachname", "Nachname"),
                       ("email", "E-Mail")):
        if not (person.get(feld) or "").strip():
            fehlt.append(name)
    if not profil.get("stationen") and not profil.get("ausbildung"):
        fehlt.append("mindestens eine Station oder Ausbildung")
    return fehlt


# --------------------------------------------------------------------------- #
# Bewerbungen
# --------------------------------------------------------------------------- #

def _ordner(bewerbung_id: str) -> Path:
    # Ordnernamen nie ungeprueft aus einer Anfrage bauen - sonst reicht ein
    # "../" in der ID, um ausserhalb des Datenordners zu schreiben.
    if not re.fullmatch(r"[0-9a-f]{8,32}", bewerbung_id or ""):
        raise ValueError("ungueltige Bewerbungs-ID")
    return BEWERBUNGEN / bewerbung_id


def bewerbung_anlegen(url: str, titel: str = "") -> dict:
    with _lock:
        bewerbung_id = uuid.uuid4().hex[:12]
        # Festhalten, mit welchem Profil die Bewerbung entstanden ist. Wird
        # spaeter gewechselt, muss ein Wiederholungslauf trotzdem dieselbe
        # Person verwenden - sonst stuende auf einmal ein fremder Werdegang in
        # einer bereits verschickten Bewerbung.
        aktiv = aktives_profil_id()
        eintrag = {
            "id": bewerbung_id,
            "profil_id": aktiv,
            "profil_name": profil_lesen(aktiv).get("name", "") if aktiv else "",
            "url": url,
            "titel": titel or "Wird analysiert …",
            "firma": "",
            "ort": "",
            "status": "entwurf",
            "phase": "warteschlange",
            "fortschritt": 0,
            "fehler": "",
            "notiz": "",
            "erstellt": _jetzt(),
            "aktualisiert": _jetzt(),
            "dateien": {},
            "analyse": {},
            "brand": {},
            "luecken": [],
            "passung": "",
        }
        _ordner(bewerbung_id).mkdir(parents=True, exist_ok=True)
        _speichere(_ordner(bewerbung_id) / "meta.json", eintrag)
    return eintrag


def bewerbung_lesen(bewerbung_id: str) -> dict | None:
    return _lade(_ordner(bewerbung_id) / "meta.json", None)


def bewerbung_aktualisieren(bewerbung_id: str, **felder) -> dict | None:
    with _lock:
        eintrag = bewerbung_lesen(bewerbung_id)
        if eintrag is None:
            return None
        eintrag.update(felder)
        eintrag["aktualisiert"] = _jetzt()
        _speichere(_ordner(bewerbung_id) / "meta.json", eintrag)
    return eintrag


def bewerbung_loeschen(bewerbung_id: str) -> bool:
    with _lock:
        ordner = _ordner(bewerbung_id)
        if not ordner.exists():
            return False
        shutil.rmtree(ordner)
    return True


def bewerbungen_liste() -> list[dict]:
    if not BEWERBUNGEN.exists():
        return []
    eintraege = []
    for ordner in BEWERBUNGEN.iterdir():
        if ordner.is_dir():
            eintrag = _lade(ordner / "meta.json", None)
            if eintrag:
                eintraege.append(eintrag)
    eintraege.sort(key=lambda e: e.get("erstellt", ""), reverse=True)
    return eintraege


def datei_pfad(bewerbung_id: str, name: str) -> Path:
    """Pfad einer Artefaktdatei - nur flache Namen, kein Verzeichniswechsel."""
    sauber = Path(name).name
    if not sauber or sauber.startswith("."):
        raise ValueError("ungueltiger Dateiname")
    return _ordner(bewerbung_id) / sauber


def kennzahlen() -> dict:
    eintraege = bewerbungen_liste()
    nach_status = {s: 0 for s in STATUS}
    for eintrag in eintraege:
        status = eintrag.get("status", "entwurf")
        if status in nach_status:
            nach_status[status] += 1
    im_rennen = nach_status["gesendet"] + nach_status["gespraech"]
    beantwortet = nach_status["gespraech"] + nach_status["zusage"] + nach_status["absage"]
    return {
        "gesamt": len(eintraege),
        "nach_status": nach_status,
        "im_rennen": im_rennen,
        # Antwortquote nur zeigen, wenn ueberhaupt etwas verschickt wurde -
        # "0 %" bei null Bewerbungen ist keine Information, sondern Entmutigung.
        "quote": round(100 * beantwortet / max(1, nach_status["gesendet"]
                                               + beantwortet)) if beantwortet else None,
    }
