#!/usr/bin/env python3
"""Lokaler Webserver fuer den Bewerbungsassistenten.

    python3 webapp/server.py            # http://127.0.0.1:8765

Bindet absichtlich nur an 127.0.0.1: Auf dem Server liegen Adresse, Telefon-
nummer und der komplette Werdegang der Person. Diese Daten gehoeren nicht ins
Netzwerk, und ein versehentliches --host 0.0.0.0 waere hier ein echter Schaden.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kern import pipeline, speicher  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 4 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "Bewerbung/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- Hilfen

    def _senden(self, status: int, koerper: bytes, typ: str = "application/json",
                extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        # Die Seite laedt ausschliesslich eigene Dateien - eine enge CSP kostet
        # nichts und verhindert, dass Modelltext ungewollt etwas nachlaedt.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "style-src 'self' 'unsafe-inline'; frame-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        for schluessel, wert in (extra or {}).items():
            self.send_header(schluessel, wert)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def _json(self, daten, status: int = 200) -> None:
        self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"))

    def _fehler(self, nachricht: str, status: int = 400) -> None:
        self._json({"fehler": nachricht}, status)

    def _koerper(self) -> dict:
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge <= 0:
            return {}
        if laenge > MAX_BODY:
            raise ValueError("Anfrage zu gross")
        return json.loads(self.rfile.read(laenge).decode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("  %s\n" % (format % args))

    # ---------------------------------------------------------------- Routen

    def do_GET(self) -> None:  # noqa: N802
        pfad = self.path.split("?", 1)[0]
        try:
            if pfad.startswith("/api/"):
                return self._api_get(pfad)
            return self._statisch(pfad)
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(str(fehler), 500)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        pfad = self.path.split("?", 1)[0]
        try:
            return self._api_post(pfad)
        except ValueError as fehler:
            return self._fehler(str(fehler), 400)
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(str(fehler), 500)

    def do_DELETE(self) -> None:  # noqa: N802
        treffer = re.fullmatch(r"/api/bewerbungen/([0-9a-f]+)", self.path)
        if not treffer:
            return self._fehler("Unbekannter Pfad", 404)
        if speicher.bewerbung_loeschen(treffer.group(1)):
            return self._json({"ok": True})
        return self._fehler("Nicht gefunden", 404)

    # ------------------------------------------------------------- statisch

    def _statisch(self, pfad: str) -> None:
        name = "index.html" if pfad in ("/", "") else pfad.lstrip("/")
        ziel = (STATIC / name).resolve()
        if not ziel.is_file() or STATIC.resolve() not in ziel.parents:
            return self._fehler("Nicht gefunden", 404)
        typ = mimetypes.guess_type(ziel.name)[0] or "application/octet-stream"
        if typ.startswith("text/") or typ in ("application/javascript",):
            typ += "; charset=utf-8"
        return self._senden(200, ziel.read_bytes(), typ)

    # ------------------------------------------------------------------ API

    def _api_get(self, pfad: str) -> None:
        if pfad == "/api/uebersicht":
            return self._json({
                "kennzahlen": speicher.kennzahlen(),
                "bewerbungen": [self._kurz(b) for b in speicher.bewerbungen_liste()],
                "profil_fehlt": speicher.profil_vollstaendig(speicher.profil_lesen()),
            })

        if pfad == "/api/profil":
            return self._json(speicher.profil_lesen())

        treffer = re.fullmatch(r"/api/bewerbungen/([0-9a-f]+)", pfad)
        if treffer:
            eintrag = speicher.bewerbung_lesen(treffer.group(1))
            return self._json(eintrag) if eintrag else self._fehler("Nicht gefunden", 404)

        treffer = re.fullmatch(r"/api/bewerbungen/([0-9a-f]+)/datei/([\w.\-]+)", pfad)
        if treffer:
            return self._datei(treffer.group(1), treffer.group(2))

        return self._fehler("Unbekannter Pfad", 404)

    def _datei(self, bewerbung_id: str, name: str) -> None:
        try:
            ziel = speicher.datei_pfad(bewerbung_id, name)
        except ValueError as fehler:
            return self._fehler(str(fehler), 400)
        if not ziel.is_file():
            return self._fehler("Datei nicht gefunden", 404)

        typ = {"pdf": "application/pdf", "md": "text/markdown; charset=utf-8",
               "html": "text/html; charset=utf-8", "txt": "text/plain; charset=utf-8",
               "json": "application/json"}.get(ziel.suffix.lstrip("."),
                                               "application/octet-stream")
        # PDFs inline, damit die Vorschau im Browser funktioniert.
        return self._senden(200, ziel.read_bytes(), typ,
                            {"Content-Disposition": f'inline; filename="{ziel.name}"'})

    def _api_post(self, pfad: str) -> None:
        koerper = self._koerper()

        if pfad == "/api/profil":
            return self._json(speicher.profil_schreiben(koerper))

        if pfad == "/api/bewerbungen":
            url = (koerper.get("url") or "").strip()
            text = (koerper.get("text") or "").strip()
            if not url and not text:
                return self._fehler("Bitte einen Link zur Stelle oder den Anzeigentext angeben.")
            if url and not re.match(r"https?://", url):
                url = "https://" + url

            fehlt = speicher.profil_vollstaendig(speicher.profil_lesen())
            if fehlt:
                return self._fehler(
                    "Im Profil fehlt noch: " + ", ".join(fehlt)
                    + ". Ohne diese Angaben lassen sich keine Unterlagen erstellen, "
                      "ohne etwas zu erfinden.", 409)

            eintrag = speicher.bewerbung_anlegen(url or "(Text eingefügt)")
            pipeline.starten(eintrag["id"], text or None)
            return self._json(eintrag, 201)

        treffer = re.fullmatch(r"/api/bewerbungen/([0-9a-f]+)", pfad)
        if treffer:
            erlaubt = {k: v for k, v in koerper.items() if k in ("status", "notiz")}
            if erlaubt.get("status") and erlaubt["status"] not in speicher.STATUS:
                return self._fehler("Unbekannter Status")
            eintrag = speicher.bewerbung_aktualisieren(treffer.group(1), **erlaubt)
            return self._json(eintrag) if eintrag else self._fehler("Nicht gefunden", 404)

        treffer = re.fullmatch(r"/api/bewerbungen/([0-9a-f]+)/neu", pfad)
        if treffer:
            eintrag = speicher.bewerbung_lesen(treffer.group(1))
            if not eintrag:
                return self._fehler("Nicht gefunden", 404)
            speicher.bewerbung_aktualisieren(treffer.group(1), phase="warteschlange",
                                             fortschritt=0, fehler="")
            pipeline.starten(treffer.group(1), (koerper.get("text") or "").strip() or None)
            return self._json({"ok": True})

        return self._fehler("Unbekannter Pfad", 404)

    @staticmethod
    def _kurz(eintrag: dict) -> dict:
        return {schluessel: eintrag.get(schluessel) for schluessel in
                ("id", "titel", "firma", "ort", "status", "phase", "fortschritt",
                 "fehler", "erstellt", "passung", "url")} | {
            "hat_dateien": bool(eintrag.get("dateien"))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--kein-browser", action="store_true")
    args = parser.parse_args()

    speicher.BEWERBUNGEN.mkdir(parents=True, exist_ok=True)
    adresse = f"http://127.0.0.1:{args.port}"

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Bewerbungsassistent laeuft auf {adresse}")
    print(f"  Daten: {speicher.BASIS}")
    print("  Beenden mit Strg+C\n")

    if not args.kein_browser:
        try:
            webbrowser.open(adresse)
        except Exception:  # noqa: BLE001 - ohne Browser laeuft es trotzdem
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Beendet.")


if __name__ == "__main__":
    main()
