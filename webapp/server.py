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
# Grosszuegig wegen hochgeladener Dokumente: Ein eingescanntes Zeugnis oder
# ein Lebenslauf mit 20 MB waechst als Datenadresse um ein Drittel, und es
# duerfen mehrere Seiten auf einmal sein.
MAX_BODY = 64 * 1024 * 1024

# Muss mit BENOETIGTER_STAND in static/app.js uebereinstimmen.
#
# Hintergrund: Die Dateien der Oberflaeche werden bei jeder Anfrage frisch von
# der Platte gelesen, der Python-Teil dagegen liegt im laufenden Prozess. Nach
# einem "git pull" ohne Neustart laeuft deshalb neue Oberflaeche gegen alten
# Dienst - und ein Aufruf, den es hier noch nicht gibt, endet in einem nackten
# 404, das nach einem kaputten Programm aussieht. Hochzaehlen, sobald die
# Oberflaeche etwas braucht, das der Dienst vorher nicht konnte.
API_STAND = 6


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
        if treffer:
            if speicher.bewerbung_loeschen(treffer.group(1)):
                return self._json({"ok": True})
            return self._fehler("Nicht gefunden", 404)

        treffer = re.fullmatch(r"/api/zeugnisse/([0-9a-f]+)", self.path)
        if treffer:
            if speicher.zeugnis_loeschen(treffer.group(1)):
                return self._json({"ok": True})
            return self._fehler("Nicht gefunden", 404)

        treffer = re.fullmatch(r"/api/gespraeche/([0-9a-f]+)", self.path)
        if treffer:
            if speicher.gespraech_loeschen(treffer.group(1)):
                return self._json({"ok": True})
            return self._fehler("Nicht gefunden", 404)

        if self.path == "/api/profil/foto":
            speicher.foto_loeschen(speicher.aktives_profil_id())
            return self._json({"ok": True})

        treffer = re.fullmatch(r"/api/profile/([0-9a-f]+)", self.path)
        if treffer:
            if speicher.profil_loeschen(treffer.group(1)):
                return self._json({"ok": True})
            return self._fehler(
                "Das letzte Profil lässt sich nicht löschen - ohne Profil "
                "können keine Unterlagen erstellt werden.", 409)

        return self._fehler("Unbekannter Pfad", 404)

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
                "profile": speicher.profile_liste(),
                "profil_aktiv": speicher.aktives_profil_id(),
            })

        if pfad == "/api/profil":
            profil = speicher.profil_lesen()
            return self._json(profil | {"hat_foto": bool(
                speicher.foto_pfad(speicher.aktives_profil_id()))})

        if pfad == "/api/profile":
            return self._json({"profile": speicher.profile_liste(),
                               "aktiv": speicher.aktives_profil_id()})

        if pfad == "/api/zeugnisse":
            return self._json({"zeugnisse": speicher.zeugnisse_liste()})

        treffer = re.fullmatch(r"/api/zeugnisse/([0-9a-f]+)", pfad)
        if treffer:
            eintrag = speicher.zeugnis_lesen(treffer.group(1))
            return self._json(eintrag) if eintrag else self._fehler("Nicht gefunden", 404)

        if pfad == "/api/gespraeche":
            return self._json({"gespraeche": speicher.gespraeche_liste(),
                               "bewerbungen": [
                                   {"id": b["id"], "titel": b.get("titel", ""),
                                    "firma": b.get("firma", "")}
                                   for b in speicher.bewerbungen_liste()
                                   if b.get("phase") == "fertig"]})

        treffer = re.fullmatch(r"/api/gespraeche/([0-9a-f]+)", pfad)
        if treffer:
            eintrag = speicher.gespraech_lesen(treffer.group(1))
            return self._json(eintrag) if eintrag else self._fehler("Nicht gefunden", 404)

        if pfad == "/api/profil/foto":
            bild = speicher.foto_pfad(speicher.aktives_profil_id())
            if not bild:
                return self._fehler("Kein Foto hinterlegt", 404)
            typ = "image/jpeg" if bild.suffix == ".jpg" else "image/png"
            return self._senden(200, bild.read_bytes(), typ)

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

        if pfad == "/api/zeugnisse":
            return self._zeugnis_pruefen(koerper)

        if pfad == "/api/profil/import":
            return self._lebenslauf_lesen(koerper)

        if pfad == "/api/profil/import/uebernehmen":
            return self._import_uebernehmen(koerper)

        if pfad == "/api/gespraeche":
            return self._gespraech_start(koerper)

        treffer = re.fullmatch(r"/api/gespraeche/([0-9a-f]+)/antwort", pfad)
        if treffer:
            return self._gespraech_antwort(treffer.group(1), koerper)

        treffer = re.fullmatch(r"/api/gespraeche/([0-9a-f]+)/feedback", pfad)
        if treffer:
            return self._gespraech_feedback(treffer.group(1))

        if pfad == "/api/jobsuche":
            if not speicher.schluessel_vorhanden():
                return self._fehler("Für die Jobsuche wird der API-Schlüssel "
                                    "gebraucht. Er lässt sich oben eintragen.", 409)
            profil = speicher.profil_lesen()
            fehlt = speicher.profil_vollstaendig(profil)
            if fehlt:
                return self._fehler(
                    "Ohne Profil lässt sich nicht sinnvoll suchen. Es fehlt noch: "
                    + ", ".join(fehlt) + ".", 409)
            try:
                return self._json(claude.suche_stellen(
                    profil,
                    (koerper.get("was") or "").strip(),
                    (koerper.get("wo") or "").strip(),
                    min(int(koerper.get("anzahl") or 8), 15)))
            except RuntimeError as fehler:
                return self._fehler(str(fehler), 502)
            except Exception as fehler:  # noqa: BLE001
                return self._fehler(claude.klartext(fehler), 502)

        if pfad == "/api/profile":
            name = (koerper.get("name") or "").strip()
            if not name:
                return self._fehler("Bitte einen Namen für das Profil angeben.")
            # Uebernahme aus einem bestehenden Profil: Wer eine Zweitfassung
            # fuer eine andere Branche baut, tippt sonst denselben Werdegang
            # ein zweites Mal ab.
            vorlage = (koerper.get("kopie_von") or "").strip()
            daten = speicher.profil_lesen(vorlage) if vorlage else None
            return self._json(speicher.profil_anlegen(name, daten), 201)

        if pfad == "/api/profil/foto":
            # Als Datenadresse aus dem Browser - das spart eine Formular-
            # Kodierung im Server und kostet nur ein Drittel mehr Uebertragung.
            roh = (koerper.get("bild") or "")
            roh = roh.split(",", 1)[-1] if roh.startswith("data:") else roh
            import base64  # noqa: PLC0415
            try:
                daten = base64.b64decode(roh, validate=True)
            except Exception:  # noqa: BLE001
                return self._fehler("Die Bilddaten waren unvollständig.")
            speicher.foto_speichern(speicher.aktives_profil_id(), daten)
            return self._json({"ok": True})

        treffer = re.fullmatch(r"/api/profile/([0-9a-f]+)/waehlen", pfad)
        if treffer:
            if speicher.profil_waehlen(treffer.group(1)):
                return self._json({"ok": True})
            return self._fehler("Profil nicht gefunden", 404)

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
            # Adresse der Firmenwebsite von Hand - der einzige Weg, wenn die
            # Anzeige von einer Jobboerse stammt und die Firma dort nicht
            # verlinkt ist.
            website = (koerper.get("firma_website") or "").strip()
            if website and not re.match(r"https?://", website):
                website = "https://" + website
            speicher.bewerbung_aktualisieren(treffer.group(1), phase="warteschlange",
                                             fortschritt=0, fehler="",
                                             firma_website=website,
                                             design_hinweis="")
            pipeline.starten(treffer.group(1), (koerper.get("text") or "").strip() or None)
            return self._json({"ok": True})

        return self._fehler("Unbekannter Pfad", 404)

    # --------------------------------------------------- Hochgeladene Dateien

    @staticmethod
    def _dateien_aus(koerper: dict) -> list[bytes]:
        """Holt die hochgeladenen Dateien als Bytes aus der Anfrage."""
        import base64  # noqa: PLC0415
        roh = koerper.get("dateien") or []
        if not roh:
            raise ValueError("Es kam keine Datei an.")
        if len(roh) > 8:
            raise ValueError("Höchstens acht Dateien auf einmal.")
        dateien = []
        for eintrag in roh:
            wert = (eintrag.get("daten") or "")
            wert = wert.split(",", 1)[-1] if wert.startswith("data:") else wert
            try:
                dateien.append(base64.b64decode(wert, validate=True))
            except Exception as fehler:  # noqa: BLE001
                raise ValueError(
                    f"Die Datei „{eintrag.get('name', '?')}“ kam unvollständig an."
                ) from fehler
        return dateien

    def _zeugnis_pruefen(self, koerper: dict) -> None:
        if not speicher.schluessel_vorhanden():
            return self._fehler("Zum Lesen des Zeugnisses wird der API-Schlüssel "
                                "gebraucht. Er lässt sich auf der Übersicht eintragen.", 409)
        try:
            dateien = self._dateien_aus(koerper)
            auswertung = claude.pruefe_zeugnis(dateien)
        except ValueError as fehler:
            return self._fehler(str(fehler))
        except RuntimeError as fehler:
            return self._fehler(str(fehler), 502)
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(claude.klartext(fehler), 502)
        name = (koerper.get("dateien") or [{}])[0].get("name", "Zeugnis")
        return self._json(speicher.zeugnis_speichern(name, auswertung), 201)

    def _lebenslauf_lesen(self, koerper: dict) -> None:
        if not speicher.schluessel_vorhanden():
            return self._fehler("Zum Einlesen wird der API-Schlüssel gebraucht. "
                                "Er lässt sich auf der Übersicht eintragen.", 409)
        try:
            dateien = self._dateien_aus(koerper)
            # Bewusst nur lesen und zurueckgeben, nicht speichern: Was aus einem
            # Scan kommt, gehoert angesehen, bevor es ein Profil ueberschreibt.
            return self._json(claude.lies_lebenslauf(dateien))
        except ValueError as fehler:
            return self._fehler(str(fehler))
        except RuntimeError as fehler:
            return self._fehler(str(fehler), 502)
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(claude.klartext(fehler), 502)

    def _import_uebernehmen(self, koerper: dict) -> None:
        daten = koerper.get("profil") or {}
        if not isinstance(daten, dict):
            return self._fehler("Es kamen keine Profildaten an.")
        # Nur bekannte Abschnitte - was das Modell zusaetzlich liefert (etwa
        # "unklar"), gehoert in die Anzeige, nicht in die Ablage.
        sauber = {k: v for k, v in daten.items() if k in speicher.LEERES_PROFIL}
        if (koerper.get("modus") or "neu") == "neu":
            name = (koerper.get("name") or "").strip()
            if not name:
                person = sauber.get("person", {})
                name = f"{person.get('vorname', '')} {person.get('nachname', '')}".strip() \
                    or "Aus Lebenslauf"
            return self._json(speicher.profil_anlegen(name, sauber), 201)
        return self._json(speicher.profil_schreiben(sauber))

    # ----------------------------------------------------- Uebungsgespraech

    def _gespraech_kontext(self, eintrag: dict) -> tuple[dict, dict]:
        """Stellenanalyse und Profil zu einem Uebungsgespraech."""
        bewerbung = speicher.bewerbung_lesen(eintrag["bewerbung_id"]) \
            if eintrag.get("bewerbung_id") else None
        analyse = (bewerbung or {}).get("analyse", {}) or {
            "position": eintrag.get("titel", ""), "firma": eintrag.get("firma", ""),
            "tonalitaet": "sie-formell", "muss": [], "kann": [],
        }
        return analyse, speicher.profil_lesen(eintrag.get("profil_id", ""))

    def _gespraech_start(self, koerper: dict) -> None:
        if not speicher.schluessel_vorhanden():
            return self._fehler("Für das Übungsgespräch wird der API-Schlüssel "
                                "gebraucht. Er lässt sich oben eintragen.", 409)
        profil = speicher.profil_lesen()
        fehlt = speicher.profil_vollstaendig(profil)
        if fehlt:
            return self._fehler(
                "Ohne Profil kann das Gegenüber nichts fragen, was zu dir passt. "
                "Es fehlt noch: " + ", ".join(fehlt) + ".", 409)

        bewerbung_id = (koerper.get("bewerbung_id") or "").strip()
        titel = (koerper.get("titel") or "").strip()
        firma = (koerper.get("firma") or "").strip()
        if bewerbung_id:
            bewerbung = speicher.bewerbung_lesen(bewerbung_id)
            if not bewerbung:
                return self._fehler("Bewerbung nicht gefunden", 404)
            titel = titel or bewerbung.get("titel", "")
            firma = firma or bewerbung.get("firma", "")
        if not titel:
            return self._fehler("Bitte eine Stelle wählen oder die Position eintragen.")

        eintrag = speicher.gespraech_anlegen(bewerbung_id, titel, firma)
        analyse, profil = self._gespraech_kontext(eintrag)
        try:
            text = claude.gespraech_antwort(analyse, profil, titel, firma, [])
        except Exception as fehler:  # noqa: BLE001
            speicher.gespraech_loeschen(eintrag["id"])
            return self._fehler(claude.klartext(fehler), 502)
        return self._json(speicher.gespraech_ergaenzen(eintrag["id"], "recruiter", text), 201)

    def _gespraech_antwort(self, gespraech_id: str, koerper: dict) -> None:
        text = (koerper.get("text") or "").strip()
        if not text:
            return self._fehler("Es kam keine Antwort an. Bitte noch einmal.")
        eintrag = speicher.gespraech_lesen(gespraech_id)
        if not eintrag:
            return self._fehler("Gespräch nicht gefunden", 404)

        eintrag = speicher.gespraech_ergaenzen(gespraech_id, "ich", text)
        analyse, profil = self._gespraech_kontext(eintrag)
        try:
            antwort = claude.gespraech_antwort(
                analyse, profil, eintrag.get("titel", ""), eintrag.get("firma", ""),
                eintrag["verlauf"])
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(claude.klartext(fehler), 502)
        return self._json(speicher.gespraech_ergaenzen(gespraech_id, "recruiter", antwort))

    def _gespraech_feedback(self, gespraech_id: str) -> None:
        eintrag = speicher.gespraech_lesen(gespraech_id)
        if not eintrag:
            return self._fehler("Gespräch nicht gefunden", 404)
        if not any(z["rolle"] == "ich" for z in eintrag.get("verlauf", [])):
            return self._fehler(
                "Es wurde noch nichts geantwortet - da gibt es nichts auszuwerten.")
        analyse, profil = self._gespraech_kontext(eintrag)
        try:
            feedback = claude.gespraech_feedback(analyse, profil, eintrag["verlauf"])
        except Exception as fehler:  # noqa: BLE001
            return self._fehler(claude.klartext(fehler), 502)
        return self._json(speicher.gespraech_aktualisieren(gespraech_id, feedback=feedback))

    @staticmethod
    def _kurz(eintrag: dict) -> dict:
        return {schluessel: eintrag.get(schluessel) for schluessel in
                ("id", "titel", "firma", "ort", "status", "phase", "fortschritt",
                 "fehler", "erstellt", "passung", "url", "profil_name")} | {
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
