/* Bewerbungsassistent - Oberflaechenlogik. Kein Framework, kein Build-Schritt. */

const $ = (auswahl) => document.querySelector(auswahl);
const $$ = (auswahl) => [...document.querySelectorAll(auswahl)];

const STATUS_TEXT = {
  entwurf: "Entwurf",
  gesendet: "Gesendet",
  gespraech: "Gespräch",
  zusage: "Zusage",
  absage: "Absage",
};

let zustand = { ansicht: "uebersicht", offen: null, timer: null };

/* ---------------------------------------------------------------- Werkzeug */

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

async function hole(pfad, optionen = {}) {
  const antwort = await fetch(pfad, {
    headers: { "Content-Type": "application/json" },
    ...optionen,
  });
  const daten = await antwort.json().catch(() => ({}));
  if (!antwort.ok) throw new Error(daten.fehler || `Fehler ${antwort.status}`);
  return daten;
}

function datum(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" });
}

function abzeichen(status) {
  return `<span class="abzeichen st-${esc(status)}">${esc(STATUS_TEXT[status] || status)}</span>`;
}

/* ------------------------------------------------------------- Navigation */

function zeige(ansicht) {
  zustand.ansicht = ansicht;
  $$(".ansicht").forEach((el) => (el.hidden = el.id !== `ansicht-${ansicht}`));
  $$("nav button").forEach((b) =>
    b.setAttribute("aria-current", b.dataset.ansicht === ansicht ? "page" : "false"));
  window.scrollTo(0, 0);
}

$$("nav button").forEach((b) =>
  b.addEventListener("click", () => { location.hash = `#/${b.dataset.ansicht}`; }));

$("#zurueck").addEventListener("click", () => { location.hash = "#/uebersicht"; });

/* Die Adresse fuehrt die Ansicht - so bleibt ein Neuladen auf derselben
   Bewerbung stehen, und der Zurueck-Knopf des Browsers tut das Erwartete. */
function routen() {
  const ziel = (location.hash || "#/uebersicht").replace(/^#\/?/, "");
  const detail = ziel.match(/^bewerbung\/([0-9a-f]+)$/);
  stoppePolling();

  if (detail) {
    zustand.offen = detail[1];
    zeige("detail");
    $("#detail-inhalt").innerHTML = `<div class="leer">Wird geladen …</div>`;
    ladeDetail();
    return;
  }
  zustand.offen = null;
  if (ziel === "profil") { zeige("profil"); ladeProfil(); return; }
  zeige("uebersicht");
  ladeUebersicht();
}

window.addEventListener("hashchange", routen);

/* -------------------------------------------------------------- Übersicht */

async function ladeUebersicht() {
  let daten;
  try {
    daten = await hole("/api/uebersicht");
  } catch (fehler) {
    $("#liste").innerHTML = `<div class="hinweis warnung">${esc(fehler.message)}</div>`;
    return;
  }

  const k = daten.kennzahlen;
  const kacheln = [
    { wert: k.gesamt, text: "Bewerbungen gesamt" },
    { wert: k.im_rennen, text: "laufend" },
    { wert: k.nach_status.gespraech, text: "Gespräche" },
    { wert: k.nach_status.zusage, text: "Zusagen", gut: k.nach_status.zusage > 0 },
  ];
  // Die Antwortquote nur zeigen, wenn schon etwas zurueckkam - eine grosse
  // Null waere hier keine Information, sondern nur entmutigend.
  if (k.quote !== null && k.quote !== undefined) {
    kacheln.push({ wert: k.quote + " %", text: "Rückmeldungen" });
  }
  $("#kennzahlen").innerHTML = kacheln.map((kachel) => `
    <div class="kachel${kachel.gut ? " gut" : ""}">
      <div class="wert">${esc(kachel.wert)}</div>
      <div class="beschriftung">${esc(kachel.text)}</div>
    </div>`).join("");

  zeigeSchluessel(daten.schluessel);

  $("#profil-warnung").innerHTML = daten.profil_fehlt.length
    ? `<div class="hinweis warnung">
         <p><strong>Im Profil fehlt noch: ${esc(daten.profil_fehlt.join(", "))}.</strong></p>
         <p>Ohne diese Angaben lassen sich keine Unterlagen erstellen, ohne etwas zu erfinden.
            <button type="button" class="link-knopf" onclick="document.querySelector('nav button[data-ansicht=profil]').click()">Jetzt ausfüllen</button></p>
       </div>`
    : "";

  const liste = daten.bewerbungen;
  $("#liste").innerHTML = liste.length
    ? liste.map(eintragHtml).join("")
    : `<div class="leer">Noch keine Bewerbung. Füge oben den Link zu einer Stellenanzeige ein.</div>`;

  $$("#liste .eintrag").forEach((el) =>
    el.addEventListener("click", () => oeffne(el.dataset.id)));

  // Solange etwas laeuft, im Hintergrund weiter aktualisieren.
  const laeuft = liste.some((b) => b.phase !== "fertig" && b.phase !== "fehler");
  planePolling(laeuft && zustand.ansicht === "uebersicht" ? ladeUebersicht : null);
}

// Ohne Schluessel geht nichts - deshalb steht die Abfrage ganz oben und nicht
// in einem Einstellungsmenue, das niemand sucht. Und sie bleibt auch dann
// erreichbar, wenn schon einer hinterlegt ist: Ein falsch eingetragener
// Schluessel liess sich sonst ueberhaupt nicht mehr korrigieren - die
// Oberflaeche blendete das Feld aus, weil ja "einer da war", und jede
// Bewerbung scheiterte weiter an derselben Ablehnung.
function zeigeSchluessel(vorhanden, aufgeklappt = false) {
  const ziel = $("#schluessel-warnung");

  if (vorhanden && !aufgeklappt) {
    ziel.innerHTML = `
      <p class="schluessel-zeile">
        API-Schlüssel ist hinterlegt.
        <button type="button" class="link-knopf" id="schluessel-aendern">Schlüssel ändern</button>
        <button type="button" class="link-knopf" id="schluessel-testen">jetzt testen</button>
        <span id="schluessel-status"></span>
      </p>`;
    $("#schluessel-aendern").addEventListener("click",
      () => zeigeSchluessel(true, true));
    $("#schluessel-testen").addEventListener("click", async () => {
      const status = $("#schluessel-status");
      status.textContent = "wird geprüft …";
      status.className = "";
      try {
        const antwort = await hole("/api/schluessel/pruefen", { method: "POST" });
        if (antwort.ok) {
          status.textContent = antwort.meldung;
          status.className = "status-gut";
          return;
        }
        // Funktioniert er nicht, ist die Meldung allein nutzlos - das
        // Eingabefeld muss gleich mit aufgehen.
        zeigeSchluessel(true, true);
        $("#schluessel-fehler").textContent = antwort.meldung;
      } catch (fehler) {
        status.textContent = fehler.message;
        status.className = "status-schlecht";
      }
    });
    return;
  }

  ziel.innerHTML = `
    <div class="hinweis warnung">
      <p><strong>${vorhanden ? "Neuen API-Schlüssel eintragen" : "Einmalig: API-Schlüssel eintragen"}</strong></p>
      <p>Das Tool nutzt Claude für die Analyse und die Texte. Den Schlüssel gibt es
         unter <code>console.anthropic.com/settings/keys</code> — er beginnt mit
         <code>sk-ant-</code> und bleibt auf diesem Rechner.</p>
      <p>Wichtig: Der Schlüssel wird nur ein einziges Mal angezeigt. Kopiere ihn
         vollständig — er ist rund 100 Zeichen lang.</p>
      <div class="neu-zeile" style="margin-top:9px">
        <input type="password" id="schluessel-feld" placeholder="sk-ant-..."
               autocomplete="off" style="flex:1 1 300px">
        <button class="knopf" id="schluessel-speichern">Prüfen und speichern</button>
      </div>
      <p id="schluessel-fehler" style="margin-top:7px;color:var(--absage)"></p>
    </div>`;

  const speichern = async () => {
    const feld = $("#schluessel-feld");
    const meldung = $("#schluessel-fehler");
    const knopf = $("#schluessel-speichern");
    knopf.disabled = true;
    // Der Schluessel wird vor dem Speichern gegen die API geprueft. Das dauert
    // einen Moment - ohne Rueckmeldung sieht das aus, als sei der Klick ins
    // Leere gegangen, und es wird ein zweites Mal geklickt.
    meldung.textContent = "Schlüssel wird geprüft …";
    meldung.style.color = "var(--text-still)";
    try {
      await hole("/api/schluessel", {
        method: "POST", body: JSON.stringify({ schluessel: feld.value }),
      });
      ladeUebersicht();
    } catch (fehler) {
      meldung.textContent = fehler.message;
      meldung.style.color = "var(--absage)";
    } finally {
      knopf.disabled = false;
    }
  };

  $("#schluessel-speichern").addEventListener("click", speichern);
  $("#schluessel-feld").addEventListener("keydown", (e) => {
    if (e.key === "Enter") speichern();
  });
}

function eintragHtml(b) {
  const laeuft = b.phase !== "fertig" && b.phase !== "fehler";
  const meta = [b.firma, b.ort, datum(b.erstellt)].filter(Boolean).join(" · ");

  let rechts = abzeichen(b.status);
  if (laeuft) {
    rechts = `<span style="font-size:12.5px;color:var(--text-leise)">${esc(b.phase)} …</span>`;
  } else if (b.phase === "fehler") {
    rechts = `<span class="abzeichen st-absage">Fehler</span>`;
  }

  return `
    <button class="eintrag" data-id="${esc(b.id)}">
      <div class="eintrag-text">
        <div class="eintrag-titel">${esc(b.titel)}</div>
        <div class="eintrag-meta">${esc(meta)}</div>
        ${laeuft ? `<div class="fortschritt" style="margin-top:8px"><div style="width:${b.fortschritt}%"></div></div>` : ""}
      </div>
      ${rechts}
    </button>`;
}

/* ------------------------------------------------------- Neue Bewerbung */

$("#text-umschalten").addEventListener("click", () => {
  const bereich = $("#text-bereich");
  bereich.hidden = !bereich.hidden;
  if (!bereich.hidden) $("#neu-text").focus();
});

$("#neu-url").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#neu-start").click();
});

$("#neu-start").addEventListener("click", async () => {
  const knopf = $("#neu-start");
  const url = $("#neu-url").value.trim();
  const text = $("#neu-text").value.trim();
  $("#neu-fehler").innerHTML = "";

  if (!url && !text) {
    $("#neu-fehler").innerHTML =
      `<div class="hinweis warnung">Bitte einen Link zur Stellenanzeige einfügen.</div>`;
    return;
  }

  knopf.disabled = true;
  knopf.textContent = "Wird gestartet …";
  try {
    const eintrag = await hole("/api/bewerbungen", {
      method: "POST",
      body: JSON.stringify({ url, text }),
    });
    $("#neu-url").value = "";
    $("#neu-text").value = "";
    $("#text-bereich").hidden = true;
    oeffne(eintrag.id);
  } catch (fehler) {
    $("#neu-fehler").innerHTML = `<div class="hinweis warnung">${esc(fehler.message)}</div>`;
  } finally {
    knopf.disabled = false;
    knopf.textContent = "Unterlagen erstellen";
  }
});

/* ------------------------------------------------------------------ Detail */

function planePolling(fn) {
  stoppePolling();
  if (fn) zustand.timer = setTimeout(fn, 2500);
}
function stoppePolling() {
  if (zustand.timer) clearTimeout(zustand.timer);
  zustand.timer = null;
}

function oeffne(id) {
  location.hash = `#/bewerbung/${id}`;
}

async function ladeDetail() {
  if (!zustand.offen) return;
  let b;
  try {
    b = await hole(`/api/bewerbungen/${zustand.offen}`);
  } catch (fehler) {
    $("#detail-inhalt").innerHTML = `<div class="hinweis warnung">${esc(fehler.message)}</div>`;
    return;
  }
  if (zustand.offen !== b.id) return;

  $("#detail-inhalt").innerHTML = detailHtml(b);
  verdrahteDetail(b);

  const laeuft = b.phase !== "fertig" && b.phase !== "fehler";
  planePolling(laeuft && zustand.ansicht === "detail" ? ladeDetail : null);

  if (b.phase === "fertig" && b.dateien && Object.keys(b.dateien).length) {
    ladeBriefing(b.id);
  }
}

function detailHtml(b) {
  const laeuft = b.phase !== "fertig" && b.phase !== "fehler";
  const a = b.analyse || {};

  let kopf = `
    <h1>${esc(b.titel)}</h1>
    <p class="unterzeile">
      ${esc([b.firma, b.ort].filter(Boolean).join(" · "))}
      ${b.url && b.url.startsWith("http") ? ` · <a href="${esc(b.url)}" target="_blank" rel="noopener">Anzeige öffnen</a>` : ""}
    </p>`;

  if (laeuft) {
    return kopf + `
      <div class="karte">
        <div class="fortschritt"><div style="width:${b.fortschritt}%"></div></div>
        <p class="laufend">${esc(b.phase)} … Das dauert ein bis zwei Minuten.</p>
      </div>`;
  }

  if (b.phase === "fehler") {
    return kopf + `
      <div class="hinweis warnung">
        <p><strong>Das hat nicht geklappt.</strong></p>
        <p>${esc(b.fehler)}</p>
      </div>
      <div class="karte">
        <label for="wiederhole-text">Anzeigentext einfügen und erneut versuchen</label>
        <textarea id="wiederhole-text" placeholder="Vollständigen Text der Stellenanzeige …"></textarea>
        <div style="margin-top:10px;display:flex;gap:9px">
          <button class="knopf" id="wiederholen">Erneut versuchen</button>
          <button class="knopf gefahr" id="loeschen">Löschen</button>
        </div>
      </div>`;
  }

  /* -------- Statuszeile -------- */
  const statusWahl = Object.entries(STATUS_TEXT).map(
    ([wert, text]) => `<option value="${wert}"${b.status === wert ? " selected" : ""}>${esc(text)}</option>`
  ).join("");

  let html = kopf + `
    <div class="karte" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
      <div style="flex:1;min-width:180px">
        <label for="status-wahl">Status</label>
        <select id="status-wahl">${statusWahl}</select>
      </div>
      <div style="flex:2;min-width:220px">
        <label for="notiz">Notiz (nur für mich)</label>
        <input type="text" id="notiz" value="${esc(b.notiz || "")}" placeholder="z. B. Nachfassen am 12.08.">
      </div>
    </div>`;

  /* -------- Dokumente -------- */
  const dateien = Object.entries(b.dateien || {});
  if (dateien.length) {
    html += `<h2>Unterlagen</h2><div class="dokumente">`;
    for (const [art, info] of dateien) {
      const pfad = `/api/bewerbungen/${b.id}/datei/${info.datei}`;
      const seitenText = info.seiten
        ? `${info.seiten} Seite${info.seiten === 1 ? "" : "n"}` : "PDF";
      html += `
        <div class="dokument">
          <div class="dokument-name">${esc(art)}
            <span class="dokument-meta"> · ${esc(seitenText)}</span></div>
          <a class="knopf leise" href="${pfad}" download="${esc(info.download)}"
             style="text-decoration:none">Herunterladen</a>
          <button class="knopf leise" data-vorschau="${pfad}">Ansehen</button>
        </div>`;
    }
    html += `</div><div id="vorschau"></div>`;
  }

  /* -------- Passung und Lücken -------- */
  html += `<h2>Einschätzung</h2>`;
  if (b.passung) {
    const klasse = b.passung === "hoch" ? "gut" : b.passung === "niedrig" ? "warnung" : "";
    html += `<div class="hinweis ${klasse}">
      <p><strong>Passung: ${esc(b.passung)}</strong></p>
      <p>${esc(b.passung_begruendung || "")}</p>
    </div>`;
  }

  if ((b.luecken || []).length) {
    html += `<div class="karte">
      <h3>Lücken — das fehlt gegenüber der Anzeige</h3>
      <p style="margin:-4px 0 10px;font-size:13.5px;color:var(--text-leise)">
        Steht in keinem Dokument. Im Gespräch kommt es aber wahrscheinlich zur Sprache.</p>
      <ul class="knapp">` +
      b.luecken.map((l) => `<li><strong>${esc(l.anforderung)}</strong>${
        l.naechstliegendes ? ` — am nächsten dran: ${esc(l.naechstliegendes)}` : ""
      }${l.umgang ? `<br><span style="color:var(--text-leise)">${esc(l.umgang)}</span>` : ""}</li>`).join("") +
      `</ul></div>`;
  } else if (b.phase === "fertig") {
    html += `<div class="hinweis gut"><p>Keine offenen Lücken gegenüber den Anforderungen der Anzeige.</p></div>`;
  }

  /* -------- Analyse -------- */
  if (a.muss || a.kann) {
    html += `<h2>Was die Anzeige verlangt</h2><div class="karten">`;
    for (const [titel, schluessel] of [["Muss-Anforderungen", "muss"], ["Kann-Anforderungen", "kann"]]) {
      const punkte = a[schluessel] || [];
      if (!punkte.length) continue;
      html += `<div class="karte"><h3>${esc(titel)}</h3><ul class="knapp">` +
        punkte.map((p) => `<li>${esc(p.anforderung)}${
          p.gewicht >= 3 ? ` <span style="color:var(--text-leise)">(hohes Gewicht)</span>` : ""
        }</li>`).join("") + `</ul></div>`;
    }
    html += `</div>`;
  }

  if ((a.zwischen_den_zeilen || []).length) {
    html += `<div class="karte" style="margin-top:12px">
      <h3>Zwischen den Zeilen</h3>
      <p style="margin:-4px 0 10px;font-size:13.5px;color:var(--text-leise)">
        Deutungen, keine Fakten — als Gesprächsstoff gedacht.</p>
      <ul class="knapp">${a.zwischen_den_zeilen.map((z) => `<li>${esc(z)}</li>`).join("")}</ul></div>`;
  }

  if ((a.warnsignale || []).length) {
    html += `<div class="hinweis warnung"><p><strong>Auffälligkeiten in der Anzeige</strong></p>
      <ul class="knapp">${a.warnsignale.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>`;
  }

  /* -------- Design -------- */
  const brand = b.brand || {};
  if (brand.colors) {
    const f = brand.colors;
    html += `<h2>Übernommenes Firmendesign</h2>
      <div class="karte">
        <p style="margin:0 0 9px">
          <span class="farbtupfer" style="background:${esc(f.primary)}"></span>
          <code>${esc(f.primary)}</code>
          ${brand.fonts && brand.fonts.heading_original
            ? ` · Hausschrift <strong>${esc(brand.fonts.heading_original)}</strong>` : ""}
        </p>
        <p style="margin:0;font-size:13.5px;color:var(--text-leise)">
          Abgeleitet von ${esc(brand.source_url || "")}. Die Farbe wird nur als Akzent
          eingesetzt — Fließtext bleibt schwarz auf Weiß. Das Firmenlogo wird nicht übernommen.
        </p>
      </div>`;
  }

  /* -------- Gespräch -------- */
  html += `<h2>Vorstellungsgespräch</h2>
    <div id="briefing"><div class="leer">Briefing wird geladen …</div></div>`;

  html += `<div style="margin-top:28px"><button class="knopf gefahr" id="loeschen">Bewerbung löschen</button></div>`;
  return html;
}

function verdrahteDetail(b) {
  const wahl = $("#status-wahl");
  if (wahl) {
    wahl.addEventListener("change", async () => {
      await hole(`/api/bewerbungen/${b.id}`, {
        method: "POST", body: JSON.stringify({ status: wahl.value }),
      });
    });
  }

  const notiz = $("#notiz");
  if (notiz) {
    let timer;
    notiz.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        hole(`/api/bewerbungen/${b.id}`, {
          method: "POST", body: JSON.stringify({ notiz: notiz.value }),
        }).catch(() => {});
      }, 600);
    });
  }

  $$("[data-vorschau]").forEach((knopf) =>
    knopf.addEventListener("click", () => {
      $("#vorschau").innerHTML =
        `<iframe class="pdf-rahmen" src="${esc(knopf.dataset.vorschau)}" title="Vorschau"></iframe>`;
      $("#vorschau").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));

  const wiederholen = $("#wiederholen");
  if (wiederholen) {
    wiederholen.addEventListener("click", async () => {
      wiederholen.disabled = true;
      try {
        await hole(`/api/bewerbungen/${b.id}/neu`, {
          method: "POST",
          body: JSON.stringify({ text: ($("#wiederhole-text") || {}).value || "" }),
        });
        ladeDetail();
      } catch (fehler) {
        alert(fehler.message);
        wiederholen.disabled = false;
      }
    });
  }

  const loeschen = $("#loeschen");
  if (loeschen) {
    loeschen.addEventListener("click", async () => {
      if (!confirm("Diese Bewerbung mit allen Dokumenten löschen?")) return;
      await fetch(`/api/bewerbungen/${b.id}`, { method: "DELETE" });
      location.hash = "#/uebersicht";
    });
  }
}

async function ladeBriefing(id) {
  const ziel = $("#briefing");
  if (!ziel) return;
  try {
    const antwort = await fetch(`/api/bewerbungen/${id}/datei/gespraech.md`);
    if (!antwort.ok) throw new Error();
    ziel.innerHTML = `<div class="karte md scrollbar">${markdown(await antwort.text())}</div>`;
  } catch {
    ziel.innerHTML = `<div class="leer">Keine Gesprächsvorbereitung vorhanden.</div>`;
  }
}

/* --------------------------------------------------- Minimales Markdown */

/* Reicht fuer das Briefing: Ueberschriften, Tabellen, Listen, Fett, Code.
   Alles wird vorher escaped, damit Modelltext kein HTML einschleusen kann. */
function markdown(roh) {
  const zeilen = esc(roh).split("\n");
  const aus = [];
  let liste = null, tabelle = false;

  const inline = (t) => t
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  const schliesseListe = () => { if (liste) { aus.push(`</${liste}>`); liste = null; } };
  const schliesseTabelle = () => { if (tabelle) { aus.push("</tbody></table>"); tabelle = false; } };

  for (let i = 0; i < zeilen.length; i++) {
    const zeile = zeilen[i];
    const roh_ = zeile.trim();

    if (!roh_) { schliesseListe(); schliesseTabelle(); continue; }

    const ueber = roh_.match(/^(#{1,4})\s+(.*)$/);
    if (ueber) {
      schliesseListe(); schliesseTabelle();
      const stufe = Math.min(ueber[1].length, 4);
      aus.push(`<h${stufe}>${inline(ueber[2])}</h${stufe}>`);
      continue;
    }

    // Tabelle: Kopfzeile gefolgt von einer Trennzeile aus |---|
    if (roh_.startsWith("|") && !tabelle &&
        /^\|[\s:|-]+\|$/.test((zeilen[i + 1] || "").trim())) {
      schliesseListe();
      const kopf = roh_.split("|").slice(1, -1).map((z) => z.trim());
      aus.push(`<table><thead><tr>${
        kopf.map((z) => `<th>${inline(z)}</th>`).join("")}</tr></thead><tbody>`);
      tabelle = true;
      i++;  // Trennzeile ueberspringen
      continue;
    }
    if (tabelle && roh_.startsWith("|")) {
      const zellen = roh_.split("|").slice(1, -1).map((z) => z.trim());
      aus.push(`<tr>${zellen.map((z) => `<td>${inline(z)}</td>`).join("")}</tr>`);
      continue;
    }
    schliesseTabelle();

    if (/^[-*]\s+/.test(roh_)) {
      if (liste !== "ul") { schliesseListe(); aus.push("<ul>"); liste = "ul"; }
      aus.push(`<li>${inline(roh_.replace(/^[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (/^\d+\.\s+/.test(roh_)) {
      if (liste !== "ol") { schliesseListe(); aus.push("<ol>"); liste = "ol"; }
      aus.push(`<li>${inline(roh_.replace(/^\d+\.\s+/, ""))}</li>`);
      continue;
    }
    schliesseListe();

    if (roh_.startsWith("&gt;")) {
      aus.push(`<blockquote>${inline(roh_.replace(/^&gt;\s?/, ""))}</blockquote>`);
      continue;
    }
    aus.push(`<p>${inline(roh_)}</p>`);
  }
  schliesseListe(); schliesseTabelle();
  return aus.join("\n");
}

/* ------------------------------------------------------------------ Profil */

const LISTEN = {
  stationen: {
    titel: "Station",
    felder: [["position", "Position", "text"], ["firma", "Firma", "text"],
             ["ort", "Ort", "text"], ["von", "Von (MM/JJJJ)", "text"],
             ["bis", "Bis (MM/JJJJ oder heute)", "text"],
             ["aufgaben", "Aufgaben", "area"],
             ["erfolge", "Erfolge mit Zahlen", "area"],
             ["tools", "Werkzeuge / Methoden", "text"]],
  },
  ausbildung: {
    titel: "Abschluss",
    felder: [["abschluss", "Abschluss und Fach", "text"], ["institut", "Hochschule / Schule", "text"],
             ["ort", "Ort", "text"], ["von", "Von", "text"], ["bis", "Bis", "text"],
             ["note", "Note (nur wenn gut)", "text"],
             ["schwerpunkt", "Schwerpunkte, Abschlussarbeit", "area"]],
  },
  kenntnisse: {
    titel: "Kategorie",
    felder: [["kategorie", "Kategorie", "text"], ["werte", "Kenntnisse (kommagetrennt)", "text"]],
  },
  sprachen: {
    titel: "Sprache",
    felder: [["sprache", "Sprache", "text"], ["niveau", "Niveau", "text"]],
  },
};

let profilDaten = null;

async function ladeProfil() {
  profilDaten = await hole("/api/profil");
  const p = profilDaten.person || {}, s = profilDaten.situation || {};
  for (const [feld, wert] of Object.entries(p)) {
    const el = $(`#p-${feld}`); if (el) el.value = wert || "";
  }
  for (const [feld, wert] of Object.entries(s)) {
    const el = $(`#s-${feld}`); if (el) el.value = wert || "";
  }
  $("#p-weiteres").value = profilDaten.weiteres || "";
  $("#p-luecken").value = profilDaten.luecken || "";
  for (const name of Object.keys(LISTEN)) zeichneListe(name);
}

function zeichneListe(name) {
  const eintraege = profilDaten[name] || [];
  const konfig = LISTEN[name];
  $(`#${name}`).innerHTML = eintraege.map((eintrag, index) => `
    <div class="station" data-liste="${name}" data-index="${index}">
      <div class="station-kopf">
        <strong>${esc(konfig.titel)} ${index + 1}</strong>
        <button class="knopf leise" data-entfernen="${name}:${index}">Entfernen</button>
      </div>
      ${konfig.felder.map(([feld, beschriftung, art]) => `
        <div class="feld">
          <label>${esc(beschriftung)}</label>
          ${art === "area"
            ? `<textarea data-feld="${feld}" style="min-height:64px">${esc(eintrag[feld] || "")}</textarea>`
            : `<input type="text" data-feld="${feld}" value="${esc(eintrag[feld] || "")}">`}
        </div>`).join("")}
    </div>`).join("");

  $$(`#${name} [data-entfernen]`).forEach((knopf) =>
    knopf.addEventListener("click", () => {
      const [liste, index] = knopf.dataset.entfernen.split(":");
      sammleListen();
      profilDaten[liste].splice(Number(index), 1);
      zeichneListe(liste);
    }));
}

$$("[data-hinzu]").forEach((knopf) =>
  knopf.addEventListener("click", () => {
    const name = knopf.dataset.hinzu;
    sammleListen();
    (profilDaten[name] = profilDaten[name] || []).push({});
    zeichneListe(name);
    const letzte = $(`#${name}`).lastElementChild;
    if (letzte) letzte.querySelector("input, textarea")?.focus();
  }));

function sammleListen() {
  if (!profilDaten) return;
  for (const name of Object.keys(LISTEN)) {
    profilDaten[name] = $$(`#${name} .station`).map((block) => {
      const eintrag = {};
      block.querySelectorAll("[data-feld]").forEach((el) => {
        eintrag[el.dataset.feld] = el.value.trim();
      });
      return eintrag;
    }).filter((e) => Object.values(e).some((v) => v));
  }
}

$("#profil-speichern").addEventListener("click", async () => {
  sammleListen();
  const person = {}, situation = {};
  ["vorname", "nachname", "strasse", "plz_ort", "email", "telefon", "web", "berufsbezeichnung"]
    .forEach((f) => (person[f] = ($(`#p-${f}`) || {}).value?.trim() || ""));
  ["verfuegbar_ab", "gehaltsvorstellung", "umzug", "wechselgrund"]
    .forEach((f) => (situation[f] = ($(`#s-${f}`) || {}).value?.trim() || ""));

  const nutzlast = {
    person, situation,
    weiteres: $("#p-weiteres").value.trim(),
    luecken: $("#p-luecken").value.trim(),
  };
  for (const name of Object.keys(LISTEN)) nutzlast[name] = profilDaten[name] || [];

  const status = $("#profil-status");
  status.textContent = "Wird gespeichert …";
  try {
    profilDaten = await hole("/api/profil", { method: "POST", body: JSON.stringify(nutzlast) });
    status.textContent = "Gespeichert.";
    setTimeout(() => (status.textContent = ""), 2500);
  } catch (fehler) {
    status.textContent = fehler.message;
  }
});

/* ------------------------------------------------------------------ Start */

routen();
