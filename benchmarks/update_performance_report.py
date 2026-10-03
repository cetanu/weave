"""Append one ASV result and render a self-contained history report."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "performance-data.json"
HTML_PATH = ROOT / "benchmarks" / "performance.html"
ENVIRONMENT = "virtualenv-py3.14"
BENCHMARKS = {
    "flat": "flat",
    "wide mixed": "wide_mixed_late",
    "medium mixed": "medium_mixed_late",
    "subtree copy": "copy_subtree",
    "mixed subtree copy": "copy_subtree_mixed_late",
    "list replace": "list_replace",
    "list concatenate": "list_concat",
}


def result_value(result):
    value = result[0] if result else None
    while isinstance(value, list) and value:
        value = value[0]
    return value if isinstance(value, (int, float)) else None


def load_measurements(commit):
    files = ROOT / ".asv" / "results"
    for path in sorted(files.rglob("*.json")):
        result_file = json.loads(path.read_text())
        if "commit_hash" not in result_file:
            continue
        if result_file["commit_hash"] != commit or result_file["env_name"] != ENVIRONMENT:
            continue
        values = {}
        for label, workload in BENCHMARKS.items():
            results = result_file["results"]
            weave = result_value(results.get(f"bench_merge.MergeBenchmarks.time_{workload}_weave"))
            python = result_value(
                results.get(f"bench_merge.MergeBenchmarks.time_{workload}_python")
            )
            if weave and python:
                values[label] = {
                    "weave_seconds": weave,
                    "python_seconds": python,
                    "speedup": python / weave,
                }
        if values:
            return result_file["date"], values
    raise SystemExit(f"No CPython 3.14 ASV results found for {commit}")


def render(data):
    serialized = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = r"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weaved performance history</title>
<style>
body{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#202124}
h1{font-size:1.7rem}p{color:#5f6368}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1rem}
article{border:1px solid #dadce0;border-radius:8px;padding:1rem}h2{font-size:1rem;margin:0 0 .5rem}
svg{width:100%;height:185px;overflow:visible}.axis{stroke:#dadce0}
.line{fill:none;stroke:#188038;stroke-width:2.5}.dot{fill:#188038}.tick{fill:#5f6368;font-size:11px}
</style>
<h1>Weaved performance history</h1>
<p>Selected ASV speedups on GitHub Actions, CPython 3.14.</p>
<p>Each point is Weaved versus the equivalent Python implementation measured in
the same run. Higher is faster; ratios reduce noise from runner speed changes.</p>
<div id="charts" class="grid"></div>
<script>
const data=__DATA__;
const ns='http://www.w3.org/2000/svg';
function el(tag,attrs={}){
 const n=document.createElementNS(ns,tag);
 for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);
 return n;
}
const names=[...new Set(data.flatMap(r=>Object.keys(r.benchmarks)))];
for(const name of names){
 const rows=data.filter(r=>r.benchmarks[name]&&Number.isFinite(r.benchmarks[name].speedup));
 if(!rows.length)continue;
 const values=rows.map(r=>r.benchmarks[name].speedup);
 const low=Math.min(1,...values),high=Math.max(1,...values);
 const pad=(high-low)*.12||.1,min=low-pad,max=high+pad;
 const W=500,H=185,L=48,R=12,T=14,B=30;
 const iw=W-L-R,ih=H-T-B;
 const x=i=>L+(rows.length===1?iw/2:i*iw/(rows.length-1));
 const y=v=>T+(max-v)*ih/(max-min);
 const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':name+' performance history'});
 for(const v of [min,(min+max)/2,max]){
  const yy=y(v);
  svg.append(el('line',{x1:L,y1:yy,x2:W-R,y2:yy,class:'axis'}));
  const t=el('text',{x:L-6,y:yy+4,'text-anchor':'end',class:'tick'});
  t.textContent=v.toFixed(1)+'×';svg.append(t);
 }
 svg.append(el('line',{x1:L,y1:y(1),x2:W-R,y2:y(1),class:'axis'}));
 svg.append(el('polyline',{points:values.map((v,i)=>`${x(i)},${y(v)}`).join(' '),class:'line'}));
 rows.forEach((r,i)=>{
  const dot=el('circle',{cx:x(i),cy:y(values[i]),r:4,class:'dot'});
  const tip=el('title');
  const date=new Date(r.date).toLocaleDateString();
  const speedup=r.benchmarks[name].speedup.toFixed(2);
  tip.textContent=`${r.commit.slice(0,7)} · ${date} · ${speedup}× faster than Python`;
  dot.append(tip);svg.append(dot);
 });
 const a=el('text',{x:L,y:H-5,class:'tick'});a.textContent=rows[0].commit.slice(0,7);svg.append(a);
 const b=el('text',{x:W-R,y:H-5,'text-anchor':'end',class:'tick'});
 b.textContent=rows.at(-1).commit.slice(0,7);svg.append(b);
 const card=document.createElement('article');
 const heading=document.createElement('h2');
 heading.textContent=name;card.append(heading,svg);
 document.querySelector('#charts').append(card);
}
</script></html>
""".replace("__DATA__", serialized)
    HTML_PATH.write_text(html)


def update(commit):
    date_ms, values = load_measurements(commit)
    rows = json.loads(DATA_PATH.read_text()) if DATA_PATH.exists() else []
    rows = [row for row in rows if row["commit"] != commit]
    rows.append(
        {
            "commit": commit,
            "date": datetime.fromtimestamp(date_ms / 1000, UTC).isoformat(),
            "benchmarks": values,
        }
    )
    rows.sort(key=lambda row: (row["date"], row["commit"]))
    DATA_PATH.write_text(json.dumps(rows, indent=2) + "\n")
    render(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: update_performance_report.py COMMIT")
    update(sys.argv[1])
