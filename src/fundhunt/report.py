"""Self-contained HTML results page for one profile.

One file, no network, no build step: data is embedded as JSON and rendered
by a small inline script. Review marks (pursue / maybe / dismiss + note)
are kept in the browser's localStorage and exported as a JSON file that
`fundhunt decisions import` reads back into the database.
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
        "title": "Oportunidades", "strong": "Para presentarse", "plausible": "Vale la pena mirar",
        "unjudged": "Aún sin revisar (solo ranking léxico)", "reject": "Descartadas por el agente",
        "grant": "Subvención / ayuda", "tender": "Licitación", "deadline": "Plazo",
        "days": "días", "budget": "Presupuesto", "source": "Fuente", "why": "Por qué",
        "constraints": "Condiciones clave", "next": "Siguiente paso", "lexical": "Coincidencias léxicas",
        "pursue": "Me interesa", "maybe": "Quizás", "dismiss": "Descartar", "note": "Nota…",
        "export": "Exportar decisiones", "exported": "Guardado. Dile a tu agente: «importa mis decisiones».",
        "all": "Todo", "search": "Buscar…", "hide_dismissed": "Ocultar descartadas",
        "stale": "La convocatoria o el perfil cambiaron desde la revisión",
        "ai": "Análisis del agente", "generated": "Generado", "corpus": "registros en la base",
        "route": {"apply": "Solicitar", "bid": "Licitar", "partner": "Como socio",
                  "advise_clients": "Asesorar a clientes", "monitor": "Vigilar"},
        "lifecycle": {"open": "abierta", "forthcoming": "próxima", "uncertain": "estado incierto"},
        "variants": "variantes similares", "fit": "Encaje", "empty": "Nada en esta sección.",
        "indirect": "indirecta", "unread": "sin leer documentos",
    },
    "en": {
        "title": "Opportunities", "strong": "Worth pursuing", "plausible": "Worth a look",
        "unjudged": "Not yet reviewed (lexical ranking only)", "reject": "Ruled out by the agent",
        "grant": "Grant / aid", "tender": "Tender", "deadline": "Deadline",
        "days": "days", "budget": "Budget", "source": "Source", "why": "Why",
        "constraints": "Key constraints", "next": "Next step", "lexical": "Lexical matches",
        "pursue": "Pursue", "maybe": "Maybe", "dismiss": "Dismiss", "note": "Note…",
        "export": "Export decisions", "exported": "Saved. Tell your agent: \"import my decisions\".",
        "all": "All", "search": "Search…", "hide_dismissed": "Hide dismissed",
        "stale": "The call or the profile changed since this review",
        "ai": "Agent analysis", "generated": "Generated", "corpus": "records in the database",
        "route": {"apply": "Apply", "bid": "Bid", "partner": "As partner",
                  "advise_clients": "Advise clients", "monitor": "Monitor"},
        "lifecycle": {"open": "open", "forthcoming": "forthcoming", "uncertain": "status uncertain"},
        "variants": "similar variants", "fit": "Fit", "empty": "Nothing in this section.",
        "indirect": "indirect", "unread": "documents not read",
    },
}


def build(store: Store, prof: Profile) -> dict:
    phash = prof.hash()
    sections: dict[str, list] = {"strong": [], "plausible": [], "unjudged": [], "reject": []}
    for g in pipeline.grouped(store, prof):
        row, opp = g["row"], g["opp"]
        c = pipeline.card(row, opp)
        c["variants"] = len(g["variants"])
        c["decision"] = row["decision"]
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
<title>__TITLE__</title>
<style>
:root{--bg:#f7f7f4;--card:#fff;--ink:#1c1d1f;--muted:#62666d;--line:#e3e3de;--accent:#1f6f5c;
 --strong:#1f6f5c;--plausible:#a26a00;--reject:#8a8f98;--chip:#eef1ee;--warn:#b54708;--focus:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--card:#1d1f22;--ink:#e8e8e6;--muted:#9aa0a8;
 --line:#2e3135;--accent:#5fc2a6;--strong:#5fc2a6;--plausible:#e3a93a;--reject:#7c828b;--chip:#262a2e;--warn:#f79009}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:18px;margin:0 0 2px}.meta{color:var(--muted);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
.bar input[type=search]{flex:1 1 200px;min-width:0;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
button,select{font:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
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
#toast{position:fixed;bottom:16px;left:16px;right:16px;max-width:520px;margin:auto;background:var(--ink);color:var(--bg);padding:10px 14px;border-radius:10px;display:none}
</style>
</head>
<body>
<header><div class="wrap">
 <h1 id="h"></h1><div class="meta" id="meta"></div>
 <div class="bar">
  <input type="search" id="q">
  <select id="kind"></select>
  <label class="meta"><input type="checkbox" id="hide" checked> <span id="hidel"></span></label>
  <button class="primary" id="export"></button>
 </div>
</div></header>
<main class="wrap" id="main"></main>
<div id="toast" role="status"></div>
<script>
const {data:D, s:S} = __PAYLOAD__;
const KEY = "fundhunt-decisions-" + D.profile;
let marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
// database marks are the baseline; newer browser marks win
for (const sec of Object.values(D.sections)) for (const c of sec)
  if (c.decision && !marks[c.ref]) marks[c.ref] = {decision: c.decision, note: c.note || "", decided_at: ""};
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} };
const esc = v => String(v ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const $ = id => document.getElementById(id);

$("h").textContent = "fundhunt · " + D.profile;
$("meta").textContent = `${S.generated} ${D.generated} · ${D.corpus.toLocaleString()} ${S.corpus}`;
$("q").placeholder = S.search; $("hidel").textContent = S.hide_dismissed; $("export").textContent = S.export;
$("kind").innerHTML = `<option value="">${S.all}</option><option value="grant">${S.grant}</option><option value="tender">${S.tender}</option>`;

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
  const btn = d => `<button data-ref="${esc(c.ref)}" data-d="${d}" aria-pressed="${m.decision === d}">${S[d]}</button>`;
  return `<article class="card ${sec} ${m.decision === "dismiss" ? "dismiss" : ""}" data-kind="${c.kind}" data-ref="${esc(c.ref)}"
     data-text="${esc((c.title + " " + (c.funder || "") + " " + (c.summary || "")).toLowerCase())}">
    <p class="t">${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>` : esc(c.title)}</p>
    <div class="f">${esc(c.funder || "")}</div>
    <div class="chips">${chips(c)}</div>
    ${agent(c.agent)}
    ${!c.agent && c.summary ? `<p class="f">${esc(c.summary.slice(0, 400))}${c.summary.length > 400 ? "…" : ""}</p>` : ""}
    <details><summary>${S.lexical} (${c.lexical.tier} · ${c.lexical.score})</summary><ul>${c.lexical.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul></details>
    <div class="act">${btn("pursue")}${btn("maybe")}${btn("dismiss")}
      <input data-note="${esc(c.ref)}" placeholder="${S.note}" value="${esc(m.note || "")}"></div>
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
}

document.addEventListener("click", e => {
  const b = e.target.closest("button[data-d]");
  if (!b) return;
  const ref = b.dataset.ref, d = b.dataset.d, cur = marks[ref] || {};
  marks[ref] = {decision: cur.decision === d ? null : d, note: cur.note || "", decided_at: new Date().toISOString()};
  save(); draw();
});
document.addEventListener("change", e => {
  const ref = e.target.dataset && e.target.dataset.note;
  if (!ref) return;
  const cur = marks[ref] || {decision: null};
  marks[ref] = {...cur, note: e.target.value, decided_at: new Date().toISOString()};
  save();
});
["q", "kind", "hide"].forEach(id => $(id).addEventListener("input", draw));
$("export").addEventListener("click", () => {
  const decisions = Object.entries(marks).filter(([, m]) => m.decided_at)
    .map(([ref, m]) => ({ref, decision: m.decision, note: m.note || null, decided_at: m.decided_at}));
  const blob = new Blob([JSON.stringify({profile: D.profile, exported_at: new Date().toISOString(), decisions}, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `fundhunt-decisions-${D.profile}-${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  const t = $("toast"); t.textContent = S.exported; t.style.display = "block";
  setTimeout(() => t.style.display = "none", 6000);
});
draw();
</script>
</body>
</html>
"""
