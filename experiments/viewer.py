"""A local web viewer for every experiment's saved runs. One tool, all experiments.

    python -m experiments.viewer            # then open http://127.0.0.1:8765

This is deliberately schema-agnostic: it does NOT know what a cheap-talk game or
an election is, and nothing needs registering when you add an experiment. It
discovers `experiments/*/results/*.json` on every request and renders whatever
it finds, so a new experiment shows up the moment it writes its first result.

That works because every experiment in this repo shares one idiom: an LLM turn
emits `private_reasoning` alongside something spoken. The renderer keys on that
shape rather than on any particular schema, and falls back through a short
ladder of structural heuristics:

  * a dict carrying a reasoning field        -> an utterance card (said + thought)
  * a list of uniform flat dicts             -> a table (ledgers, telemetry)
  * a list of dicts                          -> a sequence of nested nodes
  * a dict of scalars                        -> a key/value grid
  * anything else                            -> collapsible nested sections

The JSON files remain the durable record; this only makes them readable. (They
are gitignored by default, so runs do not accumulate in version control; an
experiment may whitelist a reference run.)
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

EXPERIMENTS_ROOT = Path(__file__).resolve().parent

# Some experiments (horizon) write a run as a DIRECTORY containing the trace
# alongside infrastructure telemetry -- 28 of its 32 JSONs are per-month
# database/service counters, which would bury the four real traces. These are
# skipped by default and restored with --all.
NOISE_SUFFIXES = ("_metrics.json",)
NOISE_PREFIXES = ("client_metrics",)
SHOW_ALL = False


def is_noise(path: Path) -> bool:
    return path.name.endswith(NOISE_SUFFIXES) or path.name.startswith(NOISE_PREFIXES)


def discover() -> list[dict]:
    """Every result file under experiments/*/results/, newest first.

    Re-scanned on each request rather than cached, so a run that finishes while
    the viewer is open appears on refresh.
    """
    runs = []
    for path in EXPERIMENTS_ROOT.glob("*/results/**/*.json"):
        if not path.is_file() or (not SHOW_ALL and is_noise(path)):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(EXPERIMENTS_ROOT)
        # A trace nested inside a per-run directory needs that directory in its
        # label, or every horizon run is just called "run_result".
        depth = rel.parts[2:-1]
        name = f"{'/'.join(depth)}/{path.stem}" if depth else path.stem
        runs.append(
            {
                "experiment": rel.parts[0],
                "name": name,
                "path": str(rel),
                "mtime": stat.st_mtime,
                "when": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "kb": round(stat.st_size / 1024, 1),
            }
        )
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def resolve_safe(rel: str) -> Path | None:
    """Resolve a client-supplied path, refusing anything outside the results
    tree. The viewer binds to localhost, but path traversal is cheap to close."""
    try:
        target = (EXPERIMENTS_ROOT / rel).resolve()
        target.relative_to(EXPERIMENTS_ROOT)
    except (ValueError, OSError):
        return None
    if target.suffix != ".json" or "results" not in target.parts or not target.is_file():
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the console clean for the runs
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/api/runs":
            self._send(json.dumps(discover()).encode(), "application/json")
        elif parsed.path == "/api/run":
            rel = parse_qs(parsed.query).get("path", [""])[0]
            target = resolve_safe(rel)
            if target is None:
                self._send(b'{"error":"not found"}', "application/json", 404)
                return
            self._send(target.read_bytes(), "application/json")
        else:
            self._send(b"not found", "text/plain", 404)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Experiment traces</title>
<style>
:root{--bg:#fbfaf8;--fg:#1c1b19;--muted:#6b6763;--line:#e3dfd9;--card:#fff;
--thought:#7a5c2e;--thought-bg:#fdf7ec;--accent:#8a5a2b;--ok:#2f6b46;--bad:#9c3328;--side:#f4f1ec;}
@media(prefers-color-scheme:dark){:root{--bg:#16151a;--fg:#e9e6e1;--muted:#9a948d;--line:#2e2c33;
--card:#1d1c22;--thought:#d5b483;--thought-bg:#241f18;--accent:#d5a56b;--ok:#7fc79b;--bad:#e8897c;--side:#131217;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 ui-serif,Georgia,serif;
display:grid;grid-template-columns:19rem 1fr;height:100vh;overflow:hidden}
aside{background:var(--side);border-right:1px solid var(--line);overflow-y:auto;padding:1rem}
main{overflow-y:auto;padding:1.6rem 2rem 6rem}
h1{font-size:.8rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
margin:0 0 .8rem;font-family:ui-sans-serif,system-ui,sans-serif}
.exp{font:600 .72rem/1 ui-sans-serif,system-ui,sans-serif;text-transform:uppercase;
letter-spacing:.07em;color:var(--accent);margin:1.2rem 0 .4rem}
.run{display:block;width:100%;text-align:left;border:0;background:none;color:var(--fg);
font:inherit;font-size:.83rem;padding:.4rem .5rem;border-radius:.35rem;cursor:pointer;line-height:1.35}
.run:hover{background:var(--card)}
.run.active{background:var(--card);box-shadow:inset 2px 0 0 var(--accent)}
.run small{display:block;color:var(--muted);font-size:.72rem}
input[type=search]{width:100%;padding:.45rem .6rem;border:1px solid var(--line);border-radius:.35rem;
background:var(--card);color:var(--fg);font:inherit;font-size:.83rem;margin-bottom:.4rem}
.toolbar{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1.4rem;position:sticky;top:0;
background:var(--bg);padding:.2rem 0 .6rem;z-index:5}
button{font:inherit;font-size:.8rem;padding:.35rem .8rem;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent);color:var(--accent)}
h2.title{font-size:1.35rem;margin:0 0 .2rem}
.sub{color:var(--muted);font-size:.85rem;margin:0 0 1.2rem;font-family:ui-monospace,Menlo,monospace}
.grid{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--line);border-radius:.5rem;
overflow:hidden;background:var(--card);margin:0 0 1.2rem}
.cell{flex:1 1 9rem;padding:.5rem .75rem;border-right:1px solid var(--line);border-bottom:1px solid var(--line);min-width:0}
.cell b{display:block;font:600 .66rem/1.4 ui-sans-serif,system-ui,sans-serif;text-transform:uppercase;
letter-spacing:.05em;color:var(--muted)}
.cell span{font-family:ui-monospace,Menlo,monospace;font-size:.85rem;word-break:break-word}
.cell.wide{flex-basis:100%;font-family:inherit}
.cell.wide span{font-family:inherit;font-size:.9rem}
details{border:1px solid var(--line);border-radius:.45rem;margin:0 0 .5rem;background:var(--card)}
details>summary{cursor:pointer;padding:.5rem .8rem;font-size:.88rem;font-weight:600}
details>summary::marker{color:var(--accent)}
.inner{padding:.2rem .8rem .8rem}
.turn{margin:0 0 1rem}
.who{font:600 .67rem/1 ui-sans-serif,system-ui,sans-serif;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);margin-bottom:.3rem}
blockquote{margin:0;padding-left:.85rem;border-left:2px solid var(--line);white-space:pre-wrap}
.thought{margin:.4rem 0 0;padding:.5rem .75rem;background:var(--thought-bg);border-radius:.35rem;
color:var(--thought);font-size:.87rem;white-space:pre-wrap}
.tag{font:600 .63rem/1 ui-sans-serif,system-ui,sans-serif;text-transform:uppercase;
letter-spacing:.07em;margin-right:.45rem;opacity:.75}
.chips{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.4rem}
.chip{font:.72rem/1 ui-monospace,Menlo,monospace;padding:.28rem .5rem;border-radius:.3rem;
border:1px solid var(--line);color:var(--muted)}
.chip b{color:var(--fg);font-weight:600}
.tblwrap{overflow-x:auto;margin:0 0 .8rem}
table{border-collapse:collapse;font:.8rem/1.5 ui-monospace,Menlo,monospace;width:100%}
th{text-align:left;color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;
border-bottom:1px solid var(--line);padding:.35rem .55rem;white-space:nowrap}
td{padding:.3rem .55rem;border-bottom:1px solid var(--line);white-space:nowrap}
.sec{margin:0 0 1.4rem}
.sec>h3{font-size:.74rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin:1.6rem 0 .6rem;font-family:ui-sans-serif,system-ui,sans-serif}
body.hide-thoughts .thought{display:none}
.empty{color:var(--muted);margin-top:4rem;text-align:center}
mark{background:var(--accent);color:var(--bg);border-radius:2px}
.hidden{display:none}
</style></head>
<body>
<aside>
  <h1>Traces</h1>
  <input type="search" id="filter" placeholder="filter runs…">
  <div id="list"></div>
</aside>
<main>
  <div class="toolbar">
    <button id="thoughts">hide private reasoning</button>
    <button id="expand">expand all</button>
    <button id="reload">refresh</button>
    <input type="search" id="find" placeholder="search in trace…" style="width:14rem;margin:0">
  </div>
  <div id="view"><p class="empty">Pick a run on the left.</p></div>
</main>
<script>
const REASONING=['private_reasoning','reasoning','thinking','rationale','private_thoughts','thoughts'];
const SAID=['message','text','speech','statement','content','said','utterance','assessment','summary'];
const SPEAKER=['speaker','candidate','agent','role','from','author','who','lobby','name'];
const OUTCOME=['choice','action','target','vote','decision','outcome','blames','demands','verdict'];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isScalar=v=>v===null||['string','number','boolean'].includes(typeof v);
const isPlain=v=>v&&typeof v==='object'&&!Array.isArray(v);
const firstKey=(o,keys)=>keys.find(k=>k in o&&o[k]!==null&&o[k]!=='');
const title=k=>k.replace(/_/g,' ');

/* A node is an utterance if it carries hidden reasoning. That single test is
   what makes this viewer work across experiments it has never seen. */
const isUtterance=v=>isPlain(v)&&REASONING.some(k=>k in v);

/* A list of flat, uniform dicts (a ledger, telemetry) reads better as a table.
   But dialogue ALSO has that shape — a list of messages is uniform and flat —
   and collapsing a conversation into a spreadsheet destroys the one thing these
   traces exist to show. Utterances therefore always win over the table form. */
function isTable(a){
  if(!Array.isArray(a)||a.length<2)return false;
  if(a.some(isUtterance))return false;
  if(!a.every(r=>isPlain(r)&&Object.values(r).every(isScalar)))return false;
  const k=JSON.stringify(Object.keys(a[0]));
  return a.every(r=>JSON.stringify(Object.keys(r))===k);
}

function renderUtterance(v){
  const sp=firstKey(v,SPEAKER), sk=firstKey(v,SAID), rk=firstKey(v,REASONING);
  const used=new Set([sp,sk,rk].filter(Boolean));
  let said=sk?esc(v[sk]):'';
  if(!said){ // no spoken field: lead with the decision it made instead
    const ok=firstKey(v,OUTCOME);
    if(ok){said=esc(v[ok]);used.add(ok);}
  }
  const chips=Object.entries(v).filter(([k,x])=>!used.has(k)&&isScalar(x))
    .map(([k,x])=>`<span class="chip"><b>${esc(title(k))}</b> ${esc(x)}</span>`).join('');
  const nested=Object.entries(v).filter(([k,x])=>!used.has(k)&&!isScalar(x))
    .map(([k,x])=>renderNode(x,k)).join('');
  return `<div class="turn">
    ${sp?`<div class="who">${esc(v[sp])}</div>`:''}
    ${said?`<blockquote>${said}</blockquote>`:''}
    ${rk?`<div class="thought"><span class="tag">privately</span>${esc(v[rk])}</div>`:''}
    ${chips?`<div class="chips">${chips}</div>`:''}${nested}</div>`;
}

function renderTable(a){
  const cols=Object.keys(a[0]);
  return `<div class="tblwrap"><table><thead><tr>${cols.map(c=>`<th>${esc(title(c))}</th>`).join('')}</tr></thead>
  <tbody>${a.map(r=>`<tr>${cols.map(c=>`<td>${esc(r[c]===null?'':r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function renderGrid(entries){
  return `<div class="grid">${entries.map(([k,v])=>{
    const long=typeof v==='string'&&v.length>90;
    return `<div class="cell${long?' wide':''}"><b>${esc(title(k))}</b><span>${esc(v)}</span></div>`;
  }).join('')}</div>`;
}

function renderNode(v,key){
  if(isScalar(v))return renderGrid([[key,v]]);
  if(Array.isArray(v)){
    if(!v.length)return '';
    if(isTable(v))return `<div class="sec"><h3>${esc(title(key))} (${v.length})</h3>${renderTable(v)}</div>`;
    if(v.every(isScalar))return renderGrid([[key,v.join(', ')]]);
    return `<div class="sec"><h3>${esc(title(key))} (${v.length})</h3>${v.map((x,i)=>renderNode(x,`${key} ${i+1}`)).join('')}</div>`;
  }
  if(isUtterance(v))return renderUtterance(v);
  const scalars=Object.entries(v).filter(([,x])=>isScalar(x));
  const rest=Object.entries(v).filter(([,x])=>!isScalar(x));
  const head=scalars.length?renderGrid(scalars):'';
  if(!rest.length)return `<details open><summary>${esc(title(key))}</summary><div class="inner">${head}</div></details>`;
  const body=head+rest.map(([k,x])=>renderNode(x,k)).join('');
  return `<details open><summary>${esc(title(key))}</summary><div class="inner">${body}</div></details>`;
}

function renderRun(d,meta){
  const scalars=Object.entries(d).filter(([,v])=>isScalar(v));
  const rest=Object.entries(d).filter(([,v])=>!isScalar(v));
  return `<h2 class="title">${esc(meta.name)}</h2>
  <p class="sub">${esc(meta.experiment)} · ${esc(meta.when)} · ${meta.kb} KB</p>
  ${scalars.length?renderGrid(scalars):''}
  ${rest.map(([k,v])=>renderNode(v,k)).join('')}`;
}

let runs=[],active=null;
const $=id=>document.getElementById(id);

/* Poll for new runs so a viewer left open picks up finished experiments on its
   own. The sidebar is only redrawn when the file list actually changed, so a
   trace you are reading is never disturbed by the poll. */
let sig='';
async function loadList(){
  let r;
  try{ r=await (await fetch('/api/runs')).json(); }
  catch(e){ return; }   // viewer stopped or restarting; try again next tick
  const s=JSON.stringify(r.map(x=>x.path+x.mtime));
  if(s===sig)return;
  sig=s;runs=r;drawList();
}
setInterval(loadList,5000);
function drawList(){
  const q=$('filter').value.toLowerCase();
  const shown=runs.filter(r=>!q||`${r.experiment} ${r.name}`.toLowerCase().includes(q));
  const groups={};
  shown.forEach(r=>(groups[r.experiment]=groups[r.experiment]||[]).push(r));
  $('list').innerHTML=Object.entries(groups).map(([exp,rs])=>
    `<div class="exp">${esc(exp)} (${rs.length})</div>`+rs.map(r=>
      `<button class="run${active===r.path?' active':''}" data-path="${esc(r.path)}">${esc(r.name)}
        <small>${esc(r.when)}</small></button>`).join('')).join('')
    ||'<p class="empty">No runs found.</p>';
  document.querySelectorAll('.run').forEach(b=>b.onclick=()=>open(b.dataset.path));
}
async function open(path){
  active=path;drawList();
  const meta=runs.find(r=>r.path===path);
  const d=await (await fetch('/api/run?path='+encodeURIComponent(path))).json();
  $('view').innerHTML=renderRun(d,meta);
  $('find').value='';applyFind();
}
function applyFind(){
  const q=$('find').value.toLowerCase();
  document.querySelectorAll('#view .turn').forEach(t=>{
    t.classList.toggle('hidden',!!q&&!t.textContent.toLowerCase().includes(q));
  });
}
$('filter').oninput=drawList;
$('find').oninput=applyFind;
$('reload').onclick=()=>{loadList();if(active)open(active);};
$('thoughts').onclick=e=>{document.body.classList.toggle('hide-thoughts');
  e.target.textContent=document.body.classList.contains('hide-thoughts')?'show private reasoning':'hide private reasoning';};
$('expand').onclick=e=>{const ds=document.querySelectorAll('#view details');
  const any=[...ds].some(d=>!d.open);ds.forEach(d=>d.open=any);
  e.target.textContent=any?'collapse all':'expand all';};
loadList();
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Web viewer for experiment traces")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="Don't launch a browser.")
    ap.add_argument(
        "--all", action="store_true",
        help="Include infrastructure telemetry files that are hidden by default.",
    )
    args = ap.parse_args()

    global SHOW_ALL
    SHOW_ALL = args.all

    runs = discover()
    experiments = sorted({r["experiment"] for r in runs})
    url = f"http://{args.host}:{args.port}"

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        # Overwhelmingly this is a viewer already running from a previous
        # session -- which is harmless and already serving the same files.
        raise SystemExit(
            f"Could not bind {args.host}:{args.port} ({exc.strerror}).\n"
            f"A viewer may already be running — try opening {url} first.\n"
            f"Otherwise pick another port: python -m experiments.viewer --port 8766"
        ) from exc

    print(f"Serving {len(runs)} run(s) from {len(experiments)} experiment(s): {', '.join(experiments)}")
    print(f"  {url}   (ctrl-c to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
