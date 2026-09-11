#!/usr/bin/env python3
"""Rendert HTML-Bewerbungsunterlagen ueber Headless-Chromium nach PDF.

    python3 render_pdf.py lebenslauf.html [-o lebenslauf.pdf]
    python3 render_pdf.py anschreiben.html lebenslauf.html   # mehrere auf einmal

Chromium wird genommen, weil es modernes CSS (Grid, Flexbox, @page) genau so
darstellt wie im Browser - die Vorlagen lassen sich damit im Browser
kontrollieren und sehen im PDF identisch aus. Seitenraender kommen aus der
@page-Regel im HTML, nicht von der Kommandozeile.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CANDIDATES = [
    # Linux
    "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/snap/bin/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Windows. Edge steht bewusst mit in der Liste: Es ist auf jedem Windows
    # vorinstalliert und beruht auf derselben Grundlage - damit gelingt die
    # PDF-Ausgabe auch dann, wenn Chrome nie installiert wurde.
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _laeuft(pfad: str) -> bool:
    """Prueft, ob der gefundene Browser tatsaechlich startet.

    Notwendig, nicht vorsichtshalber: Auf Ubuntu ist /usr/bin/chromium-browser
    ueblicherweise nur eine Huelle, die auf das Snap-Paket verweist und ohne
    dieses mit einer Fehlermeldung abbricht. Wer nur den Pfad prueft, findet
    sie zuerst und erzeugt danach kein einziges PDF - mit einer Meldung, die
    nach einem Fehler im Programm aussieht statt nach einem fehlenden Paket.
    """
    try:
        return subprocess.run([pfad, "--version"], capture_output=True,
                              timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_chromium() -> str:
    kandidaten = []
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome",
                 "msedge"):
        gefunden = shutil.which(name)
        if gefunden:
            kandidaten.append(gefunden)
    for pattern in CANDIDATES:
        # Windows-Pfade enthalten Umgebungsvariablen wie %LOCALAPPDATA%.
        kandidaten.extend(sorted(glob.glob(os.path.expandvars(pattern))))

    for pfad in kandidaten:
        if _laeuft(pfad):
            return pfad
    raise SystemExit(
        "Kein Chrome, Chromium oder Edge gefunden. Bitte einen davon "
        "installieren oder den Pfad ueber die Umgebungsvariable CHROMIUM_BIN "
        "setzen. Alles andere funktioniert auch ohne - nur die PDF-Ausgabe "
        "braucht einen dieser Browser."
    )


LINK = re.compile(
    r"""<link[^>]*rel=["']?stylesheet["']?[^>]*href=["']([^"'>]+)["'][^>]*>"""
    r"""|<link[^>]*href=["']([^"'>]+)["'][^>]*rel=["']?stylesheet["']?[^>]*>""",
    re.I)


def stylesheets_einbetten(html_path: Path) -> str:
    """Ersetzt <link rel=stylesheet> durch den Inhalt der Datei.

    Notwendig, nicht kosmetisch: Chromium laedt im Druckmodus ueber eine
    file://-Adresse keine verlinkten Stylesheets aus demselben Ordner. Ohne
    diesen Schritt blieb theme.css - also die aus der Firmenwebsite
    abgeleitete Farbgebung - wirkungslos, und jedes Dokument sah gleich aus,
    obwohl die Farben korrekt ermittelt worden waren. Der Fehler ist von aussen
    nicht zu sehen: Es fehlt keine Datei, es kommt keine Meldung, das PDF ist
    nur einfach nicht eingefaerbt.

    Fehlt eine Datei, verschwindet der Verweis ersatzlos - im Dokument stehen
    Ausweichfarben bereit, es bleibt also immer lesbar.
    """
    roh = html_path.read_text(encoding="utf-8")

    def ersetze(treffer: re.Match) -> str:
        ziel = treffer.group(1) or treffer.group(2) or ""
        if "//" in ziel or ziel.startswith("data:"):
            return treffer.group(0)  # Externes bleibt, wie es ist.
        datei = (html_path.parent / ziel).resolve()
        # Nicht ausserhalb des Dokumentordners lesen - der Pfad kann aus einer
        # Vorlage stammen, die nicht selbst geschrieben wurde.
        if html_path.parent.resolve() not in datei.parents or not datei.is_file():
            return ""
        return f"<style data-quelle=\"{ziel}\">\n{datei.read_text(encoding='utf-8')}\n</style>"

    return LINK.sub(ersetze, roh)


def render(html_path: Path, pdf_path: Path, binary: str, timeout: int = 120) -> None:
    if not html_path.exists():
        raise SystemExit(f"HTML nicht gefunden: {html_path}")

    # Im selben Ordner, damit alle uebrigen relativen Verweise weiter stimmen.
    fertig = html_path.with_name(f".{html_path.stem}.render.html")
    fertig.write_text(stylesheets_einbetten(html_path), encoding="utf-8")

    cmd = [
        binary,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",       # keine "about:blank"-Zeile im Ausdruck
        "--print-to-pdf-no-header",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=4000",   # Webfonts/Layout fertig rechnen lassen
        "--disable-extensions",
        "--disable-background-networking",
        f"--print-to-pdf={pdf_path}",
        fertig.resolve().as_uri(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    finally:
        fertig.unlink(missing_ok=True)

    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        sys.stderr.write(proc.stderr[-2000:] + "\n")
        raise SystemExit(f"PDF-Erzeugung fehlgeschlagen fuer {html_path}")

    # "OK" statt eines Hakens: Diese Zeile wird von dokumente.py wieder
    # eingelesen, und unter Windows laesst sich U+2713 nicht ausgeben.
    print(f"OK {pdf_path}  ({pdf_path.stat().st_size // 1024} KB, "
          f"{page_count(pdf_path)} Seite(n))")


def page_count(pdf_path: Path) -> int | str:
    """Grobe Seitenzahl aus dem PDF - wichtig fuer die Laengenkontrolle.

    Ein Anschreiben muss auf eine Seite, ein Lebenslauf auf ein bis zwei. Das
    faellt im HTML nicht auf, im fertigen PDF aber sofort - deshalb hier gleich
    mit ausgeben, statt es dem Zufall zu ueberlassen.
    """
    try:
        data = pdf_path.read_bytes()
        count = data.count(b"/Type /Page") + data.count(b"/Type/Page")
        types = data.count(b"/Type /Pages") + data.count(b"/Type/Pages")
        return max(1, count - types)
    except Exception:  # noqa: BLE001
        return "?"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", nargs="+", help="eine oder mehrere HTML-Dateien")
    ap.add_argument("-o", "--out", help="Ziel-PDF (nur bei genau einer HTML-Datei)")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    if args.out and len(args.html) > 1:
        raise SystemExit("--out geht nur mit einer einzelnen HTML-Datei.")

    binary = os.environ.get("CHROMIUM_BIN") or find_chromium()

    for item in args.html:
        html_path = Path(item)
        pdf_path = Path(args.out) if args.out else html_path.with_suffix(".pdf")
        render(html_path, pdf_path, binary, args.timeout)
        time.sleep(0.2)  # zwei Chromium-Starts direkt hintereinander sind fragil


if __name__ == "__main__":
    main()
