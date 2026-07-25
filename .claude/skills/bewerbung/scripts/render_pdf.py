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
import shutil
import subprocess
import sys
import time
from pathlib import Path

CANDIDATES = [
    "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chromium() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in CANDIDATES:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    raise SystemExit(
        "Kein Chromium gefunden. Bitte Chrome/Chromium installieren oder den "
        "Pfad ueber die Umgebungsvariable CHROMIUM_BIN setzen."
    )


def render(html_path: Path, pdf_path: Path, binary: str, timeout: int = 120) -> None:
    if not html_path.exists():
        raise SystemExit(f"HTML nicht gefunden: {html_path}")

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
        html_path.resolve().as_uri(),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        sys.stderr.write(proc.stderr[-2000:] + "\n")
        raise SystemExit(f"PDF-Erzeugung fehlgeschlagen fuer {html_path}")

    print(f"✓ {pdf_path}  ({pdf_path.stat().st_size // 1024} KB, "
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
