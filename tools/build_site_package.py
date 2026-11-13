"""Build the update for the demos site (cadence.floatingpragma.ai) from every demo's site.json.

    python tools/build_site_package.py --out DIR [--order slug,slug,...]

Writes:
  DIR/public/demos/<slug>/   each demo's page folder as the site serves it: index.html becomes
                             play.html with the site's theme link and data-demo on <body> (as the
                             live pages carry them); help.html and every other file as they are
  DIR/demos.json             the site's demo entries: slug, title, tagline, mechanism (the header's
                             first line), feature (the header's sentence and the home card), howTo
                             (TRY IT), embed, help, localOnly where a demo runs only locally
  DIR/public/index.html      a local preview of the site: the home page with the site's lines and
                             the cards, each demo under the site's header strip, the page in a frame
                             (serve DIR/public and open it; --theme puts the site's cadence-theme.css
                             beside it, as the site serves it)
A demo whose site.json names "deploy_dir" is copied from that folder (a built app) instead of
page_dir; "build" (a shell command run in the demo folder) builds it first.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules", "*.map")


def play_html(index: str, slug: str) -> str:
    """The page as the site serves it: the site's theme after the page's own styles, the slug on <body>."""
    if "/cadence-theme.css" not in index:
        index = re.sub(r"</head>", '  <link rel="stylesheet" href="/cadence-theme.css">\n</head>', index, count=1, flags=re.I)
    if "data-demo=" not in index:
        index = re.sub(r"<body(\s|>)", lambda m: f'<body data-demo="{slug}"' + m.group(1), index, count=1, flags=re.I)
    return index


PREVIEW = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cadence demos · preview</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root { --bg:#0d1416; --fg:#dcf0f1; --muted:#8ba3a8; --primary:#5ff2ef; --border:#24383d; }
* { box-sizing: border-box; } html, body { margin:0; height:100%; background:var(--bg); color:var(--fg); font:12px/1.6 "IBM Plex Mono", ui-monospace, monospace; }
a { color: var(--primary); text-decoration: none; }
header.top { position: sticky; top:0; z-index:3; display:flex; gap:22px; align-items:center; padding:12px 16px; border-bottom:1px solid var(--border); background:rgba(13,20,22,.94); overflow-x:auto; white-space:nowrap; }
header.top .brand { color:var(--primary); letter-spacing:.3em; text-transform:uppercase; }
header.top nav a { color:var(--muted); padding:3px 8px; } header.top nav a.on { color:var(--primary); outline:1px solid var(--primary); }
.hero { padding:90px 20px 60px; text-align:center; border-bottom:1px solid var(--border); }
.hero h1 { margin:0 0 18px; color:var(--primary); font-size:64px; font-weight:500; letter-spacing:.3em; }
.hero p { margin:4px 0; color:var(--fg); font-size:15px; } .hero p + p { color:var(--muted); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:18px; max-width:1180px; margin:40px auto; padding:0 20px; }
.cards a { display:block; padding:20px; border:1px solid var(--border); color:var(--muted); } .cards a b { display:block; margin-bottom:10px; color:var(--primary); letter-spacing:.25em; text-transform:uppercase; font-weight:500; }
.strip { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,1fr); gap:10px 40px; padding:16px 26px 14px; border-bottom:1px solid var(--border); }
.strip h2 { grid-column:1/-1; display:flex; justify-content:space-between; margin:0; font-size:21px; font-weight:400; }
.strip h2 span a { font-size:12px; margin-left:12px; }
.strip .claim { border-left:2px solid var(--primary); padding-left:12px; font-size:13px; }
.strip .k { display:block; color:var(--primary); font-size:11px; text-transform:uppercase; margin-bottom:2px; }
.strip .try { color:var(--muted); font-size:13px; } .strip .try .k { color:var(--muted); }
iframe { display:block; width:100%; height:calc(100vh - 200px); min-height:560px; border:0; }
.local { padding:30px 26px; color:var(--muted); }
</style></head><body>
<header class="top"><a class="brand" href="#/">&Lambda; Cadence</a><nav id="nav"></nav></header>
<main id="main"></main>
<script>
const DEMOS = __DEMOS__, HOME = __HOME__;
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function route() {
  const slug = (location.hash.match(/#\/demos\/([^/]+)/) || [])[1];
  document.getElementById('nav').innerHTML = DEMOS.map((d) => `<a href="#/demos/${d.slug}" class="${d.slug === slug ? 'on' : ''}">[${esc(d.title.toLowerCase())}]</a>`).join(' ');
  const main = document.getElementById('main');
  if (!slug) {
    main.innerHTML = `<section class="hero"><h1>${esc(HOME.title || 'CADENCE')}</h1>${(HOME.lines || []).map((l) => `<p>${esc(l)}</p>`).join('')}</section>`
      + `<div class="cards">${DEMOS.map((d) => `<a href="#/demos/${d.slug}"><b>${esc(d.title)}</b>${esc(d.feature)}</a>`).join('')}</div>`;
    return;
  }
  const d = DEMOS.find((x) => x.slug === slug);
  main.innerHTML = `<section class="strip"><h2>${esc(d.title)}<span><a href="${d.help}" target="_blank">[help]</a><a href="${d.github}" target="_blank">[github]</a></span></h2>`
    + `<div class="claim"><span class="k">Cadence / ${esc(d.mechanism)}</span>${esc(d.feature)}</div><div class="try"><span class="k">Try it</span>${esc(d.howTo)}</div></section>`
    + (d.localOnly ? `<p class="local">${esc(d.localOnly.reason || 'This demo runs on your own machine.')}</p>` : '')
    + `<iframe src="${d.embed}" title="${esc(d.title)}" allow="fullscreen"></iframe>`;
}
addEventListener('hashchange', route); route();
</script></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--order", default="", help="slugs in the order of the site's menu")
    ap.add_argument("--theme", type=Path, help="the site's cadence-theme.css, for the preview")
    ap.add_argument("--home", type=Path, help="a JSON file with the home page's lines: {title, lines: [...]}")
    args = ap.parse_args()
    metas = {}
    for site in sorted(ROOT.glob("*/site.json")):
        meta = json.loads(site.read_text())
        meta["_folder"] = site.parent
        metas[meta["slug"]] = meta
    order = [s for s in args.order.split(",") if s] or sorted(metas)
    order += [s for s in sorted(metas) if s not in order]
    public = args.out / "public" / "demos"
    entries = []
    for slug in order:
        if slug not in metas:
            print("no site.json for", slug, file=sys.stderr)
            return 1
        meta = metas[slug]
        folder = meta["_folder"]
        if meta.get("build"):
            subprocess.run(meta["build"], shell=True, cwd=folder, check=True)
        src = folder / meta.get("deploy_dir", meta.get("page_dir", "web"))
        dst = public / slug
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=SKIP)
        index = dst / "index.html"
        if index.exists():
            (dst / "play.html").write_text(play_html(index.read_text(), slug))
        entry = {"slug": slug, "title": meta["title"], "tagline": meta["tagline"], "mechanism": meta["kicker"],
                 "feature": meta["feature"], "howTo": meta["howTo"], "embed": f"/demos/{slug}/play.html",
                 "help": f"/demos/{slug}/{meta.get('help', 'help.html')}",
                 "github": f"https://github.com/muellerberndt/cadence-demos/tree/main/{folder.name}"}
        if meta.get("localOnly"):
            entry["localOnly"] = meta["localOnly"]
        entries.append(entry)
        size = sum(p.stat().st_size for p in dst.rglob("*") if p.is_file())
        print(f"{slug:14s} {len(list(dst.rglob('*'))):5d} files {size / 1e6:7.1f} MB  from {src.relative_to(ROOT)}")
    (args.out / "demos.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    home = json.loads(args.home.read_text()) if args.home else {"title": "CADENCE", "lines": []}
    if args.theme:
        shutil.copyfile(args.theme, args.out / "public" / "cadence-theme.css")
    (args.out / "public" / "index.html").write_text(PREVIEW.replace("__DEMOS__", json.dumps(entries, ensure_ascii=False)).replace("__HOME__", json.dumps(home, ensure_ascii=False)))
    print("wrote", args.out / "demos.json", len(entries), "demos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
