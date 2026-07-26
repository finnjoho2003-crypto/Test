"""Der Ablauf von der Stellen-URL bis zu den fertigen Unterlagen.

Laeuft in einem Hintergrund-Thread, weil die Modellaufrufe zusammen ein bis zwei
Minuten dauern. Der Fortschritt landet in meta.json; das Frontend fragt ihn ab.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import traceback
import urllib.parse
from pathlib import Path

from . import claude, dokumente, speicher

SKRIPTE = dokumente.SKRIPTE

SCHRITTE = [
    ("anzeige", "Stellenanzeige laden", 10),
    ("analyse", "Anforderungen analysieren", 30),
    ("design", "Firmendesign ableiten", 45),
    ("texte", "Unterlagen texten", 70),
    ("pdf", "PDF erzeugen", 85),
    ("gespraech", "Gespraechsvorbereitung", 100),
]


def _melde(bewerbung_id: str, phase: str, fortschritt: int) -> None:
    speicher.bewerbung_aktualisieren(bewerbung_id, phase=phase, fortschritt=fortschritt)


def _text_von_url(url: str) -> str:
    """Holt die Anzeige und macht daraus lesbaren Text.

    Nutzt den Fetcher des Skills, damit Proxy, Zeitlimit und Teilinhalt-Logik
    nur an einer Stelle gepflegt werden muessen.
    """
    sys.path.insert(0, str(SKRIPTE))
    try:
        import extract_brand  # noqa: PLC0415 - bewusst spaet, Pfad muss stehen
        _, roh = extract_brand.fetch(url, timeout=30)
    finally:
        sys.path.pop(0)

    if not roh:
        raise RuntimeError(
            "Die Anzeige liess sich nicht laden. Viele Jobboersen sperren "
            "automatisierte Zugriffe - bitte den Anzeigentext einfuegen."
        )

    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", roh)
    text = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h[1-6])\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
                .replace("&#39;", "'"))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


BOERSEN = ("stepstone", "indeed", "linkedin", "xing", "monster", "glassdoor",
           "kununu", "arbeitsagentur", "jobware", "meinestadt", "jobs.",
           "softgarden", "personio", "workday", "successfactors", "greenhouse",
           "lever.co", "smartrecruiters", "join.com", "empfehlungsbund")

RECHTSFORMEN = re.compile(
    r"\b(gmbh|mbh|ag|se|kg|ohg|gbr|ug|e\.?\s?v|e\.?\s?k|co\.?|kgaa|"
    r"holding|group|gruppe|deutschland|germany|inc|ltd|llc|plc|nv|bv|sa)\b",
    re.I)


def _namensteil(firma: str) -> str:
    """Macht aus 'Muster Technik GmbH & Co. KG' -> 'mustertechnik'."""
    name = firma.lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        name = name.replace(alt, neu)
    name = RECHTSFORMEN.sub(" ", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def _firmen_website(analyse: dict, job_url: str) -> str:
    """Bestimmt die Startseite der Firma - nicht die der Jobboerse."""
    kandidat = (analyse.get("firma_website") or "").strip()
    if kandidat:
        if not urllib.parse.urlparse(kandidat).scheme:
            kandidat = "https://" + kandidat
        return kandidat

    host = urllib.parse.urlparse(job_url).netloc.lower()
    if host and not any(b in host for b in BOERSEN):
        return f"https://{host}"

    # Die Anzeige stand auf einer Jobboerse - dort ist nichts ueber das Design
    # der Firma zu holen. Aus dem Firmennamen laesst sich die Adresse aber oft
    # erraten. Geraten wird nur, was sich anschliessend bestaetigen laesst:
    # Die Seite muss den Namen auch tatsaechlich enthalten. Sonst landet das
    # Design irgendeiner fremden Firma im Lebenslauf.
    kern = _namensteil(analyse.get("firma", ""))
    if len(kern) < 4:
        return ""

    sys.path.insert(0, str(SKRIPTE))
    try:
        import extract_brand  # noqa: PLC0415
        for endung in (".de", ".com", ".net", ".at", ".ch"):
            adresse = f"https://www.{kern}{endung}"
            try:
                _, roh = extract_brand.fetch(adresse, timeout=12)
            except Exception:  # noqa: BLE001 - jeder Fehlversuch ist nur ein Nein
                continue
            if roh and kern[:6] in _namensteil(roh[:200000]):
                return adresse
    finally:
        sys.path.pop(0)
    return ""


def _design(bewerbung_id: str, website: str, ordner: Path) -> tuple[dict, str]:
    """Leitet die Hausfarben ab.

    Scheitert nie hart - die Standardpalette sieht ordentlich aus. Der Grund
    wird aber zurueckgegeben und angezeigt: Bleibt das Design unerklaert aus,
    wirkt es wie ein defektes Programm.
    """
    if not website:
        return {}, ("Die Firmenwebsite liess sich aus der Anzeige nicht "
                    "ermitteln - vermutlich stammt sie von einer Jobboerse. "
                    "Trage sie im Feld unten ein und starte neu, dann wird "
                    "das Design uebernommen.")
    ergebnis = subprocess.run(
        [sys.executable, str(SKRIPTE / "extract_brand.py"), website,
         "-o", str(ordner / "brand.json"),
         "--emit-css", str(ordner / "theme.css"), "--timeout", "30"],
        capture_output=True, text=True, timeout=180,
    )
    if ergebnis.returncode != 0 or not (ordner / "brand.json").exists():
        return {}, (f"{website} liess sich nicht auswerten "
                    f"({(ergebnis.stderr or '').strip()[-160:] or 'kein Zugriff'}). "
                    "Es gilt die Standardgestaltung.")
    import json  # noqa: PLC0415
    with open(ordner / "brand.json", encoding="utf-8") as fh:
        return json.load(fh), ""


def _lauf(bewerbung_id: str, anzeigentext: str | None) -> None:
    eintrag = speicher.bewerbung_lesen(bewerbung_id)
    if eintrag is None:
        return
    ordner = speicher.datei_pfad(bewerbung_id, "x").parent
    profil = speicher.profil_lesen()

    try:
        # 1 - Anzeige
        _melde(bewerbung_id, "Stellenanzeige laden", 10)
        # Beim Wiederholen liegt die Anzeige schon im Ordner. Sie von dort zu
        # nehmen spart nicht nur einen Abruf: Wurde der Text urspruenglich von
        # Hand eingefuegt, gibt es gar keine Adresse, von der er sich erneut
        # holen liesse - der zweite Lauf waere sonst zum Scheitern verurteilt.
        gespeichert = ordner / "anzeige.txt"
        if anzeigentext:
            text = anzeigentext.strip()
        elif gespeichert.is_file():
            text = gespeichert.read_text(encoding="utf-8").strip()
        else:
            text = _text_von_url(eintrag["url"])
        if len(text) < 200:
            raise RuntimeError("Der Anzeigentext ist zu kurz für eine Analyse.")
        (ordner / "anzeige.txt").write_text(text, encoding="utf-8")

        # 2 - Analyse
        _melde(bewerbung_id, "Anforderungen analysieren", 30)
        analyse = claude.analysiere_stelle(text, eintrag["url"])
        speicher.bewerbung_aktualisieren(
            bewerbung_id, analyse=analyse,
            titel=analyse.get("position") or eintrag["titel"],
            firma=analyse.get("firma", ""), ort=analyse.get("ort", ""))

        # 3 - Design
        _melde(bewerbung_id, "Firmendesign ableiten", 45)
        # Eine von Hand eingetragene Adresse schlaegt jede Ermittlung: Sie kommt
        # von der Person, die die Firma kennt.
        website = (eintrag.get("firma_website") or "").strip() \
            or _firmen_website(analyse, eintrag["url"])
        brand, design_hinweis = _design(bewerbung_id, website, ordner)
        speicher.bewerbung_aktualisieren(bewerbung_id, brand=brand,
                                         firma_website=website,
                                         design_hinweis=design_hinweis)

        # 4 - Texte
        _melde(bewerbung_id, "Unterlagen texten", 70)
        unterlagen = claude.erstelle_unterlagen(analyse, profil)

        person = profil.get("person", {})
        ort = (person.get("plz_ort", "").split(maxsplit=1) or [""])[-1] or person.get("plz_ort", "")
        (ordner / "lebenslauf.html").write_text(
            dokumente.baue_lebenslauf(unterlagen["lebenslauf"], person, ort), encoding="utf-8")
        (ordner / "anschreiben.html").write_text(
            dokumente.baue_anschreiben(unterlagen["anschreiben"], person, analyse, ort),
            encoding="utf-8")

        # 5 - PDF
        _melde(bewerbung_id, "PDF erzeugen", 85)
        # Das Anschreiben muss auf eine Seite - nicht "moeglichst". Der
        # Lebenslauf darf zwei haben, soll aber nicht wegen dreier Zeilen auf
        # eine dritte rutschen und keine fast leere Seite hinterlassen.
        seiten = {
            "anschreiben.pdf": dokumente.rendere_begrenzt(
                ordner / "anschreiben.html", "anschreiben", hart=1),
            "lebenslauf.pdf": dokumente.rendere_begrenzt(
                ordner / "lebenslauf.html", "lebenslauf", hart=2, weich=1),
        }

        nachname = person.get("nachname", "Bewerbung") or "Bewerbung"
        vorname = person.get("vorname", "") or ""
        dateien = {}
        for quelle, art in (("anschreiben", "Anschreiben"), ("lebenslauf", "Lebenslauf")):
            pdf = ordner / f"{quelle}.pdf"
            if pdf.exists():
                dateien[art] = {
                    "datei": pdf.name,
                    "download": f"{nachname}_{vorname}_{art}.pdf".replace(" ", ""),
                    "seiten": seiten.get(pdf.name, 0),
                }

        speicher.bewerbung_aktualisieren(
            bewerbung_id, dateien=dateien,
            luecken=unterlagen.get("luecken", []),
            passung=unterlagen.get("passung", ""),
            passung_begruendung=unterlagen.get("passung_begruendung", ""))

        # 6 - Gespraech
        _melde(bewerbung_id, "Gespraechsvorbereitung", 95)
        briefing = claude.gespraechs_briefing(analyse, profil, unterlagen.get("luecken", []))
        (ordner / "gespraech.md").write_text(briefing, encoding="utf-8")

        speicher.bewerbung_aktualisieren(bewerbung_id, phase="fertig", fortschritt=100,
                                         fehler="")
    except Exception as fehler:  # noqa: BLE001 - jeder Fehler gehoert in die UI
        traceback.print_exc()
        # In die Oberflaeche gehoert ein Satz, aus dem hervorgeht, was zu tun
        # ist - nicht der englische Rohtext des SDK samt Statuscode.
        speicher.bewerbung_aktualisieren(
            bewerbung_id, phase="fehler", fehler=claude.klartext(fehler))


def starten(bewerbung_id: str, anzeigentext: str | None = None) -> None:
    threading.Thread(target=_lauf, args=(bewerbung_id, anzeigentext), daemon=True).start()
