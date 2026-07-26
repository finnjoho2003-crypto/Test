"""Fuellt die HTML-Vorlagen des Skills und rendert sie nach PDF."""

from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "bewerbung"
VORLAGEN = SKILL / "assets"
SKRIPTE = SKILL / "scripts"

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


def _datum_lang() -> str:
    heute = date.today()
    return f"{heute.day}. {MONATE[heute.month - 1]} {heute.year}"


def e(text) -> str:
    """Escapt Text fuer HTML.

    Inhalte kommen aus Profil und Modellantwort und landen in einer HTML-Datei -
    ohne Escaping wuerde ein Ampersand oder eine spitze Klammer im Firmennamen
    das Dokument zerlegen.
    """
    return html.escape(str(text or ""), quote=True)


def _absatz(text: str) -> str:
    return e(text).replace("\n", "<br>")


# --------------------------------------------------------------------------- #
# Lebenslauf
# --------------------------------------------------------------------------- #

def baue_lebenslauf(inhalt: dict, person: dict, ort: str) -> str:
    vorlage = (VORLAGEN / "lebenslauf.html").read_text(encoding="utf-8")

    name = f"{person.get('vorname', '')} {person.get('nachname', '')}".strip()
    kopf = f"""<header class="kopf">
  <div>
    <h1 class="name">{e(name)}</h1>
    <p class="rolle">{e(inhalt.get('berufsbezeichnung', ''))}</p>
  </div>
  <div class="kontakt">
    <div>{e(person.get('strasse', ''))}</div>
    <div>{e(person.get('plz_ort', ''))}</div>
    <div><a href="mailto:{e(person.get('email', ''))}">{e(person.get('email', ''))}</a></div>
    <div>{e(person.get('telefon', ''))}</div>
    <div>{e(person.get('web', ''))}</div>
  </div>
</header>"""

    teile = [f"""<section>
  <h2>Profil</h2>
  <p style="margin:0">{_absatz(inhalt.get('kurzprofil', ''))}</p>
</section>"""]

    if inhalt.get("stationen"):
        eintraege = "\n".join(
            f"""  <div class="eintrag">
    <div class="zeit">{e(s.get('von', ''))} – {e(s.get('bis', ''))}</div>
    <div>
      <p class="titel">{e(s.get('position', ''))}</p>
      <p class="firma">{e(s.get('firma', ''))} <span class="ort">· {e(s.get('ort', ''))}</span></p>
      <ul class="punkte">{''.join(f'<li>{_zahlen_hervorheben(p)}</li>' for p in s.get('punkte', []))}</ul>
    </div>
  </div>""" for s in inhalt["stationen"])
        teile.append(f'<section>\n  <h2>Berufserfahrung</h2>\n{eintraege}\n</section>')

    if inhalt.get("ausbildung"):
        eintraege = "\n".join(
            f"""  <div class="eintrag">
    <div class="zeit">{e(a.get('von', ''))} – {e(a.get('bis', ''))}</div>
    <div>
      <p class="titel">{e(a.get('abschluss', ''))}</p>
      <p class="firma">{e(a.get('institut', ''))} <span class="ort">· {e(a.get('ort', ''))}</span></p>
      <ul class="punkte">{''.join(f'<li>{e(p)}</li>' for p in a.get('punkte', []))}</ul>
    </div>
  </div>""" for a in inhalt["ausbildung"])
        teile.append(f'<section>\n  <h2>Ausbildung</h2>\n{eintraege}\n</section>')

    for titel, schluessel, felder in (("Kenntnisse", "kenntnisse", ("kategorie", "werte")),
                                      ("Sprachen", "sprachen", ("sprache", "niveau"))):
        if inhalt.get(schluessel):
            zeilen = "\n".join(
                f'  <div class="skill-zeile"><div class="skill-label">{e(z.get(felder[0], ""))}</div>'
                f'<div class="skill-werte">{e(z.get(felder[1], ""))}</div></div>'
                for z in inhalt[schluessel])
            teile.append(f'<section>\n  <h2>{titel}</h2>\n{zeilen}\n</section>')

    fuss = f"""<footer class="fuss">
  <div>{e(ort)}, {_datum_lang()}</div>
  <div class="unterschrift"><div>{e(name)}</div></div>
</footer>"""

    dokument = re.sub(r'<header class="kopf">.*?</header>', lambda _: kopf,
                      vorlage, flags=re.S)
    start = dokument.index("<!-- ============ KURZPROFIL ============ -->")
    ende = dokument.index("<!-- ============ FUSS ============ -->")
    dokument = dokument[:start] + "\n\n".join(teile) + "\n\n" + dokument[ende:]
    dokument = re.sub(r'<footer class="fuss">.*?</footer>', lambda _: fuss,
                      dokument, flags=re.S)
    return dokument


def _zahlen_hervorheben(text: str) -> str:
    """Hebt Kennzahlen im Lebenslauf optisch hervor.

    Zahlen sind das, was beim Ueberfliegen haengenbleibt - ein halbfetter
    Prozentwert wird gelesen, derselbe Wert im Fliesstext nicht.
    """
    sicher = e(text)
    return re.sub(
        r"(\d[\d.,]*\s?(?:%|Prozent|Mio\.?|Mrd\.?|TEUR|EUR|€|Tage?|Monate?|Jahre?|Stunden?|Personen|Mitarbeitende?)?)",
        lambda m: f'<span class="kpi">{m.group(1)}</span>' if any(c.isdigit() for c in m.group(1)) else m.group(1),
        sicher, count=2)


# --------------------------------------------------------------------------- #
# Anschreiben
# --------------------------------------------------------------------------- #

def baue_anschreiben(inhalt: dict, person: dict, analyse: dict, ort: str) -> str:
    vorlage = (VORLAGEN / "anschreiben.html").read_text(encoding="utf-8")
    name = f"{person.get('vorname', '')} {person.get('nachname', '')}".strip()

    ersetzungen = {
        "{{VORNAME}} {{NACHNAME}}": e(name),
        "{{BERUFSBEZEICHNUNG}}": e(person.get("berufsbezeichnung", "")),
        "{{STRASSE}}, {{PLZ_ORT}}": f"{e(person.get('strasse', ''))}, {e(person.get('plz_ort', ''))}",
        "{{EMAIL}}": e(person.get("email", "")),
        "{{TELEFON}}": e(person.get("telefon", "")),
        "{{FIRMA}}": e(analyse.get("firma", "")),
        "{{ANSPRECHPARTNER}}": e(analyse.get("ansprechpartner", "")),
        "{{FIRMA_STRASSE}}": "",
        "{{FIRMA_PLZ_ORT}}": e(analyse.get("ort", "")),
        "{{ORT}}, {{DATUM}}": f"{e(ort)}, {_datum_lang()}",
        "Bewerbung als {{STELLENBEZEICHNUNG}}": e(inhalt.get("betreff", "")),
        "{{REFERENZNUMMER_UND_QUELLE}}": e(inhalt.get("referenzzeile", "")),
        "{{ANREDE}}": e(inhalt.get("anrede", "")),
        "{{EINSTIEG}}": _absatz(inhalt.get("einstieg", "")),
        "{{BELEG_ANFORDERUNG_1}}": _absatz(inhalt.get("beleg1", "")),
        "{{BELEG_ANFORDERUNG_2}}": _absatz(inhalt.get("beleg2", "")),
        "{{MOTIVATION}}": _absatz(inhalt.get("motivation", "")),
        "{{ABSCHLUSS}}": _absatz(inhalt.get("abschluss", "")),
        "{{ANLAGEN}}": e(inhalt.get("anlagen", "Lebenslauf, Zeugnisse")),
    }
    for suchen, ersetzen in ersetzungen.items():
        vorlage = vorlage.replace(suchen, ersetzen)

    # Leere Empfaengerzeile entfernen, damit kein Loch im Anschriftfeld bleibt.
    vorlage = re.sub(r"\n\s*<div></div>", "", vorlage)
    return vorlage


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

# Stufen zum Verdichten, falls ein Dokument ueber die gewuenschte Seitenzahl
# laeuft. Reihenfolge und Werte stammen aus den Kommentaren in den Vorlagen:
# erst Abstaende, dann Zeilenabstand, zuletzt die Schriftgroesse - und die nie
# so weit, dass das Dokument nicht mehr zu ueberfliegen ist. Lieber zwei Seiten
# als eine unlesbare.
VERDICHTUNG = {
    # Gleichmaessig gestaffelt: Jede Stufe muss spuerbar mehr bringen als die
    # vorige, sonst laeuft ein Brief, der nur wenig zu lang ist, bis zur
    # haertesten Stufe durch und sieht gequetscht aus, obwohl eine milde
    # gereicht haette.
    "anschreiben": [
        ".empfaenger { margin-top: 7mm; } .anlagen, .gruss { margin-top: 4mm; }"
        " body { line-height: 1.4; } p.text { margin-bottom: 2.8mm; }"
        " .betreff { margin-top: 5mm; }",
        ".empfaenger { margin-top: 6mm; } .anlagen, .gruss { margin-top: 3.5mm; }"
        " body { line-height: 1.36; font-size: 10.5pt; } p.text { margin-bottom: 2.5mm; }"
        " .betreff { margin-top: 4.5mm; } .anrede { margin-top: 4mm; }"
        " .datum { margin-top: 3mm; }",
        ".empfaenger { margin-top: 5mm; } .anlagen, .gruss { margin-top: 3mm; }"
        " body { line-height: 1.32; font-size: 10.3pt; } p.text { margin-bottom: 2.2mm; }"
        " .betreff { margin-top: 4mm; } .anrede { margin-top: 3.5mm; }"
        " .datum { margin-top: 2.5mm; } .briefkopf { padding-bottom: 2mm; }",
        "@page { margin: 15mm 18mm 13mm 22mm; }"
        " .empfaenger { margin-top: 4mm; } .anlagen, .gruss { margin-top: 2.5mm; }"
        " body { line-height: 1.28; font-size: 10.2pt; } p.text { margin-bottom: 2mm; }"
        " .betreff { margin-top: 3.5mm; } .anrede { margin-top: 3mm; }"
        " .datum { margin-top: 2mm; } .briefkopf { padding-bottom: 1.5mm; }"
        " .signatur { margin-top: 1.5mm; }",
    ],
    "lebenslauf": [
        "section { margin-top: 5mm; } .eintrag { margin-bottom: 3mm; }"
        " .fuss { margin-top: 4mm; }",
        "section { margin-top: 4.5mm; } .eintrag { margin-bottom: 2.6mm; }"
        " .fuss { margin-top: 3.5mm; } ul.punkte li { margin-bottom: 0.6mm; }",
        "section { margin-top: 4mm; } .eintrag { margin-bottom: 2.3mm; }"
        " .fuss { margin-top: 3mm; } ul.punkte li { margin-bottom: 0.5mm; }"
        " body { font-size: 10pt; line-height: 1.4; }",
    ],
}


def _mit_stufe(roh: str, css: str) -> str:
    """Haengt eine Verdichtungsstufe als letztes Stylesheet an.

    Als eigener Block direkt vor </head> - dadurch gewinnt er gegen die
    Vorlage, ohne dass an ihr etwas geaendert werden muesste. Die Vorlage
    bleibt so lesbar und die Verdichtung an einer Stelle nachvollziehbar.
    """
    block = f'<style id="verdichtung">\n{css}\n</style>\n</head>'
    return roh.replace("</head>", block, 1)


def rendere_begrenzt(pfad: Path, art: str, hart: int, weich: int = 0) -> int:
    """Rendert und verdichtet, bis das Dokument in `hart` Seiten passt.

    `hart` ist die Grenze, die nicht ueberschritten werden darf - dafuer werden
    alle Stufen ausgereizt. Ohne das war "eine Seite" eine Bitte an das Modell
    und keine Zusage: Ein Anschreiben, das um drei Zeilen zu lang ist, wandert
    sonst auf zwei Seiten, und ein zweiseitiges Anschreiben liest niemand zu
    Ende.

    `weich` ist die Wunschgroesse. Sie wird nur mit der ersten, schonendsten
    Stufe versucht - gegen die fast leere letzte Seite, die wie ein Fehler
    aussieht. Genuegt das nicht, ist der Inhalt wirklich laenger und darf auch
    danach aussehen; die Vorlage bleibt dann unangetastet.
    """
    urfassung = pfad.read_text(encoding="utf-8")
    stufen = VERDICHTUNG.get(art, [])
    name = pfad.with_suffix(".pdf").name

    def rendere(css: str | None) -> int:
        pfad.write_text(_mit_stufe(urfassung, css) if css else urfassung,
                        encoding="utf-8")
        return rendere_pdf([pfad]).get(name, 0)

    seiten = rendere(None)

    if weich and stufen and seiten > weich:
        versuch = rendere(stufen[0])
        if versuch and versuch <= weich:
            return versuch
        seiten = rendere(None)  # Zurueck auf Anfang, dann die harte Grenze.

    for css in stufen:
        if seiten and seiten <= hart:
            break
        seiten = rendere(css)

    # Passt es auch nach der letzten Stufe nicht, bleibt die kompakteste
    # Fassung stehen - sie ueberschreitet am wenigsten.
    return seiten


def rendere_pdf(html_pfade: list[Path]) -> dict[str, int]:
    """Rendert HTML nach PDF und gibt die Seitenzahl je Datei zurueck."""
    if not html_pfade:
        return {}
    ergebnis = subprocess.run(
        [sys.executable, str(SKRIPTE / "render_pdf.py"), *[str(p) for p in html_pfade]],
        capture_output=True, text=True, timeout=300,
    )
    seiten: dict[str, int] = {}
    for zeile in ergebnis.stdout.splitlines():
        treffer = re.search(r"✓ (\S+\.pdf).*?(\d+) Seite", zeile)
        if treffer:
            seiten[Path(treffer.group(1)).name] = int(treffer.group(2))
    if not seiten and ergebnis.returncode != 0:
        raise RuntimeError(f"PDF-Erzeugung fehlgeschlagen: {ergebnis.stderr[-500:]}")
    return seiten
