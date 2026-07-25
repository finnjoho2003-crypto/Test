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
    """
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    try:
        wert = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return False
    if wert:
        os.environ["ANTHROPIC_API_KEY"] = wert
        return True
    return False


def schluessel_speichern(wert: str) -> None:
    wert = (wert or "").strip()
    if not wert.startswith("sk-"):
        raise ValueError("Das sieht nicht nach einem API-Schluessel aus "
                         "(er beginnt mit 'sk-ant-').")
    with _lock:
        SCHLUESSEL_DATEI.parent.mkdir(parents=True, exist_ok=True)
        SCHLUESSEL_DATEI.write_text(wert, encoding="utf-8")
        # Nur fuer die eigene Nutzerin lesbar - es ist ein Zugangsdatum.
        try:
            os.chmod(SCHLUESSEL_DATEI, 0o600)
        except OSError:
            pass
    os.environ["ANTHROPIC_API_KEY"] = wert


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


def profil_lesen() -> dict:
    daten = _lade(PROFIL, {})
    # Fehlende Abschnitte auffuellen, damit das Frontend nie auf None trifft.
    profil = json.loads(json.dumps(LEERES_PROFIL))
    for schluessel, wert in daten.items():
        if schluessel in profil and isinstance(profil[schluessel], dict):
            profil[schluessel].update(wert or {})
        else:
            profil[schluessel] = wert
    return profil


def profil_schreiben(daten: dict) -> dict:
    with _lock:
        profil = profil_lesen()
        for schluessel, wert in (daten or {}).items():
            if schluessel in LEERES_PROFIL:
                profil[schluessel] = wert
        profil["aktualisiert"] = _jetzt()
        _speichere(PROFIL, profil)
    return profil


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
        eintrag = {
            "id": bewerbung_id,
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
