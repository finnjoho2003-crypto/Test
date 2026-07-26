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

// Muss mit API_STAND in server.py uebereinstimmen. Passt es nicht, laeuft der
// Dienst noch in einer aelteren Fassung als diese Oberflaeche - siehe die
// Erklaerung an der Konstante dort.
const BENOETIGTER_STAND = 5;

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
  // Stimme und Mikrofon gehoeren zur Gespraechsansicht. Laufen sie weiter,
  // waehrend jemand das Profil bearbeitet, ist das schlicht unheimlich.
  if (zustand.ansicht === "gespraech" && ansicht !== "gespraech") {
    stimmeAus(); hoerenBeenden();
  }
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
  if (ziel === "jobsuche") { zeige("jobsuche"); return; }
  if (ziel === "gespraech") {
    zeige("gespraech");
    // Ein weiterlaufender Sprecher beim Verlassen der Ansicht waere gruselig.
    if ($("#g-lauf").hidden) ladeGespraeche();
    return;
  }
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

  // Veralteten Dienst erkennen, bevor die Person auf einen Knopf drueckt, den
  // er noch nicht kennt. Ein "404" waere hier die unbrauchbarste aller
  // Antworten: Es klingt nach kaputt, dabei fehlt nur ein Neustart.
  $("#neustart-warnung").innerHTML =
    (daten.api_stand || 1) >= BENOETIGTER_STAND ? "" : `
      <div class="hinweis warnung">
        <p><strong>Der Assistent läuft noch in einer älteren Fassung.</strong></p>
        <p>Die Programmdateien wurden aktualisiert, der laufende Dienst kennt
           sie aber noch nicht. Ein Neustart genügt — es geht nichts verloren.</p>
        <p>Im Terminal <strong>Strg</strong>+<strong>C</strong> drücken, dann:</p>
        <p><code>bash starten.sh</code></p>
        <p>Danach diese Seite neu laden.</p>
      </div>`;

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
  // Bei mehreren Profilen ist die Zuordnung wichtig - sonst weiss man
  // spaeter nicht mehr, welcher Werdegang in dieser Bewerbung steckt.
  const meta = [b.firma, b.ort, b.profil_name, datum(b.erstellt)]
    .filter(Boolean).join(" · ");

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

  /* -------- Firmendesign -------- */
  // Bleibt die Gestaltung neutral, ohne dass jemand sagt warum, wirkt das wie
  // ein Fehler im Programm. Meist ist es keiner: Auf einer Jobbörse steht die
  // Firmenwebsite oft schlicht nicht. Deshalb hier der Grund und gleich das
  // Feld, mit dem es sich beheben lässt.
  if (b.design_hinweis) {
    html += `<div class="hinweis warnung">
      <p><strong>Das Firmendesign wurde nicht übernommen.</strong></p>
      <p>${esc(b.design_hinweis)}</p>
      <div class="neu-zeile" style="margin-top:9px">
        <input type="text" id="firma-website" placeholder="www.firma.de"
               value="${esc(b.firma_website || "")}" style="flex:1 1 260px">
        <button class="knopf" id="design-neu">Übernehmen und neu erstellen</button>
      </div>
    </div>`;
  } else if (b.firma_website && b.phase === "fertig") {
    html += `<p class="schluessel-zeile">Gestaltung abgeleitet von
      <strong>${esc(b.firma_website)}</strong></p>`;
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

  const designNeu = $("#design-neu");
  if (designNeu) {
    designNeu.addEventListener("click", async () => {
      const adresse = $("#firma-website").value.trim();
      if (!adresse) {
        alert("Bitte die Adresse der Firmenwebsite eintragen, z. B. www.firma.de");
        return;
      }
      designNeu.disabled = true;
      try {
        await hole(`/api/bewerbungen/${b.id}/neu`, {
          method: "POST", body: JSON.stringify({ firma_website: adresse }),
        });
        ladeDetail();
      } catch (fehler) {
        alert(fehler.message);
        designNeu.disabled = false;
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


/* ---------------------------------------------------------------- Jobsuche */

// Die Suche laeuft ueber das Websuch-Werkzeug des Modells und dauert ein bis
// zwei Minuten. Ohne sichtbaren Fortschritt wirkt das wie ein Absturz -
// deshalb laeuft waehrenddessen eine Uhr mit.
let jsLaeuft = false;

$("#js-starten").addEventListener("click", async () => {
  if (jsLaeuft) return;
  jsLaeuft = true;
  const knopf = $("#js-starten");
  const status = $("#js-status");
  knopf.disabled = true;
  $("#js-ergebnis").innerHTML = "";

  const start = Date.now();
  const uhr = setInterval(() => {
    const s = Math.round((Date.now() - start) / 1000);
    status.textContent = `Es wird gesucht … (${s} s)`;
  }, 1000);
  status.textContent = "Es wird gesucht … (0 s)";

  try {
    const daten = await hole("/api/jobsuche", {
      method: "POST",
      body: JSON.stringify({ was: $("#js-was").value, wo: $("#js-wo").value }),
    });
    zeigeTreffer(daten);
    status.textContent = `${(daten.stellen || []).length} Treffer.`;
  } catch (fehler) {
    $("#js-ergebnis").innerHTML =
      `<div class="hinweis warnung"><p>${esc(fehler.message)}</p></div>`;
    status.textContent = "";
  } finally {
    clearInterval(uhr);
    knopf.disabled = false;
    jsLaeuft = false;
  }
});

function zeigeTreffer(daten) {
  const stellen = daten.stellen || [];
  let html = "";
  if (daten.hinweis) {
    html += `<div class="hinweis"><p>${esc(daten.hinweis)}</p></div>`;
  }
  if (!stellen.length) {
    html += `<div class="leer">Nichts gefunden. Andere Bezeichnung oder größerer
             Umkreis hilft oft — viele Jobbörsen sperren automatische Zugriffe.</div>`;
    $("#js-ergebnis").innerHTML = html;
    return;
  }

  // Bewusst dieselben Bausteine wie in der Bewerbungsliste - eine zweite
  // Kartenform fuer denselben Zweck macht die Oberflaeche nur unruhiger.
  html += `<h2>Gefundene Stellen</h2><div class="liste">` + stellen.map((s, i) => `
    <div class="treffer">
      <div class="treffer-kopf">
        <div class="eintrag-text">
          <div class="eintrag-titel">${esc(s.titel)}</div>
          <div class="eintrag-meta">${esc([s.firma, s.ort, s.quelle].filter(Boolean).join(" · "))}</div>
        </div>
        <span class="abzeichen st-${s.passung === "hoch" ? "zusage" : s.passung === "niedrig" ? "absage" : "gesendet"}">Passung ${esc(s.passung)}</span>
      </div>
      <p class="knapp-text">${esc(s.warum_passend)}</p>
      ${s.haken ? `<p class="knapp-text" style="color:var(--text-still)"><strong>Zu bedenken:</strong> ${esc(s.haken)}</p>` : ""}
      <div class="neu-zeile" style="margin-top:11px">
        ${s.url ? `<a class="knopf leise" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Anzeige öffnen</a>` : ""}
        ${s.url ? `<button class="knopf" data-bewerben="${i}">Unterlagen erstellen</button>` : ""}
      </div>
    </div>`).join("") + `</div>`;

  $("#js-ergebnis").innerHTML = html;

  // Direkt aus dem Treffer heraus bewerben - der Umweg über Kopieren und
  // Einfügen der Adresse ist genau die Stelle, an der man es dann doch lässt.
  $$("#js-ergebnis [data-bewerben]").forEach((knopf) =>
    knopf.addEventListener("click", async () => {
      const stelle = stellen[Number(knopf.dataset.bewerben)];
      knopf.disabled = true;
      knopf.textContent = "wird angelegt …";
      try {
        const eintrag = await hole("/api/bewerbungen", {
          method: "POST", body: JSON.stringify({ url: stelle.url }),
        });
        location.hash = `#/bewerbung/${eintrag.id}`;
      } catch (fehler) {
        alert(fehler.message);
        knopf.disabled = false;
        knopf.textContent = "Unterlagen erstellen";
      }
    }));
}

/* -------------------------------------------------------------- Foto */

function zeigeFoto(vorhanden) {
  // Zeitstempel gegen den Browser-Zwischenspeicher: Ohne ihn zeigt die
  // Vorschau nach einem Wechsel weiter das alte Bild.
  $("#foto-vorschau").innerHTML = vorhanden
    ? `<img src="/api/profil/foto?t=${Date.now()}" alt="Bewerbungsfoto">`
    : `<span class="foto-leer">kein Foto</span>`;
  $("#foto-entfernen").disabled = !vorhanden;
}

$("#foto-waehlen").addEventListener("click", () => $("#foto-datei").click());

$("#foto-datei").addEventListener("change", async (e) => {
  const datei = e.target.files && e.target.files[0];
  if (!datei) return;
  const status = $("#foto-status");
  if (datei.size > 8 * 1024 * 1024) {
    status.textContent = "Das Bild ist größer als 8 MB. Bitte ein kleineres wählen.";
    return;
  }
  status.textContent = "Bild wird übertragen …";
  try {
    const daten = await new Promise((fertig, schief) => {
      const leser = new FileReader();
      leser.onload = () => fertig(leser.result);
      leser.onerror = () => schief(new Error("Die Datei ließ sich nicht lesen."));
      leser.readAsDataURL(datei);
    });
    await hole("/api/profil/foto", { method: "POST", body: JSON.stringify({ bild: daten }) });
    zeigeFoto(true);
    status.textContent = "Foto gespeichert. Es erscheint in allen neu erstellten Lebensläufen.";
  } catch (fehler) {
    status.textContent = fehler.message;
  } finally {
    e.target.value = "";
  }
});

$("#foto-entfernen").addEventListener("click", async () => {
  await fetch("/api/profil/foto", { method: "DELETE" });
  zeigeFoto(false);
  $("#foto-status").textContent = "Foto entfernt.";
});


/* ------------------------------------------------------------- Übungsgespräch */

/* Sprache läuft im Browser, nicht über die API.
   Anthropics Schnittstelle kennt weder Sprachein- noch -ausgabe — sie nimmt
   Text (und Bilder) und gibt Text zurück. Die Sprachfunktion der Claude-App
   ist Teil dieser App, nicht der Schnittstelle. Beides steckt aber ohnehin
   im Browser: SpeechSynthesis liest vor, SpeechRecognition hört zu. Das
   kostet nichts extra und die Aufnahme verlässt den Rechner nur bei der
   Erkennung. */

const Erkennung = window.SpeechRecognition || window.webkitSpeechRecognition;
const kannHoeren = Boolean(Erkennung);
// Auf den Wert pruefen, nicht auf die Existenz: In manchen Umgebungen ist
// die Eigenschaft vorhanden, aber undefiniert - dann waere jeder Zugriff
// darauf ein Absturz mitten im Gespraech.
const kannSprechen = Boolean(window.speechSynthesis
  && typeof window.SpeechSynthesisUtterance === "function");

let gZustand = { id: null, hoert: false, erkenner: null };

function stimmeAus() {
  if (kannSprechen) window.speechSynthesis.cancel();
}

function vorlesen(text) {
  if (!kannSprechen || !$("#g-vorlesen").checked) return;
  stimmeAus();
  const spruch = new SpeechSynthesisUtterance(text);
  spruch.lang = "de-DE";
  spruch.rate = 1.02;
  // Eine deutsche Stimme, falls vorhanden - sonst liest das System den
  // deutschen Text mit englischer Aussprache vor, was unfreiwillig komisch ist.
  const stimme = window.speechSynthesis.getVoices()
    .find((s) => s.lang && s.lang.toLowerCase().startsWith("de"));
  if (stimme) spruch.voice = stimme;
  window.speechSynthesis.speak(spruch);
}

function sprachhinweis() {
  const ziel = $("#g-sprachhinweis");
  if (!ziel) return;
  if (kannHoeren && kannSprechen) { ziel.innerHTML = ""; return; }
  const fehlt = [];
  if (!kannHoeren) fehlt.push("Zuhören (Mikrofon)");
  if (!kannSprechen) fehlt.push("Vorlesen");
  ziel.innerHTML = `
    <div class="hinweis">
      <p><strong>In diesem Browser fehlt: ${esc(fehlt.join(" und "))}.</strong></p>
      <p>Die Sprachfunktion steckt im Browser, nicht im Assistenten. Am
         zuverlässigsten läuft sie in <strong>Chrome</strong> oder
         <strong>Edge</strong> über die weitergeleitete Adresse
         (<code>https://…app.github.dev</code>) — im Vorschaufenster des
         Editors bekommt die Seite kein Mikrofon.</p>
      <p>Tippen geht immer und ist genauso gültig.</p>
    </div>`;
}

function hoerenStarten() {
  if (!kannHoeren) {
    $("#g-status").textContent =
      "Dieser Browser kann nicht zuhören. In Chrome oder Edge öffnen — oder tippen.";
    return;
  }
  if (gZustand.hoert) { hoerenBeenden(); return; }

  stimmeAus();  // Sonst hört das Mikrofon die eigene Stimme mit.
  const erkenner = new Erkennung();
  erkenner.lang = "de-DE";
  erkenner.continuous = true;
  erkenner.interimResults = true;

  const vorher = $("#g-antwort").value;
  let sicher = "";

  erkenner.onresult = (ereignis) => {
    let vorlaeufig = "";
    for (let i = ereignis.resultIndex; i < ereignis.results.length; i++) {
      const stueck = ereignis.results[i][0].transcript;
      if (ereignis.results[i].isFinal) sicher += stueck;
      else vorlaeufig += stueck;
    }
    // Erkanntes anhängen statt ersetzen - sonst ist Getipptes weg, sobald
    // jemand zusätzlich das Mikrofon benutzt.
    $("#g-antwort").value = (vorher + " " + sicher + vorlaeufig).trim();
  };
  erkenner.onerror = (ereignis) => {
    const texte = {
      "not-allowed": "Das Mikrofon wurde nicht freigegeben. Im Browser oben in der Adresszeile erlauben.",
      "service-not-allowed": "Das Mikrofon wurde nicht freigegeben.",
      "no-speech": "Nichts gehört. Noch einmal versuchen.",
      "audio-capture": "Kein Mikrofon gefunden.",
      "network": "Die Spracherkennung braucht eine Internetverbindung.",
    };
    $("#g-status").textContent = texte[ereignis.error] || `Spracherkennung: ${ereignis.error}`;
    hoerenBeenden();
  };
  erkenner.onend = () => { if (gZustand.hoert) hoerenBeenden(); };

  gZustand.erkenner = erkenner;
  gZustand.hoert = true;
  $("#g-mikro").textContent = "⏹ Fertig";
  $("#g-mikro").classList.add("hoert");
  $("#g-status").textContent = "Es wird zugehört … Zum Beenden noch einmal drücken.";
  erkenner.start();
}

function hoerenBeenden() {
  if (gZustand.erkenner) {
    try { gZustand.erkenner.stop(); } catch (e) { /* schon beendet */ }
  }
  gZustand.erkenner = null;
  gZustand.hoert = false;
  const knopf = $("#g-mikro");
  if (knopf) { knopf.textContent = "🎤 Sprechen"; knopf.classList.remove("hoert"); }
  const status = $("#g-status");
  if (status && status.textContent.startsWith("Es wird zugehört")) status.textContent = "";
}

async function ladeGespraeche() {
  sprachhinweis();
  let daten;
  try { daten = await hole("/api/gespraeche"); }
  catch (fehler) {
    $("#g-liste").innerHTML = `<div class="hinweis warnung">${esc(fehler.message)}</div>`;
    return;
  }

  const wahl = $("#g-bewerbung");
  wahl.innerHTML = daten.bewerbungen.map((b) =>
    `<option value="${esc(b.id)}">${esc(b.titel)}${b.firma ? " — " + esc(b.firma) : ""}</option>`
  ).join("") + `<option value="">Andere Stelle (frei eintragen)</option>`;
  // Ohne fertige Bewerbung bleibt nur der freie Modus - dann ihn gleich zeigen.
  if (!daten.bewerbungen.length) wahl.value = "";
  $("#g-frei").hidden = Boolean(wahl.value);

  $("#g-liste").innerHTML = daten.gespraeche.length
    ? daten.gespraeche.map((g) => `
        <button class="eintrag" data-gespraech="${esc(g.id)}">
          <div class="eintrag-text">
            <div class="eintrag-titel">${esc(g.titel)}</div>
            <div class="eintrag-meta">${esc([g.firma, g.profil_name,
              `${g.runden} Antwort${g.runden === 1 ? "" : "en"}`, datum(g.erstellt)]
              .filter(Boolean).join(" · "))}</div>
          </div>
          ${g.hat_feedback ? `<span class="abzeichen st-zusage">ausgewertet</span>` : ""}
        </button>`).join("")
    : `<div class="leer">Noch nichts geübt.</div>`;

  $$("#g-liste [data-gespraech]").forEach((el) =>
    el.addEventListener("click", () => oeffneGespraech(el.dataset.gespraech)));
}

$("#g-bewerbung").addEventListener("change", (e) => {
  $("#g-frei").hidden = Boolean(e.target.value);
});

$("#g-starten").addEventListener("click", async () => {
  const knopf = $("#g-starten");
  const status = $("#g-startstatus");
  knopf.disabled = true;
  status.textContent = "Das Gegenüber bereitet sich vor …";
  try {
    const g = await hole("/api/gespraeche", {
      method: "POST",
      body: JSON.stringify({
        bewerbung_id: $("#g-bewerbung").value,
        titel: $("#g-titel").value,
        firma: $("#g-firma").value,
      }),
    });
    status.textContent = "";
    zeigeGespraech(g, true);
  } catch (fehler) {
    status.textContent = fehler.message;
  } finally {
    knopf.disabled = false;
  }
});

async function oeffneGespraech(id) {
  try { zeigeGespraech(await hole(`/api/gespraeche/${id}`), false); }
  catch (fehler) { alert(fehler.message); }
}

function zeigeGespraech(g, vorlesenLetzte) {
  gZustand.id = g.id;
  $("#g-start").hidden = true;
  $("#g-lauf").hidden = false;
  $("#g-stelle").textContent = g.titel || "Übungsgespräch";
  $("#g-firma-anzeige").textContent = [g.firma, g.profil_name].filter(Boolean).join(" · ");

  $("#g-verlauf").innerHTML = (g.verlauf || []).map((z) => `
    <div class="g-zeile ${z.rolle === "ich" ? "g-ich" : "g-gegen"}">
      <div class="g-wer">${z.rolle === "ich" ? "Ich" : "Gegenüber"}</div>
      <div class="g-text">${esc(z.text).replace(/\n/g, "<br>")}</div>
    </div>`).join("");

  const letzte = $("#g-verlauf").lastElementChild;
  if (letzte) letzte.scrollIntoView({ behavior: "smooth", block: "nearest" });

  $("#g-feedback").innerHTML = g.feedback ? feedbackHtml(g.feedback) : "";

  const letzteAeusserung = [...(g.verlauf || [])].reverse()
    .find((z) => z.rolle === "recruiter");
  if (vorlesenLetzte && letzteAeusserung) vorlesen(letzteAeusserung.text);
}

async function antwortSenden() {
  const feld = $("#g-antwort");
  const text = feld.value.trim();
  if (!text) { $("#g-status").textContent = "Erst etwas sagen oder tippen."; return; }
  hoerenBeenden();

  const senden = $("#g-senden");
  senden.disabled = true;
  $("#g-status").textContent = "Das Gegenüber überlegt …";
  try {
    const g = await hole(`/api/gespraeche/${gZustand.id}/antwort`, {
      method: "POST", body: JSON.stringify({ text }),
    });
    feld.value = "";
    $("#g-status").textContent = "";
    zeigeGespraech(g, true);
  } catch (fehler) {
    $("#g-status").textContent = fehler.message;
  } finally {
    senden.disabled = false;
  }
}

$("#g-senden").addEventListener("click", antwortSenden);
$("#g-mikro").addEventListener("click", hoerenStarten);
$("#g-antwort").addEventListener("keydown", (e) => {
  // Strg+Enter sendet - Enter allein bleibt der Absatzumbruch, weil Antworten
  // hier mehrere Sätze lang sind.
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) antwortSenden();
});

$("#g-beenden").addEventListener("click", async () => {
  hoerenBeenden();
  stimmeAus();
  const knopf = $("#g-beenden");
  knopf.disabled = true;
  $("#g-status").textContent = "Das Gespräch wird ausgewertet … (kann eine Minute dauern)";
  try {
    const g = await hole(`/api/gespraeche/${gZustand.id}/feedback`, { method: "POST" });
    $("#g-status").textContent = "";
    $("#g-feedback").innerHTML = feedbackHtml(g.feedback);
    $("#g-feedback").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (fehler) {
    $("#g-status").textContent = fehler.message;
  } finally {
    knopf.disabled = false;
  }
});

function feedbackHtml(f) {
  if (!f) return "";
  const farbe = f.einschaetzung === "ueberzeugend" ? "gut"
    : f.einschaetzung === "ausbaufaehig" ? "warnung" : "";
  const worte = { ueberzeugend: "überzeugend", solide: "solide", ausbaufaehig: "ausbaufähig" };

  let html = `<h2>Auswertung</h2>
    <div class="hinweis ${farbe}">
      <p><strong>Gesamteindruck: ${esc(worte[f.einschaetzung] || f.einschaetzung)}</strong></p>
      <p>${esc(f.gesamteindruck)}</p>
    </div>`;

  if ((f.stark || []).length) {
    html += `<div class="karte"><h3>Das lief gut</h3><ul class="knapp">` +
      f.stark.map((s) => `<li><strong>${esc(s.punkt)}</strong><br>
        <span class="g-zitat">„${esc(s.zitat)}“</span><br>
        <span style="color:var(--text-leise)">${esc(s.warum)}</span></li>`).join("") +
      `</ul></div>`;
  }
  if ((f.schwach || []).length) {
    html += `<div class="karte"><h3>Das würde im echten Gespräch Punkte kosten</h3><ul class="knapp">` +
      f.schwach.map((s) => `<li><strong>${esc(s.punkt)}</strong><br>
        <span class="g-zitat">„${esc(s.zitat)}“</span><br>
        <span style="color:var(--text-leise)">${esc(s.warum)}</span><br>
        <span class="g-besser"><strong>Besser:</strong> ${esc(s.besser)}</span></li>`).join("") +
      `</ul></div>`;
  }
  if ((f.naechstes_mal || []).length) {
    html += `<div class="karte"><h3>Beim nächsten Mal</h3><ul class="knapp">` +
      f.naechstes_mal.map((p) => `<li>${esc(p)}</li>`).join("") + `</ul></div>`;
  }
  html += `<div class="neu-zeile" style="margin-top:16px">
      <button class="knopf leise" id="g-zurueck">← Zur Übersicht der Übungen</button>
    </div>`;
  return html;
}

// Aus dem Feedback zurueck zur Liste - der Knopf entsteht erst mit dem HTML.
document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "g-zurueck") {
    stimmeAus();
    hoerenBeenden();
    $("#g-lauf").hidden = true;
    $("#g-feedback").innerHTML = "";
    $("#g-start").hidden = false;
    ladeGespraeche();
  }
});

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

/* ---- Mehrere Profile ----------------------------------------------------
   Etwa eines für die eigene Branche und eines für einen Quereinstieg, mit
   anders gewichtetem Werdegang. Die Auswahl steht im Kopf und nicht in einem
   Menü: Mit welcher Person gerade gearbeitet wird, darf man nie raten müssen. */

async function zeichneProfilwahl() {
  const daten = await hole("/api/profile");
  const wahl = $("#profil-wahl");
  wahl.innerHTML = daten.profile.map((p) =>
    `<option value="${esc(p.id)}"${p.id === daten.aktiv ? " selected" : ""}>${
      esc(p.name)}${p.vollstaendig ? "" : " (unvollständig)"}</option>`).join("");
  const anzahl = $("#profil-anzahl");
  if (anzahl) {
    anzahl.textContent = daten.profile.length === 1
      ? "Ein Profil angelegt. Über „Neues Profil“ lässt sich ein weiteres anlegen."
      : `${daten.profile.length} Profile angelegt. Umschalten oben rechts.`;
  }
  return daten;
}

async function wechsleProfil(id) {
  await hole(`/api/profile/${id}/waehlen`, { method: "POST" });
  await ladeProfil();
  await ladeUebersicht();
}

$("#profil-wahl").addEventListener("change", (e) => wechsleProfil(e.target.value));

async function neuesProfil(alsKopie) {
  const name = prompt(alsKopie
    ? "Name für die Kopie:"
    : "Name für das neue Profil (z. B. „Vertrieb“ oder „Quereinstieg IT“):", "");
  if (name === null) return;
  if (!name.trim()) { alert("Bitte einen Namen angeben."); return; }
  const nutzlast = { name: name.trim() };
  // Bei der Kopie den Werdegang mitnehmen - ihn ein zweites Mal abzutippen
  // wäre der sicherste Weg, dass es nie jemand tut.
  if (alsKopie) nutzlast.kopie_von = $("#profil-wahl").value;
  await hole("/api/profile", { method: "POST", body: JSON.stringify(nutzlast) });
  await ladeProfil();
  await ladeUebersicht();
}

$("#profil-neu").addEventListener("click", () => neuesProfil(false));
$("#profil-kopieren").addEventListener("click", () => neuesProfil(true));

$("#profil-loeschen").addEventListener("click", async () => {
  const wahl = $("#profil-wahl");
  const name = wahl.options[wahl.selectedIndex]?.text || "dieses Profil";
  if (!confirm(`„${name}“ löschen?\n\nBereits erstellte Bewerbungen bleiben erhalten.`)) return;
  try {
    await hole(`/api/profile/${wahl.value}`, { method: "DELETE" });
    await ladeProfil();
    await ladeUebersicht();
  } catch (fehler) {
    alert(fehler.message);
  }
});

async function ladeProfil() {
  profilDaten = await hole("/api/profil");
  await zeichneProfilwahl();
  const titel = $("#profil-titel");
  if (titel) titel.textContent = profilDaten.name || "Profil";
  const namensfeld = $("#p-name");
  if (namensfeld) namensfeld.value = profilDaten.name || "";
  zeigeFoto(Boolean(profilDaten.hat_foto));
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
    name: ($("#p-name") || {}).value?.trim() || "",
    weiteres: $("#p-weiteres").value.trim(),
    luecken: $("#p-luecken").value.trim(),
  };
  for (const name of Object.keys(LISTEN)) nutzlast[name] = profilDaten[name] || [];

  const status = $("#profil-status");
  status.textContent = "Wird gespeichert …";
  try {
    profilDaten = await hole("/api/profil", { method: "POST", body: JSON.stringify(nutzlast) });
    // Der Name kann sich geändert haben - Kopfauswahl und Überschrift ziehen nach.
    await zeichneProfilwahl();
    const titel = $("#profil-titel");
    if (titel) titel.textContent = profilDaten.name || "Profil";
    status.textContent = "Gespeichert.";
    setTimeout(() => (status.textContent = ""), 2500);
  } catch (fehler) {
    status.textContent = fehler.message;
  }
});

/* ------------------------------------------------------------------ Start */

// Die Profilauswahl im Kopf gehoert zu jeder Ansicht - deshalb hier und nicht
// erst, wenn die Profilseite geoeffnet wird.
zeichneProfilwahl().catch(() => {});
routen();
