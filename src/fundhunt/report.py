"""Self-contained HTML results page for one profile.

One file, no network, no build step: data is embedded as JSON and rendered
by a small inline script, so the page works wherever the user can open a
file — including when the agent runs in a cloud sandbox and hands the
report over as a download.

Review marks (pursue / maybe / dismiss + note) live in the browser until
the user sends them back, by either route `fundhunt decisions import`
understands:
- "Download file": fundhunt-decisions-<profile>-<date>.json, found
  automatically in ~/Downloads by an agent on the same machine;
- "Copy for agent": a FUNDHUNT-DECISIONS text block to paste into the
  chat, for agents that cannot see the user's files.
A first-visit guided tour, an unsent-marks counter and a leave-page warning
make the send-back step hard to forget (docs/log/2026-10-08-decision-return-channels).
"""

from __future__ import annotations

import html
import json
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline
from .profile import Profile
from .settings import reports_dir
from .store import Store

UNJUDGED_SHOWN = 25

STRINGS = {
    "es": {
        "strong": "Para presentarse", "plausible": "Vale la pena mirar",
        "unjudged": "Aún sin revisar (solo ranking léxico)", "reject": "Descartadas por el agente",
        "grant": "Subvención / ayuda", "tender": "Licitación", "deadline": "Plazo",
        "days": "días", "budget": "Presupuesto", "source": "Fuente",
        "constraints": "Condiciones clave", "next": "Siguiente paso", "lexical": "Coincidencias léxicas",
        "pursue": "Me interesa", "maybe": "Quizás", "dismiss": "Descartar", "note": "Nota para el agente…",
        "download": "Descargar archivo", "copy": "Copiar para el agente",
        "pending": "{n} sin enviar", "pending1": "1 sin enviar", "allsent": "Todo enviado",
        "nomarks": "Sin marcas aún",
        "downloaded": "Descargado {file}. Dile a tu agente: «importa mis decisiones». Si no puede ver tu carpeta de Descargas, adjunta el archivo al chat o usa «Copiar para el agente».",
        "copied": "Copiado. Pégalo en el chat con tu agente y dile «importa mis decisiones».",
        "copy_title": "Copia este texto y pégalo en el chat",
        "copy_body": "Tu navegador no permitió copiar automáticamente. Selecciona todo el texto (ya está seleccionado), cópialo y pégalo en la conversación con tu agente.",
        "copy_done": "Ya lo he copiado", "close": "Cerrar",
        "leave": "Tienes marcas sin enviar a tu agente.",
        "all": "Todo", "search": "Buscar…", "hide_dismissed": "Ocultar descartadas",
        "stale": "La convocatoria o el perfil cambiaron desde la revisión",
        "ai": "Análisis del agente", "generated": "Generado", "corpus": "registros en la base",
        "route": {"apply": "Solicitar", "bid": "Licitar", "partner": "Como socio",
                  "advise_clients": "Asesorar a clientes", "monitor": "Vigilar"},
        "lifecycle": {"open": "abierta", "forthcoming": "próxima", "uncertain": "estado incierto"},
        "variants": "variantes similares", "fit": "Encaje", "empty": "Nada en esta sección.",
        "indirect": "indirecta", "unread": "sin leer documentos",
        "help": "Guía", "t_next": "Siguiente", "t_back": "Atrás", "t_done": "Entendido", "t_skip": "Saltar guía",
        "tour": [
            ["Tus oportunidades", "Tu agente ha revisado las convocatorias y licitaciones que mejor encajan con tu perfil. Arriba, las que recomienda; abajo, las que aún no ha revisado y las que descartó."],
            ["Marca cada una", "Pulsa «Me interesa», «Quizás» o «Descartar». Pulsa otra vez para quitar la marca. Las descartadas dejan de aparecerle al agente."],
            ["Añade notas", "¿Por qué sí o por qué no? Una nota corta ayuda al agente a afinar tu perfil en la próxima búsqueda."],
            ["¡No olvides enviarlas!", "Tus marcas solo viven en este navegador hasta que se las devuelvas al agente. Si tu agente trabaja en este ordenador, pulsa «Descargar archivo»: lo encontrará solo en Descargas. Si trabaja en la nube, en el móvil o no puede ver tus archivos, pulsa «Copiar para el agente» y pega el texto en el chat."],
            ["Aquí tienes la guía", "Puedes volver a ver esta guía cuando quieras."],
        ],
    },
    "en": {
        "strong": "Worth pursuing", "plausible": "Worth a look",
        "unjudged": "Not yet reviewed (lexical ranking only)", "reject": "Ruled out by the agent",
        "grant": "Grant / aid", "tender": "Tender", "deadline": "Deadline",
        "days": "days", "budget": "Budget", "source": "Source",
        "constraints": "Key constraints", "next": "Next step", "lexical": "Lexical matches",
        "pursue": "Pursue", "maybe": "Maybe", "dismiss": "Dismiss", "note": "Note for the agent…",
        "download": "Download file", "copy": "Copy for agent",
        "pending": "{n} not sent", "pending1": "1 not sent", "allsent": "All sent",
        "nomarks": "No marks yet",
        "downloaded": "Downloaded {file}. Tell your agent: \"import my decisions\". If it cannot see your Downloads folder, attach the file in the chat or use \"Copy for agent\".",
        "copied": "Copied. Paste it into the chat with your agent and say \"import my decisions\".",
        "copy_title": "Copy this text and paste it into the chat",
        "copy_body": "Your browser did not allow automatic copying. Select all the text (it is already selected), copy it, and paste it into the conversation with your agent.",
        "copy_done": "I've copied it", "close": "Close",
        "leave": "You have marks not yet sent to your agent.",
        "all": "All", "search": "Search…", "hide_dismissed": "Hide dismissed",
        "stale": "The call or the profile changed since this review",
        "ai": "Agent analysis", "generated": "Generated", "corpus": "records in the database",
        "route": {"apply": "Apply", "bid": "Bid", "partner": "As partner",
                  "advise_clients": "Advise clients", "monitor": "Monitor"},
        "lifecycle": {"open": "open", "forthcoming": "forthcoming", "uncertain": "status uncertain"},
        "variants": "similar variants", "fit": "Fit", "empty": "Nothing in this section.",
        "indirect": "indirect", "unread": "documents not read",
        "help": "Guide", "t_next": "Next", "t_back": "Back", "t_done": "Got it", "t_skip": "Skip guide",
        "tour": [
            ["Your opportunities", "Your agent reviewed the calls and tenders that best fit your profile. At the top, the ones it recommends; further down, the ones it has not reviewed yet and the ones it ruled out."],
            ["Mark each one", "Press Pursue, Maybe or Dismiss. Press again to clear the mark. Dismissed calls stop being shown to the agent."],
            ["Add notes", "Why yes, why not? A short note helps the agent tune your profile on the next search."],
            ["Don't forget to send them!", "Your marks only live in this browser until you give them back to the agent. If your agent runs on this computer, press Download file: it will find it in Downloads by itself. If it runs in the cloud, on your phone, or cannot see your files, press Copy for agent and paste the text into the chat."],
            ["The guide lives here", "You can replay this guide any time."],
        ],
    },
}


def build(store: Store, prof: Profile) -> dict:
    phash = prof.hash()
    sections: dict[str, list] = {"strong": [], "plausible": [], "unjudged": [], "reject": []}
    for g in pipeline.grouped(store, prof):
        row, opp = g["row"], g["opp"]
        c = pipeline.card(row, opp)
        c["variants"] = len(g["variants"])
        c["decision"] = None if row["decision"] == "note" else row["decision"]
        c["note"] = row["note"]
        if row["verdict"]:
            c["agent"] = {
                "verdict": row["verdict"], "route": row["route"], "fit": row["fit"],
                "summary": row["summary"], "rationale": row["rationale"],
                "constraint": row["constraint_applied"],
                "key_constraints": json.loads(row["key_constraints"] or "[]"),
                "next_step": row["next_step"], "deep_read": bool(row["deep_read"]),
                "judged_by": row["judged_by"], "judged_at": row["judged_at"],
                "stale": pipeline._verdict_state(row, row["content_hash"], phash) != "current",
            }
            sections[row["verdict"]].append(c)
        elif len(sections["unjudged"]) < UNJUDGED_SHOWN:
            sections["unjudged"].append(c)

    def order(c):
        a = c["agent"]
        return (-(a["fit"] or 0), c["days_left"] if c["days_left"] is not None else 9999)

    for k in ("strong", "plausible"):
        sections[k].sort(key=order)
    total = store.conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    return {
        "profile": prof.name, "language": prof.language,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "corpus": total, "sections": sections,
    }


def render(data: dict) -> str:
    s = STRINGS[data["language"]]
    payload = json.dumps({"data": data, "s": s}, ensure_ascii=False).replace("</", "<\\/")
    title = f"fundhunt · {html.escape(data['profile'])}"
    return TEMPLATE.replace("__TITLE__", title).replace("__LANG__", data["language"]) \
        .replace("__PAYLOAD__", payload)


def write(store: Store, prof: Profile, open_browser: bool = False) -> dict:
    data = build(store, prof)
    out_dir = reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = out_dir / f"{prof.name}-{stamp}.html"
    page = render(data)
    path.write_text(page, encoding="utf-8")
    latest = out_dir / f"{prof.name}-latest.html"
    latest.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(latest.resolve().as_uri())
    counts = {k: len(v) for k, v in data["sections"].items()}
    return {"report": str(path), "latest": str(latest), "counts": counts}


TEMPLATE = r"""<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>__TITLE__</title>
<style>
:root{--bg:#f7f7f4;--card:#fff;--ink:#1c1d1f;--muted:#62666d;--line:#e3e3de;--accent:#1f6f5c;
 --strong:#1f6f5c;--plausible:#a26a00;--reject:#8a8f98;--chip:#eef1ee;--warn:#b54708;--warnbg:#fff4e5;
 --ok:#1f6f5c;--focus:#2563eb;--scrim:rgba(15,17,20,.55)}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--card:#1d1f22;--ink:#e8e8e6;--muted:#9aa0a8;
 --line:#2e3135;--accent:#5fc2a6;--strong:#5fc2a6;--plausible:#e3a93a;--reject:#7c828b;--chip:#262a2e;
 --warn:#f7a14a;--warnbg:#3a2a17;--ok:#5fc2a6;--scrim:rgba(0,0,0,.65)}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
.wrap{max-width:980px;margin:0 auto}
.top{display:flex;gap:8px;align-items:flex-start;justify-content:space-between}
h1{font-size:18px;margin:0 0 2px}.meta{color:var(--muted);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
.bar input[type=search]{flex:1 1 200px;min-width:0;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
#send{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:4px;border-radius:10px}
.badge{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--chip);color:var(--muted);white-space:nowrap}
.badge.pending{background:var(--warnbg);color:var(--warn);font-weight:600}
.badge.sent{color:var(--ok)}
button,select{font:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
@media (prefers-color-scheme:dark){button.primary{color:#0d1a16}}
#help{border-radius:999px;white-space:nowrap}
main{padding:8px 16px 60px}
h2{font-size:15px;margin:28px 0 10px;display:flex;gap:8px;align-items:center}
h2 .n{color:var(--muted);font-weight:400}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.card.strong{border-left-color:var(--strong)}.card.plausible{border-left-color:var(--plausible)}.card.reject{border-left-color:var(--reject);opacity:.85}
.card.dismiss{opacity:.45}
.t{font-weight:600;font-size:15px;margin:0 0 4px;overflow-wrap:anywhere}.t a{color:inherit}
.f{color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{background:var(--chip);border-radius:999px;padding:2px 9px;font-size:12px;white-space:nowrap}
.chip.warn{color:var(--warn)}
.ai{border-top:1px dashed var(--line);margin-top:8px;padding-top:8px}
.ai .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.ai p{margin:4px 0}.ai ul{margin:4px 0 0 18px;padding:0}
details{margin-top:6px}summary{cursor:pointer;color:var(--muted);font-size:13px}
details ul{margin:4px 0 0 18px;padding:0;font-size:13px;color:var(--muted)}
.act{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;align-items:center}
.act button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.act input{flex:1 1 160px;min-width:0;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font-size:13px}
.empty{color:var(--muted);font-size:13px}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
#toast{position:fixed;bottom:16px;left:16px;right:16px;max-width:560px;margin:auto;background:var(--ink);color:var(--bg);padding:10px 14px;border-radius:10px;display:none;z-index:5}
/* guided tour */
#scrim{position:fixed;inset:0;background:var(--scrim);z-index:10;display:none}
#spot{position:fixed;z-index:11;border-radius:10px;box-shadow:0 0 0 4px var(--accent),0 0 0 9999px var(--scrim);pointer-events:none;display:none;transition:all .18s ease}
#bubble{position:fixed;z-index:12;width:min(380px,calc(100vw - 32px));background:var(--card);color:var(--ink);border:1px solid var(--line);
 border-radius:12px;padding:14px 16px;box-shadow:0 12px 32px rgba(0,0,0,.25);display:none}
#bubble h3{margin:0 0 6px;font-size:16px}#bubble p{margin:0 0 12px;font-size:14px}
#bubble .row{display:flex;gap:8px;align-items:center}
#bubble .row .grow{flex:1}
#bubble .steps{font-size:12px;color:var(--muted)}
/* copy fallback */
#copybox{position:fixed;inset:0;z-index:20;background:var(--scrim);display:none;align-items:center;justify-content:center;padding:16px}
#copybox .panel{background:var(--card);border-radius:12px;padding:16px;width:min(640px,100%);max-height:90vh;display:flex;flex-direction:column;gap:10px}
#copybox textarea{width:100%;min-height:200px;font:12px/1.4 ui-monospace,Menlo,monospace;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}
#copybox h3{margin:0;font-size:16px}#copybox p{margin:0;font-size:14px;color:var(--muted)}
</style>
</head>
<body>
<header><div class="wrap">
 <div class="top"><div><h1 id="h"></h1><div class="meta" id="meta"></div></div>
  <button id="help" type="button"></button></div>
 <div class="bar">
  <input type="search" id="q">
  <select id="kind"></select>
  <label class="meta"><input type="checkbox" id="hide" checked> <span id="hidel"></span></label>
  <div id="send"><span class="badge" id="badge"></span>
   <button class="primary" id="download" type="button"></button>
   <button id="copy" type="button"></button></div>
 </div>
</div></header>
<main class="wrap" id="main"></main>
<div id="toast" role="status" aria-live="polite"></div>
<div id="scrim"></div><div id="spot"></div>
<div id="bubble" role="dialog" aria-modal="true" aria-labelledby="bt"><h3 id="bt"></h3><p id="bp"></p>
 <div class="row"><span class="steps grow" id="bs"></span><button id="bskip" type="button"></button>
  <button id="bback" type="button"></button><button class="primary" id="bnext" type="button"></button></div></div>
<div id="copybox" role="dialog" aria-modal="true" aria-labelledby="ct"><div class="panel">
 <h3 id="ct"></h3><p id="cp"></p><textarea id="ctext" readonly></textarea>
 <div class="row" style="display:flex;gap:8px;justify-content:flex-end"><button id="cclose" type="button"></button>
  <button class="primary" id="cdone" type="button"></button></div></div></div>
<script>
const {data:D, s:S} = __PAYLOAD__;
const KEY = "fundhunt-decisions-" + D.profile, SENT = KEY + "-sent", TOUR = "fundhunt-tour-v1";
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
let marks = store.get(KEY, {});
let lastSent = store.get(SENT, "");
// database marks are the baseline; newer browser marks win
for (const sec of Object.values(D.sections)) for (const c of sec)
  if ((c.decision || c.note) && !marks[c.ref]) marks[c.ref] = {decision: c.decision, note: c.note || "", decided_at: ""};
const save = () => { store.set(KEY, marks); badge(); };
const esc = v => String(v ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const $ = id => document.getElementById(id);
const pending = () => Object.values(marks).filter(m => m.decided_at && m.decided_at > lastSent).length;
const changed = () => Object.entries(marks).filter(([, m]) => m.decided_at);

$("h").textContent = "fundhunt · " + D.profile;
$("meta").textContent = `${S.generated} ${D.generated} · ${D.corpus.toLocaleString()} ${S.corpus}`;
$("q").placeholder = S.search; $("hidel").textContent = S.hide_dismissed;
$("download").textContent = S.download; $("copy").textContent = S.copy; $("help").textContent = "? " + S.help;
$("kind").innerHTML = `<option value="">${S.all}</option><option value="grant">${S.grant}</option><option value="tender">${S.tender}</option>`;

function badge() {
  const n = pending(), b = $("badge");
  b.className = "badge" + (n ? " pending" : changed().length ? " sent" : "");
  b.textContent = n ? (n === 1 ? S.pending1 : S.pending.replace("{n}", n)) : changed().length ? "✓ " + S.allsent : S.nomarks;
}

function chips(c) {
  const out = [`<span class="chip">${c.kind === "grant" ? S.grant : S.tender}</span>`,
               `<span class="chip">${S.source}: ${esc(c.source)}</span>`];
  if (c.deadline) out.push(`<span class="chip${c.days_left !== null && c.days_left < 15 ? " warn" : ""}">${S.deadline}: ${esc(c.deadline.slice(0,10))} (${c.days_left} ${S.days})</span>`);
  if (c.lifecycle !== "open") out.push(`<span class="chip warn">${esc(S.lifecycle[c.lifecycle] || c.lifecycle)}</span>`);
  if (c.budget) out.push(`<span class="chip" title="${esc(c.budget_note || "")}">${S.budget}: ${esc(c.budget)}${c.budget_note ? " *" : ""}</span>`);
  if (c.agent && c.agent.route) out.push(`<span class="chip">${esc(S.route[c.agent.route] || c.agent.route)}</span>`);
  if (c.agent && c.agent.fit) out.push(`<span class="chip">${S.fit} ${c.agent.fit}/5</span>`);
  if (c.indirect) out.push(`<span class="chip">${S.indirect}</span>`);
  if (c.agent && !c.agent.deep_read && c.agent.verdict !== "reject") out.push(`<span class="chip">${S.unread}</span>`);
  if (c.variants) out.push(`<span class="chip">+${c.variants} ${S.variants}</span>`);
  return out.join("");
}

function agent(a) {
  if (!a) return "";
  const kc = a.key_constraints && a.key_constraints.length ? `<div class="lbl">${S.constraints}</div><ul>${a.key_constraints.map(k => `<li>${esc(k)}</li>`).join("")}</ul>` : "";
  return `<div class="ai"><div class="lbl">${S.ai}${a.judged_by ? " · " + esc(a.judged_by) : ""}</div>
    ${a.stale ? `<p class="chip warn">${S.stale}</p>` : ""}
    <p><strong>${esc(a.summary)}</strong></p>
    <p>${esc(a.rationale)}</p>
    ${a.constraint ? `<p><em>${esc(a.constraint)}</em></p>` : ""}
    ${kc}
    ${a.next_step ? `<p><span class="lbl">${S.next}:</span> ${esc(a.next_step)}</p>` : ""}</div>`;
}

function card(c, sec) {
  const m = marks[c.ref] || {};
  const btn = d => `<button type="button" data-ref="${esc(c.ref)}" data-d="${d}" aria-pressed="${m.decision === d}">${S[d]}</button>`;
  return `<article class="card ${sec} ${m.decision === "dismiss" ? "dismiss" : ""}" data-ref="${esc(c.ref)}">
    <p class="t">${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>` : esc(c.title)}</p>
    <div class="f">${esc(c.funder || "")}</div>
    <div class="chips">${chips(c)}</div>
    ${agent(c.agent)}
    ${!c.agent && c.summary ? `<p class="f">${esc(c.summary.slice(0, 400))}${c.summary.length > 400 ? "…" : ""}</p>` : ""}
    <details><summary>${S.lexical} (${c.lexical.tier} · ${c.lexical.score})</summary><ul>${c.lexical.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul></details>
    <div class="act">${btn("pursue")}${btn("maybe")}${btn("dismiss")}
      <input data-note="${esc(c.ref)}" aria-label="${esc(S.note)}" placeholder="${esc(S.note)}" value="${esc(m.note || "")}"></div>
  </article>`;
}

function draw() {
  const q = $("q").value.trim().toLowerCase(), kind = $("kind").value, hide = $("hide").checked;
  let html = "";
  for (const sec of ["strong", "plausible", "unjudged", "reject"]) {
    const items = D.sections[sec].filter(c => (!kind || c.kind === kind)
      && (!q || (c.title + " " + (c.funder || "") + " " + (c.summary || "")).toLowerCase().includes(q))
      && !(hide && (marks[c.ref] || {}).decision === "dismiss"));
    const body = items.length ? items.map(c => card(c, sec)).join("") : `<p class="empty">${S.empty}</p>`;
    html += sec === "reject"
      ? `<details><summary><h2 style="display:inline">${S[sec]} <span class="n">${items.length}</span></h2></summary>${body}</details>`
      : `<h2>${S[sec]} <span class="n">${items.length}</span></h2>${body}`;
  }
  $("main").innerHTML = html;
  badge();
}

document.addEventListener("click", e => {
  const b = e.target.closest("button[data-d]");
  if (!b) return;
  const ref = b.dataset.ref, d = b.dataset.d, cur = marks[ref] || {};
  marks[ref] = {decision: cur.decision === d ? null : d, note: cur.note || "", decided_at: new Date().toISOString()};
  save(); draw();
});
document.addEventListener("input", e => {
  const ref = e.target.dataset && e.target.dataset.note;
  if (!ref) return;
  const cur = marks[ref] || {decision: null};
  marks[ref] = {...cur, note: e.target.value, decided_at: new Date().toISOString()};
  save();
});
["q", "kind", "hide"].forEach(id => $(id).addEventListener("input", draw));

// ---- sending marks back to the agent ---------------------------------
function payload() {
  return {profile: D.profile, exported_at: new Date().toISOString(),
          decisions: changed().map(([ref, m]) => ({ref, decision: m.decision, note: m.note || null, decided_at: m.decided_at}))};
}
function markSent() { lastSent = new Date().toISOString(); store.set(SENT, lastSent); badge(); }
function toast(msg, ms = 9000) {
  const t = $("toast"); t.textContent = msg; t.style.display = "block";
  clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = "none", ms);
}
$("download").addEventListener("click", () => {
  const file = `fundhunt-decisions-${D.profile}-${new Date().toISOString().slice(0,10)}.json`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(payload(), null, 2)], {type: "application/json"}));
  a.download = file; document.body.appendChild(a); a.click(); a.remove();
  markSent(); toast(S.downloaded.replace("{file}", file));
});
function pasteText() {
  const p = payload();
  return `FUNDHUNT-DECISIONS ${D.profile} · ${p.decisions.length} · ${p.exported_at.slice(0,10)}\n` +
         `(agent: pipe this block to \`uv run fundhunt decisions import --profile ${D.profile} --stdin\`)\n` +
         JSON.stringify(p);
}
$("copy").addEventListener("click", async () => {
  const text = pasteText();
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error("no clipboard");
    await navigator.clipboard.writeText(text);
    markSent(); toast(S.copied);
  } catch (e) {
    $("ct").textContent = S.copy_title; $("cp").textContent = S.copy_body;
    $("cdone").textContent = S.copy_done; $("cclose").textContent = S.close;
    $("ctext").value = text; $("copybox").style.display = "flex";
    $("ctext").focus(); $("ctext").select();
  }
});
$("cdone").addEventListener("click", () => { $("copybox").style.display = "none"; markSent(); toast(S.copied); });
$("cclose").addEventListener("click", () => { $("copybox").style.display = "none"; });
window.addEventListener("beforeunload", e => { if (pending()) { e.preventDefault(); e.returnValue = S.leave; return S.leave; } });

// ---- guided tour ------------------------------------------------------
const STEPS = [
  {target: null},
  {target: "#main .act"},
  {target: "#main .act input"},
  {target: "#send"},
  {target: "#help"},
];
let step = -1;
function steps() { return STEPS.map((s, i) => ({...s, text: S.tour[i]})).filter(s => !s.target || document.querySelector(s.target)); }
function showStep(i) {
  const all = steps(); step = i;
  if (i < 0 || i >= all.length) return endTour();
  const s = all[i], t = s.target && document.querySelector(s.target);
  $("bt").textContent = s.text[0]; $("bp").textContent = s.text[1];
  $("bs").textContent = `${i + 1} / ${all.length}`;
  $("bback").textContent = S.t_back; $("bback").style.visibility = i ? "visible" : "hidden";
  $("bnext").textContent = i === all.length - 1 ? S.t_done : S.t_next;
  $("bskip").textContent = S.t_skip; $("bskip").style.display = i === all.length - 1 ? "none" : "";
  const bub = $("bubble"), spot = $("spot");
  bub.style.display = "block";
  if (!t) {
    spot.style.display = "none"; $("scrim").style.display = "block";
    bub.style.left = Math.max(16, (innerWidth - bub.offsetWidth) / 2) + "px";
    bub.style.top = Math.max(16, (innerHeight - bub.offsetHeight) / 2) + "px";
  } else {
    $("scrim").style.display = "none";
    t.scrollIntoView({block: "center", behavior: "instant"});
    const r = t.getBoundingClientRect(), pad = 6;
    Object.assign(spot.style, {display: "block", left: r.left - pad + "px", top: r.top - pad + "px",
                               width: r.width + 2 * pad + "px", height: r.height + 2 * pad + "px"});
    const bw = bub.offsetWidth, bh = bub.offsetHeight;
    const below = r.bottom + pad + 12, above = r.top - pad - 12 - bh;
    bub.style.top = (below + bh < innerHeight - 8 || above < 8 ? Math.min(below, innerHeight - bh - 8) : above) + "px";
    bub.style.left = Math.min(Math.max(16, r.left), innerWidth - bw - 16) + "px";
  }
  $("bnext").focus();
}
function endTour() {
  ["bubble", "spot", "scrim"].forEach(id => $(id).style.display = "none");
  step = -1; store.set(TOUR, true);
}
$("bnext").addEventListener("click", () => showStep(step + 1));
$("bback").addEventListener("click", () => showStep(step - 1));
$("bskip").addEventListener("click", endTour);
$("help").addEventListener("click", () => showStep(0));
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { if (step >= 0) endTour(); $("copybox").style.display = "none"; }
  if (step >= 0 && e.key === "ArrowRight") showStep(step + 1);
  if (step >= 0 && e.key === "ArrowLeft") showStep(step - 1);
});
addEventListener("resize", () => { if (step >= 0) showStep(step); });

draw();
if (!store.get(TOUR, false)) setTimeout(() => showStep(0), 300);
</script>
</body>
</html>
"""
