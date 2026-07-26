#!/usr/bin/env python3
"""Lokaler Webserver fuer den Bewerbungsassistenten.

    python3 webapp/server.py            # http://127.0.0.1:8765

Standardmaessig nur auf 127.0.0.1 erreichbar: Auf dem Server liegen Adresse,
Telefonnummer und der komplette Werdegang der Person - die gehoeren nicht
ungefragt ins lokale Netz.

Mit --host laesst sich das aendern. Das ist fuer genau einen Fall gedacht:
In einem Codespace erreicht die Weiterleitung von GitHub den Dienst je nach
Umgebung nicht auf 127.0.0.1. Dort ist der Container isoliert und der Zugang
laeuft ohnehin ueber die Anmeldung bei GitHub - auf dem eigenen Rechner waere
dieselbe Einstellung dagegen leichtsinnig, deshalb bleibt sie dort aus und
wird beim Start deutlich gemeldet.
"""

from __future__ import annotations

import argparse
import atexit
import json
import mimetypes
import os
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kern import claude, pipeline, speicher  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 4 * 1024 * 1024

# Muss mit BENOETIGTER_STAND in static/app.js uebereinstimmen.
#
# Hintergrund: Die Dateien der Oberflaeche werden bei jeder Anfrage frisch von
# der Platte gelesen, der Python-Teil dagegen liegt im laufenden Prozess. Nach
# einem "git pull" ohne Neustart laeuft deshalb neue Oberflaeche gegen alten
# Dienst - und ein Aufruf, den es hier noch nicht gibt, endet in einem nackten
# 404, das nach einem kaputten Programm aussieht. Hochzaehlen, sobald die
# Oberflaeche etwas braucht, das der Dienst vorher nicht konnte.
API_STAND = 2


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
                "api_stand": API_STAND,
                "kennzahlen": speicher.kennzahlen(),
                "bewerbungen": [self._kurz(b) for b in speicher.bewerbungen_liste()],
                "profil_fehlt": speicher.profil_vollstaendig(speicher.profil_lesen()),
                "schluessel": speicher.schluessel_vorhanden(),
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

        if pfad == "/api/schluessel":
            wert = koerper.get("schluessel", "")
            # Erst pruefen, dann speichern. Ein fehlerhafter Schluessel darf
            # einen funktionierenden nicht ueberschreiben - und die Person
            # erfaehrt jetzt, dass er nicht taugt, statt zwei Minuten spaeter
            # mitten in einer Bewerbung.
            speicher.pruefe_form(wert)
            try:
                claude.pruefe_schluessel(wert.strip())
            except RuntimeError as fehler:
                return self._fehler(str(fehler), 400)
            speicher.schluessel_speichern(wert)
            return self._json({"ok": True})

        if pfad == "/api/schluessel/pruefen":
            try:
                claude.pruefe_schluessel()
            except RuntimeError as fehler:
                return self._json({"ok": False, "meldung": str(fehler)})
            return self._json({"ok": True, "meldung": "Der Schlüssel funktioniert."})

        if pfad == "/api/profil":
            return self._json(speicher.profil_schreiben(koerper))

        if pfad == "/api/bewerbungen":
            url = (koerper.get("url") or "").strip()
            text = (koerper.get("text") or "").strip()
            if not url and not text:
                return self._fehler("Bitte einen Link zur Stelle oder den Anzeigentext angeben.")
            if url and not re.match(r"https?://", url):
                url = "https://" + url

            if not speicher.schluessel_vorhanden():
                return self._fehler(
                    "Es ist noch kein API-Schluessel hinterlegt. Du kannst ihn "
                    "oben auf der Uebersicht eintragen.", 409)

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


def oeffentliche_adresse(port: int) -> str:
    """Die Adresse, unter der die Seite tatsaechlich erreichbar ist.

    Im Codespace laeuft der Dienst in einem Container. 127.0.0.1 zeigt dort auf
    den Container - im Browser aber auf den eigenen Rechner, wo nichts lauscht.
    Wer die Adresse aus dem Terminal anklickt, landet also verlaesslich auf
    einer Fehlerseite. GitHub stellt den richtigen Namen in der Umgebung
    bereit; genau der gehoert in die Startmeldung.
    """
    name = os.environ.get("CODESPACE_NAME")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if name and domain:
        return f"https://{name}-{port}.{domain}"
    return f"http://127.0.0.1:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Adresse, auf der gelauscht wird. Standard 127.0.0.1 "
                             "(nur dieser Rechner). Im Codespace 0.0.0.0.")
    parser.add_argument("--kein-browser", action="store_true")
    args = parser.parse_args()

    speicher.BEWERBUNGEN.mkdir(parents=True, exist_ok=True)
    hat_schluessel = speicher.schluessel_laden()
    adresse = oeffentliche_adresse(args.port)

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as fehler:
        print(f"\n  Port {args.port} ist belegt ({fehler}).")
        print(f"  Laeuft der Assistent vielleicht schon? Dann einfach {adresse} oeffnen.")
        print(f"  Sonst mit anderem Port starten:  python3 webapp/server.py --port {args.port + 1}\n")
        raise SystemExit(1) from fehler

    # Eigene Prozessnummer hinterlegen, damit starten.sh eine laufende Fassung
    # gezielt beenden kann. Die Alternative - in den Kommandozeilen aller
    # Prozesse nach einem Muster suchen - trifft zuverlaessig auch fremde
    # Prozesse, die das Muster nur zufaellig enthalten (etwa die Shell, die den
    # Suchbefehl selbst ausfuehrt), und beendet im schlimmsten Fall diese.
    pid_datei = speicher.BASIS / "dienst.pid"
    try:
        pid_datei.write_text(str(os.getpid()), encoding="utf-8")
        atexit.register(lambda: pid_datei.unlink(missing_ok=True))
    except OSError:
        pass  # Ohne PID-Datei laeuft alles weiter, nur der Neustart wird ruppiger.

    rahmen = "─" * 52
    print(f"\n  {rahmen}")
    print("   Der Bewerbungsassistent laeuft. Im Browser oeffnen:")
    print(f"\n       {adresse}\n")
    print(f"  {rahmen}")
    if adresse.startswith("https://"):
        print("  Diese Adresse anklicken - nicht 127.0.0.1. Beim ersten Mal")
        print("  fragt GitHub nach der Anmeldung, das ist normal.")
    elif args.host not in ("127.0.0.1", "localhost"):
        print(f"  Achtung: erreichbar auf {args.host} - nicht nur auf diesem Rechner.")
    print(f"\n  Daten liegen in: {speicher.BASIS}")
    if not hat_schluessel:
        print("  Hinweis: Noch kein API-Schluessel hinterlegt - die Seite fragt danach.")
    print("  Beenden mit Strg+C\n")

    # Oeffnet sich nichts (Server ohne Oberflaeche, WSL, SSH), ist das kein
    # Fehler - die Adresse oben steht bewusst gross da und laesst sich kopieren.
    if not args.kein_browser:
        try:
            webbrowser.open(adresse)
        except Exception:  # noqa: BLE001
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Beendet.")


if __name__ == "__main__":
    main()
