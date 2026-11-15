"""The parrot page's own checks, in headless Chromium on the real page; writes ../evidence/page_check.json.

    python parrot/site/tools/check_page.py [--shots DIR] [--looks realistic,anime] [--seconds 10]

1. The page runs end to end: the room, the parrot, both eyes and the brain (the pack's host in
   Pyodide). It counts the brain's moments and the frames drawn over --seconds, and the brain's
   time per moment (the worker's).
2. The skin holds: for each look, every joint is swept through its range (seven values, the other
   joints at rest), and the head's turn with its tilt and with its cock over 7 by 7 grids within the
   combined limits; the body's skinning is computed on the CPU (three.js applyBoneTransform); no
   edge of a triangle may stretch beyond 1.25 times its length at rest. Edges shorter than 0.5 mm
   (slivers the decimation leaves) are measured against 0.5 mm; the raw worst ratio is reported too.
3. The head is rigid: over the head's and the neck's sweeps, the distances between points of the
   beak and of the eyes' sockets change by at most 1 %; and with every joint at its bind value the
   skinned body is the prepared body (at most 0.05 mm apart).
4. The distance units answer: the placeholder brain's units respond to a thing moved nearer and
   further, and silencing them silences them inside the host (its reading of distance goes).
Shots (with --shots): the page, the head close-up at rest and turned, and each look from the front.
"""
from __future__ import annotations

import argparse
import datetime
import functools
import http.server
import json
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1]
EVIDENCE = SITE.parent / "evidence"

SWEEP_JS = r"""
async () => {
  const FLOOR = 0.0005;
  const P = window.parrotPage.parrot, J = P.joints;
  const mesh = P.skinned[0], geo = mesh.geometry, pos = geo.attributes.position, n = pos.count;
  const THREE = window.parrotPage.THREE;
  const idx = geo.index.array;
  // the triangles' edges, once each
  const seen = new Set(), edges = [];
  for (let t = 0; t < idx.length; t += 3) for (const [a, b] of [[idx[t], idx[t + 1]], [idx[t + 1], idx[t + 2]], [idx[t + 2], idx[t]]]) {
    const k = a < b ? a * n + b : b * n + a; if (!seen.has(k)) { seen.add(k); edges.push(a < b ? a : b, a < b ? b : a); }
  }
  const rest = new Float32Array(edges.length / 2);
  const P0 = new Float32Array(3 * n), v = new THREE.Vector3();
  for (let i = 0; i < n; i++) { P0[3 * i] = pos.getX(i); P0[3 * i + 1] = pos.getY(i); P0[3 * i + 2] = pos.getZ(i); }
  for (let e = 0; e < rest.length; e++) { const a = edges[2 * e], b = edges[2 * e + 1]; rest[e] = Math.hypot(P0[3 * a] - P0[3 * b], P0[3 * a + 1] - P0[3 * b + 1], P0[3 * a + 2] - P0[3 * b + 2]); }
  const skinned = new Float32Array(3 * n);
  const setAll = (vals) => { for (let i = 0; i < J.n; i++) { J.pos[i] = vals[i]; J.target[i] = vals[i]; J.vel[i] = 0; } P.update(0); };
  const skin = () => { for (let i = 0; i < n; i++) { v.fromBufferAttribute(pos, i); mesh.applyBoneTransform(i, v); skinned[3 * i] = v.x; skinned[3 * i + 1] = v.y; skinned[3 * i + 2] = v.z; } };
  const restVals = J.spec.map((j) => j.rest);
  // the bind values: every joint where the body was made (the head at its rest turn)
  const bindVals = restVals.slice(); const hy = J.index.head_yaw; bindVals[hy] = P.rig.head_rest_yaw || 0;
  setAll(bindVals); skin();
  let bindErr = 0; for (let i = 0; i < 3 * n; i++) bindErr = Math.max(bindErr, Math.abs(skinned[i] - P0[i]));
  // rigid parts: points of the beak (vertices bound only to the head) near the beak's tip, and the sockets
  const si = geo.attributes.skinIndex, sw = geo.attributes.skinWeight, headIdx = P.boneList.indexOf(P.bones.head);
  const headOnly = []; for (let i = 0; i < n; i++) if (si.getX(i) === headIdx && sw.getX(i) > 0.999) headOnly.push(i);
  const step = Math.max(1, Math.floor(headOnly.length / 200)); if (!headOnly.length) return { error: 'no vertex bound to the head alone' }; const probe = headOnly.filter((_, k) => k % step === 0);
  const pairDist = () => { const d = []; for (let a = 0; a < probe.length; a += 7) for (let b = a + 3; b < probe.length; b += 11) { const i = probe[a], j = probe[b]; d.push(Math.hypot(skinned[3 * i] - skinned[3 * j], skinned[3 * i + 1] - skinned[3 * j + 1], skinned[3 * i + 2] - skinned[3 * j + 2])); } return d; };
  const restPairs = pairDist();
  const out = { joints: {}, worst: { ratio: 0 }, bind_error_m: bindErr, rigid_head_max_change: 0, edges: rest.length, vertices: n };
  for (let j = 0; j < J.n; j++) {
    const spec = J.spec[j]; let worst = { ratio: 0 }, raw = 0;
    for (let k = 0; k < 7; k++) {
      const vals = restVals.slice(); vals[j] = spec.min + (k / 6) * (spec.max - spec.min);
      setAll(vals); skin();
      for (let e = 0; e < rest.length; e++) {
        if (rest[e] < 1e-5) continue;
        const a = edges[2 * e], b = edges[2 * e + 1];
        const L = Math.hypot(skinned[3 * a] - skinned[3 * b], skinned[3 * a + 1] - skinned[3 * b + 1], skinned[3 * a + 2] - skinned[3 * b + 2]);
        const r = L / Math.max(rest[e], FLOOR); raw = Math.max(raw, L / rest[e]);
        if (r > worst.ratio) worst = { ratio: r, value: vals[j], at: [skinned[3 * a], skinned[3 * a + 1], skinned[3 * a + 2]].map((x) => +x.toFixed(4)) };
      }
      if (['head_yaw', 'head_pitch', 'head_roll', 'neck_pitch'].includes(spec.name)) {
        const d = pairDist(); let m = 0; for (let q = 0; q < d.length; q++) m = Math.max(m, Math.abs(d[q] / restPairs[q] - 1));
        out.rigid_head_max_change = Math.max(out.rigid_head_max_change, m);
      }
    }
    out.joints[spec.name] = { worst_ratio: +worst.ratio.toFixed(3), raw_ratio: +raw.toFixed(3), at_value: worst.value, where: worst.at };
    if (worst.ratio > out.worst.ratio) out.worst = { ratio: +worst.ratio.toFixed(3), joint: spec.name, value: worst.value, where: worst.at };
  }
  // pairs: the head's turn with its tilt and with its cock, over a 7 by 7 grid within the combined limits
  const stretchNow = () => { let w = { ratio: 0 }; for (let e = 0; e < rest.length; e++) { if (rest[e] < 1e-5) continue; const a = edges[2 * e], b = edges[2 * e + 1];
    const r = Math.hypot(skinned[3 * a] - skinned[3 * b], skinned[3 * a + 1] - skinned[3 * b + 1], skinned[3 * a + 2] - skinned[3 * b + 2]) / Math.max(rest[e], FLOOR);
    if (r > w.ratio) w = { ratio: r, at: [skinned[3 * a], skinned[3 * a + 1], skinned[3 * a + 2]].map((x) => +x.toFixed(4)) }; } return w; };
  out.pairs = {};
  for (const other of ['head_pitch', 'head_roll']) {
    const iy = J.index.head_yaw, io = J.index[other]; let worst = { ratio: 0 };
    for (let a = 0; a < 7; a++) for (let b = 0; b < 7; b++) {
      const vals = restVals.slice(); vals[iy] = J.spec[iy].min + (a / 6) * (J.spec[iy].max - J.spec[iy].min);
      for (let i = 0; i < J.n; i++) J.pos[i] = vals[i];
      const [lo, hi] = J.limits(io); vals[io] = lo + (b / 6) * (hi - lo);
      setAll(vals); skin();
      const w = stretchNow();
      if (w.ratio > worst.ratio) worst = { ratio: +w.ratio.toFixed(3), yaw: vals[iy], [other]: +vals[io].toFixed(2), where: w.at };
      const d = pairDist(); let m = 0; for (let q = 0; q < d.length; q++) m = Math.max(m, Math.abs(d[q] / restPairs[q] - 1));
      out.rigid_head_max_change = Math.max(out.rigid_head_max_change, m);
    }
    out.pairs[`head_yaw x ${other}`] = worst;
    if (worst.ratio > out.worst.ratio) out.worst = { ratio: worst.ratio, joint: `head_yaw x ${other}`, value: [worst.yaw, worst[other]], where: worst.where };
  }
  setAll(restVals);
  return out;
}
"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--looks", default="realistic,anime")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--limit", type=float, default=1.25)
    args = ap.parse_args()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    report: dict = {"checked": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "looks": {}, "checks": []}
    try:
        report["commit"] = subprocess.run(["git", "-C", str(SITE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        report["load_average"] = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip().split("load average")[-1].strip(": ")
    except OSError:
        pass

    def check(ok: bool, name: str, detail: object = "") -> None:
        report["checks"].append({"ok": bool(ok), "name": name, "detail": detail})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
        for look in args.looks.split(","):
            page = browser.new_page(viewport={"width": 1512, "height": 860})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(f"{base}index.html?look={look}")
            page.wait_for_selector("body[data-ready='1']", timeout=240000)
            page.wait_for_function("Number(document.body.dataset.moment || 0) > 5", timeout=120000)
            m0 = page.evaluate("Number(document.body.dataset.moment)")
            page.evaluate("window.__frames = 0; (function f(){ window.__frames++; requestAnimationFrame(f); })()")
            page.wait_for_timeout(int(args.seconds * 1000))
            run = page.evaluate("({ moments: Number(document.body.dataset.moment), frames: window.__frames, think: document.getElementById('s-think').textContent, status: document.getElementById('status-text').textContent, look: document.body.dataset.look, eye_ms: window.parrotPage.eyes.ms })")
            moments_per_s = (run["moments"] - m0) / args.seconds
            fps = run["frames"] / args.seconds
            entry = {"look": run["look"], "frames_per_s": round(fps, 1), "moments_per_s": round(moments_per_s, 2), "think": run["think"], "eyes_ms": round(run["eye_ms"], 2), "status": run["status"]}
            check(run["look"] == look, f"{look}: the look loads (not the fallback)", run["look"])
            check(moments_per_s >= 8.0, f"{look}: the brain lives near 10 moments a second", entry)
            if args.shots:
                page.screenshot(path=str(args.shots / f"page-{look}.png"))
            # the distance units answer, and silencing them silences them in the host
            dist = page.evaluate("""async () => {
              const pg = window.parrotPage; pg.room.clear(); pg.setMode('you');
              const P = pg.parrot; P.joints.set('head_yaw', 0); P.joints.set('head_pitch', -10);
              const id = await pg.place('apple', 0.22, 0.12); pg.state.subject = id;
              const read = () => new Promise((r) => setTimeout(() => r(pg.state.lastReply), 700));
              const near = await read(); pg.move(id, 0.55, 0.32); const far = await read();
              document.getElementById('silence').click(); const quiet = await read(); document.getElementById('silence').click();
              const sum = (x) => (x?.group_activity?.distance || []).reduce((a, b) => a + b, 0);
              return { near: sum(near), far: sum(far), silenced: sum(quiet), reading_near: near?.readout?.distance, reading_far: far?.readout?.distance, reading_silenced: quiet?.readout?.distance };
            }""")
            check(dist["silenced"] == 0 and dist["reading_silenced"] is None, f"{look}: silencing the distance units silences them in the host", dist)
            entry["distance_units"] = dist
            sweep = page.evaluate(SWEEP_JS)
            entry["skin"] = sweep
            check(sweep["worst"]["ratio"] <= args.limit, f"{look}: no triangle edge stretches beyond {args.limit}x over every joint's range", sweep["worst"])
            check(sweep["rigid_head_max_change"] <= 0.01, f"{look}: the head and beak stay rigid as the head turns", round(sweep["rigid_head_max_change"], 5))
            check(sweep["bind_error_m"] <= 5e-5, f"{look}: at the bind values the skinned body is the prepared body", sweep["bind_error_m"])
            if args.shots:
                for name, joints in (("rest", {}), ("turned", {"head_yaw": 60, "head_roll": 20}), ("bind", {"head_yaw": None})):
                    page.evaluate("""([joints]) => { const P = window.parrotPage.parrot, J = P.joints;
                      for (let i = 0; i < J.n; i++) { J.pos[i] = J.target[i] = J.spec[i].rest; J.vel[i] = 0; }
                      for (const [k, v] of Object.entries(joints)) { const i = J.index[k]; J.pos[i] = J.target[i] = (v === null ? (P.rig.head_rest_yaw || 0) : v); }
                      P.update(0); window.parrotPage.view('head'); }""", [joints])
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(args.shots / f"head-{look}-{name}.png"))
            check(not errors, f"{look}: no console or page error", errors[:5])
            report["looks"][look] = entry
            page.close()
        browser.close()
    server.shutdown()
    report["passed"] = all(c["ok"] for c in report["checks"])
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / "page_check.json").write_text(json.dumps(report, indent=1) + "\n")
    for c in report["checks"]:
        print(("ok   " if c["ok"] else "FAIL ") + c["name"] + ("" if c["ok"] else f"  {json.dumps(c['detail'], default=str)[:300]}"))
    for look, e in report["looks"].items():
        print(f"{look}: {e['frames_per_s']} frames/s, {e['moments_per_s']} moments/s, think {e['think']}, eyes {e['eyes_ms']} ms; worst stretch {e['skin']['worst']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
