#!/usr/bin/env python3
"""Leitet aus der Website einer Firma ein Design-Profil ab (Farben, Typografie, Logo).

Nur Standardbibliothek. Nutzt Proxy- und CA-Einstellungen aus der Umgebung.

    python3 extract_brand.py https://firma.de -o brand.json --emit-css theme.css

Das Ergebnis ist bewusst konservativ: Es liefert Marken*akzente*, keine
Komplettkopie der Website. Bewerbungsunterlagen muessen in erster Linie lesbar
und seriös sein - deshalb prueft das Skript Kontraste und liefert fuer Text
gegebenenfalls eine abgedunkelte Variante der Markenfarbe mit.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

MAX_BYTES = 3_000_000
DEFAULT_TIMEOUT = 20

# Selektoren/Variablennamen, die typischerweise die Markenfarbe tragen.
BRANDISH = re.compile(
    r"(brand|primary|primaer|prim\b|accent|akzent|highlight|cta|btn|button|"
    r"header|navbar|nav\b|hero|logo|link|theme|corporate|main-?color)",
    re.I,
)
# Selektoren, die eher Fliesstext beschreiben.
BODYISH = re.compile(r"(^|[\s,>+~])(body|html|p|:root)\b", re.I)
HEADINGISH = re.compile(r"(h1|h2|h3|\.title|\.heading|\.logo|\.brand|display)", re.I)

GENERIC_FAMILIES = {
    "inherit", "initial", "unset", "revert", "serif", "sans-serif", "monospace",
    "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif", "ui-monospace",
    "ui-rounded", "-apple-system", "blinkmacsystemfont", "emoji", "math", "fangsong",
}

# Icon- und Widget-Schriften sagen nichts ueber die Hausschrift aus. Sie tauchen
# in fast jedem CSS auf und wuerden die Erkennung sonst zuverlaessig kapern.
ICON_FONTS = re.compile(
    r"(icon|glyph|fontawesome|font awesome|material.{0,2}(icons|symbols)|slick|"
    r"feather|ionicon|octicon|symbol|dashicon|typicon|elusive|entypo|webfont-?icons)",
    re.I,
)

NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "blue": "#0000ff", "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000",
    "olive": "#808000", "lime": "#00ff00", "aqua": "#00ffff", "cyan": "#00ffff",
    "teal": "#008080", "navy": "#000080", "fuchsia": "#ff00ff", "magenta": "#ff00ff",
    "gold": "#ffd700", "indigo": "#4b0082", "crimson": "#dc143c", "salmon": "#fa8072",
    "tomato": "#ff6347", "turquoise": "#40e0d0", "violet": "#ee82ee",
    "darkblue": "#00008b", "darkred": "#8b0000", "darkgreen": "#006400",
    "midnightblue": "#191970", "royalblue": "#4169e1", "steelblue": "#4682b4",
    "seagreen": "#2e8b57", "forestgreen": "#228b22", "firebrick": "#b22222",
    "slategray": "#708090", "slategrey": "#708090", "dimgray": "#696969",
}

# Auf den meisten Linux-Systemen tatsaechlich vorhandene Familien. Das Mapping
# haelt das Rendering vorhersagbar - eine Webfont der Firma ist lokal fast nie
# installiert, und ein stiller Fallback auf eine Zufallsschrift sieht schlecht aus.
FONT_MAP = [
    # (Erkennungsmuster im Namen, lokale Familie, Klassifikation)
    (r"(garamond|baskerville|caslon|minion|charter|freight|tiempo|lora|merriweather)",
     "Bitstream Charter, Liberation Serif, Georgia, serif", "serif"),
    (r"(times|georgia|cambria|book|serif|playfair|didot|bodoni|slab|roboto slab)",
     "Liberation Serif, Georgia, serif", "serif"),
    (r"(courier|mono|consol|menlo)",
     "Liberation Mono, Courier New, monospace", "mono"),
    (r"(futura|avenir|century gothic|poppins|montserrat|nunito|quicksand|circular|"
     r"gotham|proxima|museo|geometr)",
     "DejaVu Sans, Liberation Sans, Arial, sans-serif", "geometric-sans"),
    (r"(helvetica|arial|inter|roboto|open sans|lato|source sans|noto sans|"
     r"segoe|system|ibm plex|work sans|nimbus|univers|frutiger|neue)",
     "Liberation Sans, Arial, Helvetica, sans-serif", "neo-grotesque-sans"),
]
FONT_FALLBACK = ("Liberation Sans, Arial, Helvetica, sans-serif", "sans")


# --------------------------------------------------------------------------- #
# Netzwerk
# --------------------------------------------------------------------------- #

def _opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()  # respektiert SSL_CERT_FILE
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPRedirectHandler(),
        urllib.request.ProxyHandler(),  # respektiert HTTPS_PROXY/NO_PROXY
    )


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """Laedt eine URL und gibt (finale_url, text) zurueck. Fehler -> ('', '')."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,text/css,*/*;q=0.8",
            "Accept-Language": "de,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    try:
        resp = _opener().open(req, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - jede Netzwerkstoerung ist hier gleich
        print(f"  ! konnte {url} nicht laden: {exc}", file=sys.stderr)
        return "", ""

    # Stueckweise lesen mit hartem Zeitlimit. Grosse Konzernseiten halten die
    # Verbindung gern offen (Tracking, Streaming); ein blockierendes read() bis
    # zum Ende laeuft dort in den Timeout und wir haetten am Ende gar nichts -
    # obwohl das <head> mit allen Stylesheet-Links laengst angekommen ist.
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    total = 0
    try:
        with resp:
            while total < MAX_BYTES:
                if time.monotonic() > deadline:
                    print("  ! Zeitlimit - arbeite mit Teilinhalt weiter",
                          file=sys.stderr)
                    break
                block = resp.read(65536)
                if not block:
                    break
                chunks.append(block)
                total += len(block)
            final_url = resp.geturl()
            headers = resp.headers
    except Exception as exc:  # noqa: BLE001
        if not chunks:
            print(f"  ! Abbruch beim Lesen von {url}: {exc}", file=sys.stderr)
            return "", ""
        print(f"  ! unvollstaendig gelesen ({exc}) - nutze Teilinhalt",
              file=sys.stderr)
        final_url, headers = url, resp.headers

    raw = b"".join(chunks)
    enc = (headers.get("Content-Encoding") or "").lower()
    try:
        if "gzip" in enc:
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
        elif "deflate" in enc:
            raw = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw)
    except Exception:  # noqa: BLE001 - abgeschnittener Stream, nimm was da ist
        pass

    charset = headers.get_content_charset() or "utf-8"
    return final_url, raw.decode(charset, errors="replace")


# --------------------------------------------------------------------------- #
# HTML-Analyse
# --------------------------------------------------------------------------- #

class PageParser(HTMLParser):
    """Sammelt Stylesheet-Links, Inline-CSS, Logo-Kandidaten und Meta-Farben."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.css_links: list[str] = []
        self.inline_css: list[str] = []
        self.style_attrs: list[str] = []
        self.logos: list[str] = []
        self.theme_colors: list[str] = []
        self.title = ""
        self._in_style = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").lower()
            href = a.get("href", "")
            if "stylesheet" in rel and href:
                self.css_links.append(href)
            if "icon" in rel and href and not href.endswith(".ico"):
                self.logos.append(href)
        elif tag == "style":
            self._in_style = True
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content", "")
            if name == "theme-color" and content:
                self.theme_colors.append(content)
            if name in ("og:image", "twitter:image") and content:
                self.logos.append(content)
        elif tag == "img":
            hay = " ".join((a.get("src", ""), a.get("alt", ""), a.get("class", ""),
                            a.get("id", "")))
            if re.search(r"logo|brand|wordmark", hay, re.I) and a.get("src"):
                self.logos.append(a["src"])
        if "style" in a and a["style"]:
            self.style_attrs.append(a["style"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.inline_css.append(data)
        elif self._in_title:
            self.title += data.strip()


# --------------------------------------------------------------------------- #
# Farb-Utilities
# --------------------------------------------------------------------------- #

def parse_color(token: str) -> str | None:
    """Normalisiert einen CSS-Farbwert auf '#rrggbb'. Transparentes -> None."""
    t = token.strip().lower()
    if not t:
        return None
    if t in NAMED_COLORS:
        return NAMED_COLORS[t]
    m = re.fullmatch(r"#([0-9a-f]{3,8})", t)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            if len(h) == 4 and int(h[3] * 2, 16) < 40:
                return None
            return "#" + "".join(c * 2 for c in h[:3])
        if len(h) in (6, 8):
            if len(h) == 8 and int(h[6:8], 16) < 40:
                return None
            return "#" + h[:6]
        return None
    m = re.fullmatch(r"rgba?\(([^)]+)\)", t)
    if m:
        parts = re.split(r"[,\s/]+", m.group(1).strip())
        parts = [p for p in parts if p]
        if len(parts) < 3:
            return None
        try:
            vals = []
            for p in parts[:3]:
                vals.append(round(float(p[:-1]) * 255 / 100) if p.endswith("%")
                            else int(float(p)))
            if len(parts) >= 4:
                alpha = parts[3]
                a = float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)
                if a < 0.15:
                    return None
        except ValueError:
            return None
        return "#%02x%02x%02x" % tuple(max(0, min(255, v)) for v in vals)
    m = re.fullmatch(r"hsla?\(([^)]+)\)", t)
    if m:
        parts = [p for p in re.split(r"[,\s/]+", m.group(1).strip()) if p]
        if len(parts) < 3:
            return None
        try:
            h = float(re.sub(r"(deg|turn|rad)$", "", parts[0]))
            if parts[0].endswith("turn"):
                h *= 360
            s = float(parts[1].rstrip("%")) / 100
            light = float(parts[2].rstrip("%")) / 100
            if len(parts) >= 4:
                alpha = parts[3]
                a = float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)
                if a < 0.15:
                    return None
        except ValueError:
            return None
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360, light, s)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    return None


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hsl(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in rgb(hex_color))
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, light


def luminance(hex_color: str) -> float:
    def chan(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(hex_color)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def shade(hex_color: str, lightness: float) -> str:
    h, s, _ = hsl(hex_color)
    r, g, b = colorsys.hls_to_rgb(h / 360, max(0.0, min(1.0, lightness)), s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def darken_until_readable(hex_color: str, bg: str = "#ffffff",
                          target: float = 4.5) -> str:
    """Dunkelt eine Farbe ab, bis sie als Text auf bg lesbar ist.

    Markenfarben sind fuer grosse Flaechen gemacht, nicht fuer 10-pt-Text. Ohne
    diesen Schritt entstehen huebsche, aber unlesbare Ueberschriften - und ein
    Personaler, der die Zeile nicht entziffert, liest sie nicht.
    """
    if contrast(hex_color, bg) >= target:
        return hex_color
    _, _, light = hsl(hex_color)
    while light > 0.04:
        light -= 0.02
        cand = shade(hex_color, light)
        if contrast(cand, bg) >= target:
            return cand
    return "#1a1a1a"


def muted_tone(base: str) -> str:
    """Gedaempfter Grauton im Farbton der Marke - fuer Datumsangaben, Ortsangaben.

    Eine schlicht aufgehellte Markenfarbe waere hier falsch: Sekundaertext in
    kraeftigem Blau konkurriert mit den Ueberschriften. Entsaettigt wirkt es
    ruhig und bleibt trotzdem erkennbar zur Marke gehoerend.
    """
    h, s, _ = hsl(base)
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.42, min(s * 0.3, 0.22))
    return darken_until_readable("#%02x%02x%02x" % (round(r * 255), round(g * 255),
                                                    round(b * 255)))


def is_keyword_pure(hex_color: str) -> bool:
    """Erkennt #0000ff, #ff0000, #00ffff & Co.

    Solche Vollton-Werte stammen praktisch immer aus CSS-Schluesselwoertern
    (`blue`, `red`) in Resets, Focus-Outlines oder Debug-Regeln. Echte
    Corporate-Farben sind nuanciert. Ohne diesen Filter schlaegt ein einzelnes
    `outline: 2px solid blue` die tatsaechliche Hausfarbe.
    """
    r, g, b = rgb(hex_color)
    return all(c in (0, 128, 255) for c in (r, g, b))


def is_chromatic(hex_color: str) -> bool:
    """True fuer echte Farben - Grautoene und Fast-Weiss/Schwarz fliegen raus.

    Die untere Helligkeitsgrenze ist bewusst sehr niedrig: Sehr viele Konzerne
    fuehren ein fast schwarzes Navy als Hausfarbe (Siemens #000028, Allianz,
    diverse Banken). Bei einer Grenze von 10 % Helligkeit fielen genau diese
    heraus und ein zufaelliges Bootstrap-Orange gewann. Reine Grautoene bleiben
    ueber die Saettigungsgrenze trotzdem aussen vor.
    """
    _, s, light = hsl(hex_color)
    return s >= 0.18 and 0.05 <= light <= 0.90 and not is_keyword_pure(hex_color)


def hue_distance(a: str, b: str) -> float:
    d = abs(hsl(a)[0] - hsl(b)[0]) % 360
    return min(d, 360 - d)


# --------------------------------------------------------------------------- #
# CSS-Analyse
# --------------------------------------------------------------------------- #

COLOR_TOKEN = re.compile(
    r"(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(?:%s)\b)"
    % "|".join(NAMED_COLORS)
)
DECL = re.compile(r"([-a-zA-Z]+)\s*:\s*([^;{}]+)")
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def score_css(css: str, colors: dict[str, float], fonts: dict[str, dict[str, float]],
              base_weight: float = 1.0, brand_hits: dict[str, float] | None = None
              ) -> None:
    """Zaehlt Farb- und Schriftvorkommen gewichtet nach Kontext.

    Die Gewichtung ist der Kern der Heuristik: Eine Farbe, die in einer
    Custom-Property namens --brand-primary steht, ist mit sehr viel hoeherer
    Wahrscheinlichkeit die Hausfarbe als eine, die einmal in einem Schatten
    vorkommt.

    `brand_hits` zaehlt zusaetzlich nur die wirklich aussagekraeftigen Treffer
    (benannte Marken-Variablen, Marken-Selektoren). Reine Haeufigkeit reicht als
    Kriterium naemlich nicht: CSS-Frameworks bringen ihre Alarm- und
    Hinweisfarben so oft mit, dass ein Bootstrap-Orange sonst als zweite
    Hausfarbe durchgeht.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    hits = brand_hits if brand_hits is not None else {}

    # 1. Custom Properties - staerkstes Signal.
    for name, value in re.findall(r"(--[-\w]+)\s*:\s*([^;{}]+)", css):
        col = parse_color(value.strip())
        if not col:
            continue
        named = bool(BRANDISH.search(name))
        w = 12.0 if named else 2.0
        colors[col] = colors.get(col, 0.0) + w * base_weight
        if named:
            hits[col] = hits.get(col, 0.0) + w * base_weight

    # 2. Deklarationen im Kontext ihres Selektors.
    for selector, block in RULE.findall(css):
        sel = selector.strip()
        if sel.startswith("@"):
            continue
        brandish = bool(BRANDISH.search(sel))
        for prop, value in DECL.findall(block):
            prop = prop.lower().strip()
            if prop.startswith("--"):
                continue

            if prop in ("color", "background", "background-color", "border-color",
                        "fill", "stroke", "border-bottom-color", "border-top-color",
                        "outline-color"):
                for token in COLOR_TOKEN.findall(value):
                    col = parse_color(token if isinstance(token, str) else token[0])
                    if not col:
                        continue
                    w = 1.0
                    if brandish:
                        w = 6.0
                    if prop in ("background", "background-color", "fill"):
                        w *= 1.4
                    colors[col] = colors.get(col, 0.0) + w * base_weight
                    if brandish:
                        hits[col] = hits.get(col, 0.0) + w * base_weight

            elif prop in ("font-family", "font"):
                fam = first_family(value)
                if not fam:
                    continue
                role = "heading" if HEADINGISH.search(sel) else (
                    "body" if BODYISH.search(sel) else "other")
                bucket = fonts.setdefault(fam, {"heading": 0.0, "body": 0.0,
                                                "other": 0.0})
                bucket[role] += (3.0 if role != "other" else 1.0) * base_weight


def first_family(value: str) -> str | None:
    """Erste nicht-generische, nicht-Icon-Familie aus einem font-family-Stack."""
    for part in value.split(","):
        fam = part.strip()
        fam = re.sub(r"!\s*important", "", fam, flags=re.I)
        fam = fam.strip().strip("'\"").strip()
        # Bei der Kurzform `font:` steht vor der Familie noch Groesse/Zeilenhoehe.
        fam = re.sub(r"^(\d+(\.\d+)?(px|rem|em|pt|%)?\s*(/\s*\S+)?\s+)+", "",
                     fam).strip()
        if not fam or fam.lower() in GENERIC_FAMILIES:
            continue
        if len(fam) > 40 or fam.startswith("var(") or ICON_FONTS.search(fam):
            continue
        return fam
    return None


def map_font(family: str | None) -> tuple[str, str, str]:
    """(original, lokaler_stack, klassifikation) - webfonts lokal ersetzen."""
    if not family:
        return "", FONT_FALLBACK[0], FONT_FALLBACK[1]
    low = family.lower()
    for pattern, stack, kind in FONT_MAP:
        if re.search(pattern, low):
            return family, stack, kind
    return family, FONT_FALLBACK[0], FONT_FALLBACK[1]


# --------------------------------------------------------------------------- #
# Hauptlogik
# --------------------------------------------------------------------------- #

def extract(url: str, max_css: int = 10, timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url

    print(f"→ lade {url}", file=sys.stderr)
    final_url, html = fetch(url, timeout)
    if not html:
        raise SystemExit(f"Website nicht erreichbar: {url}")

    page = PageParser()
    try:
        page.feed(html)
    except Exception:  # noqa: BLE001 - kaputtes HTML soll nicht abbrechen
        pass

    colors: dict[str, float] = {}
    fonts: dict[str, dict[str, float]] = {}
    brand_hits: dict[str, float] = {}

    for tc in page.theme_colors:
        col = parse_color(tc)
        if col:
            colors[col] = colors.get(col, 0.0) + 15.0
            brand_hits[col] = brand_hits.get(col, 0.0) + 15.0

    for block in page.inline_css:
        score_css(block, colors, fonts, base_weight=1.2, brand_hits=brand_hits)
    for attr in page.style_attrs:
        score_css("x{%s}" % attr, colors, fonts, base_weight=0.6,
                  brand_hits=brand_hits)

    seen: set[str] = set()
    loaded = 0
    for href in page.css_links:
        if loaded >= max_css:
            break
        css_url = urllib.parse.urljoin(final_url, href)
        if css_url in seen:
            continue
        seen.add(css_url)
        print(f"→ CSS {css_url}", file=sys.stderr)
        _, css = fetch(css_url, timeout)
        if css:
            loaded += 1
            score_css(css, colors, fonts, brand_hits=brand_hits)

    if not colors:
        raise SystemExit(
            "Keine Farben gefunden - vermutlich rendert die Seite rein per "
            "JavaScript. Bitte Farben manuell in brand.json eintragen."
        )

    ranked = sorted(colors.items(), key=lambda kv: (-kv[1], kv[0]))
    chromatic = [c for c, _ in ranked if is_chromatic(c)]
    neutrals = [c for c, _ in ranked if not is_chromatic(c)]

    scores = dict(ranked)
    primary = chromatic[0] if chromatic else "#1f3a5f"
    top_score = scores.get(primary, 1.0)

    # Zweitfarben nur uebernehmen, wenn sie wirklich tragend sind. Jede Website
    # enthaelt Status-Gruen und Fehler-Rot; als "Hausfarbe" ausgegeben wuerden sie
    # die Bewerbung falsch einfaerben. Lieber keine Zweitfarbe als eine falsche -
    # die Vorlagen kommen mit Abstufungen der Primaerfarbe gut allein zurecht.
    top_brand = max(brand_hits.values(), default=0.0)

    def strong(c: str) -> bool:
        if scores.get(c, 0.0) < 0.5 * top_score:
            return False
        # Zusaetzlich echtes Marken-Signal verlangen, nicht blosse Haeufigkeit.
        return top_brand == 0.0 or brand_hits.get(c, 0.0) >= 0.25 * top_brand

    # Gleicher Farbton, andere Helligkeit: fast immer eine echte Palettenvariante.
    primary_alt = next((c for c in chromatic[1:]
                        if hue_distance(c, primary) <= 25 and strong(c)), None)
    secondary = next((c for c in chromatic[1:]
                      if hue_distance(c, primary) > 25 and strong(c)), None)
    accent = next((c for c in chromatic[1:]
                   if c not in (secondary, primary_alt)
                   and hue_distance(c, primary) > 40
                   and (secondary is None or hue_distance(c, secondary) > 25)
                   and strong(c)), None)

    dark_neutrals = [c for c in neutrals if luminance(c) < 0.18]
    ink = dark_neutrals[0] if dark_neutrals else "#1a1a1a"
    if contrast(ink, "#ffffff") < 10:
        ink = "#1a1a1a"

    usable = {f: v for f, v in fonts.items() if not ICON_FONTS.search(f)}
    heading_font = max(usable.items(), key=lambda kv: kv[1]["heading"], default=None)
    body_font = max(usable.items(), key=lambda kv: kv[1]["body"] + kv[1]["other"],
                    default=None)
    h_orig, h_stack, h_kind = map_font(
        heading_font[0] if heading_font and heading_font[1]["heading"] > 0 else None)
    b_orig, b_stack, b_kind = map_font(
        body_font[0] if body_font and sum(body_font[1].values()) > 0 else None)
    if not h_orig:
        h_orig, h_stack, h_kind = b_orig, b_stack, b_kind

    primary_text = darken_until_readable(primary)
    on_primary = "#ffffff" if contrast(primary, "#ffffff") >= 4.0 else ink

    logos = []
    for href in page.logos[:6]:
        logos.append(urllib.parse.urljoin(final_url, href))

    return {
        "source_url": final_url,
        "site_title": page.title[:120],
        "colors": {
            "primary": primary,
            "primary_alt": primary_alt,
            "primary_text": primary_text,
            "on_primary": on_primary,
            "secondary": secondary,
            "accent": accent,
            "ink": ink,
            "muted": muted_tone(primary),
            "rule": shade(primary, 0.86),
            "wash": shade(primary, 0.965),
        },
        "contrast": {
            "primary_on_white": contrast(primary, "#ffffff"),
            "primary_text_on_white": contrast(primary_text, "#ffffff"),
            "ink_on_white": contrast(ink, "#ffffff"),
        },
        "fonts": {
            "heading_original": h_orig,
            "heading_stack": h_stack,
            "heading_kind": h_kind,
            "body_original": b_orig,
            "body_stack": b_stack,
            "body_kind": b_kind,
        },
        "logo_candidates": logos,
        "evidence": {
            "top_colors": [{"hex": c, "score": round(s, 1)} for c, s in ranked[:12]],
            "fonts_seen": sorted(fonts.keys())[:12],
            "stylesheets_read": loaded,
        },
        "notes": [
            "Markenfarben nur als Akzent verwenden - Fliesstext bleibt ink auf Weiss.",
            "Firmenlogo NICHT in die eigenen Unterlagen uebernehmen; nur Farb- und "
            "Schriftsprache adaptieren.",
        ],
    }


CSS_TEMPLATE = """/* Automatisch aus {source} abgeleitet. */
:root {{
  --primary: {primary};
  --primary-text: {primary_text};
  --on-primary: {on_primary};
  --secondary: {secondary};
  --accent: {accent};
  --ink: {ink};
  --muted: {muted};
  --rule: {rule};
  --wash: {wash};
  --font-heading: {heading_stack};
  --font-body: {body_stack};
}}
"""


def emit_css(brand: dict) -> str:
    c = brand["colors"]
    f = brand["fonts"]
    return CSS_TEMPLATE.format(
        source=brand["source_url"],
        primary=c["primary"],
        primary_text=c["primary_text"],
        on_primary=c["on_primary"],
        secondary=c["secondary"] or c["primary_text"],
        accent=c["accent"] or c["muted"],
        ink=c["ink"],
        muted=c["muted"],
        rule=c["rule"],
        wash=c["wash"],
        heading_stack=f["heading_stack"],
        body_stack=f["body_stack"],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="Startseite der Firma, z.B. https://firma.de")
    ap.add_argument("-o", "--out", default="brand.json", help="Ziel fuer brand.json")
    ap.add_argument("--emit-css", metavar="PFAD",
                    help="schreibt zusaetzlich ein CSS mit :root-Variablen")
    ap.add_argument("--max-css", type=int, default=10,
                    help="maximale Anzahl geladener Stylesheets (Standard 10)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = ap.parse_args()

    brand = extract(args.url, args.max_css, args.timeout)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(brand, fh, indent=2, ensure_ascii=False)
    print(f"✓ {args.out}", file=sys.stderr)

    if args.emit_css:
        with open(args.emit_css, "w", encoding="utf-8") as fh:
            fh.write(emit_css(brand))
        print(f"✓ {args.emit_css}", file=sys.stderr)

    c = brand["colors"]
    print(json.dumps({
        "primary": c["primary"],
        "primary_text": c["primary_text"],
        "secondary": c["secondary"],
        "heading_font": brand["fonts"]["heading_original"] or "(keine)",
        "body_font": brand["fonts"]["body_original"] or "(keine)",
        "contrast_primary_on_white": brand["contrast"]["primary_on_white"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
