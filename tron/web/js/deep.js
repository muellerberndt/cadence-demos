// The brain in layers. The inputs (the field, the eyes, the heading arrow, as in ripple.js), then
// each layer of the connectome in order, L1, L2, ..., then the working trace (the last move's
// L-top state, fed back) when it is switched on, then the three motor neurons. The front of each
// settle passes through the layers in turn and every neuron plays its own recorded sweeps.
//
// Within a layer the neurons sit in groups by the role scripts/introspect.py decoded for them
// (pack/brain/introspect.json): what they fire on (a wall ahead, the left blocked, the opponent
// close, ...), "mixed" when no single feature explains them. A thin amber ring marks a neuron
// whose role the causal check supported (silencing or driving it changed the move).
//
// Beside each layer, "what it knows": linear probes fitted on held-out games, read live from
// the layer's settled state each move; the held-out score sits beside each bar (R^2, or the
// balanced accuracy with chance in brackets). A number probe with held-out R^2 < 0.1, or a
// class probe with too few held-out cases of a class, shows "n/a" and no bar. Hover or tap a neuron to zoom in: its role, the
// evidence, the causal effect if tested, its live activation, and its receptive field (input
// weights for L1, weights propagated through the layers below for deeper layers) drawn on the
// field here and on the arena, turned into the arena's frame.

import { RippleView, glow, rgba, MOTOR_RGB, ARROWS, PLAY_MS, roundRect } from "./ripple.js";

const LAYER_RGB = [[110, 160, 255], [90, 215, 255], [150, 130, 255], [120, 190, 255]];
const TRACE_RGB = [80, 235, 200];
const EXC = [255, 196, 90];   // a receptive field's excitatory weight
const INH = [150, 120, 255];  // inhibitory
const FAMILY_ORDER = ["ahead", "left", "right", "edge", "opponent", "territory", "apart", "cutoff", "teacher",
  "other", "mixed", "silent", "neurons"];
const FAMILY_NAME = { ahead: "ahead", left: "left", right: "right", edge: "edges", opponent: "opponent",
  territory: "territory", apart: "walled apart", cutoff: "cut-off", teacher: "teacher", other: "other roles",
  mixed: "mixed", silent: "silent", neurons: "neurons" };
const PLANE = 576;
const RF_FLOOR = 0.35; // a field shows its weights above this share of its largest
const MONO = "ui-monospace, Menlo, monospace";

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sigmoid = (z) => 1 / (1 + Math.exp(-z));

function decodeInt8(b64) {
  const raw = atob(b64);
  const out = new Int8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = (raw.charCodeAt(i) << 24) >> 24;
  return out;
}

// np.rot90(world, k=h) gives the rider's frame; this turns a rider-frame plane back.
function toWorld(plane, h, n = 24) {
  let a = plane;
  for (let t = 0; t < ((h % 4) + 4) % 4; t++) {
    const b = new Float32Array(n * n);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) b[i * n + j] = a[(n - 1 - j) * n + i];
    a = b;
  }
  return a;
}

export class DeepView extends RippleView {
  constructor(canvas, card) {
    super(canvas);
    this.card = card;
    this.intro = null;
    this.sel = null;
    this.hover = null;
    this.heading = null;
    this.frontMs = 520;
    this.probeShown = {};
    this.probeTarget = {};
    canvas.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") this.setHover(this.pick(e)); });
    canvas.addEventListener("pointerleave", () => this.setHover(null));
    canvas.addEventListener("click", (e) => { const i = this.pick(e); this.select(i === this.sel ? null : i); });
    window.addEventListener("keydown", (e) => { if (e.code === "Escape") this.select(null); });
  }

  setIntrospect(intro) { this.intro = intro; }

  setBrain(desc) {
    const pops = desc.populations;
    const intro = this.intro;
    const fits = intro && intro.neurons === desc.neurons && intro.layers.every((L) => pops[L.pop] && pops[L.pop][0] === L.start && pops[L.pop][1] === L.count);
    if (intro && !fits) console.warn("introspect.json does not match this brain; showing layers without roles");
    if (fits) {
      this.layers = intro.layers.map((L) => ({ ...L }));
    } else {
      // Without the introspection: the populations in their order, the trace if switched on.
      const off = desc.play && desc.play.working_memory_amplitude === 0;
      const names = Object.keys(pops).filter((k) => k !== "sensory" && !(off && k === "prefrontal"));
      names.sort((a, b) => {
        const rank = (k) => (k === "motor" ? 3 : k === "prefrontal" ? 2 : k === "association" ? 1 : 0);
        return rank(a) - rank(b) || pops[a][0] - pops[b][0];
      });
      let d = 0;
      this.layers = names.map((k) => {
        const kind = k === "motor" ? "motor" : k === "prefrontal" ? "trace" : "hidden";
        if (kind === "hidden") d += 1;
        return { key: kind === "hidden" ? `L${d}` : kind, name: kind === "hidden" ? `L${d}` : kind, pop: k, kind,
          start: pops[k][0], count: pops[k][1], labels: null, probes: [] };
      });
    }
    let h = 0;
    for (const L of this.layers) {
      L.rgb = L.kind === "trace" ? TRACE_RGB : L.kind === "motor" ? [220, 230, 255] : LAYER_RGB[h++ % LAYER_RGB.length];
      this.sprites[L.pop] = glow(L.rgb);
      L.groups = this.groupsOf(L);
    }
    this.layerOf = new Map();
    for (const L of this.layers) for (let k = 0; k < L.count; k++) this.layerOf.set(L.start + k, L);
    super.setBrain(desc);
    // Trace neurons that the design switches off stay hidden (super.setBrain marks them).
  }

  groupsOf(L) {
    if (L.kind === "motor") return [{ family: "motor", members: [...Array(L.count).keys()] }];
    if (!L.labels) return [{ family: "neurons", members: [...Array(L.count).keys()] }];
    const fam = new Map();
    L.labels.forEach((x, k) => {
      const f = x.family || "mixed";
      if (!fam.has(f)) fam.set(f, []);
      fam.get(f).push(k);
    });
    const other = [];
    for (const [f, m] of [...fam]) {
      if (m.length < 3 && !["mixed", "silent"].includes(f)) { other.push(...m); fam.delete(f); }
    }
    if (other.length) fam.set("other", other);
    const strength = (x) => Math.max(Math.abs(x.phi || 0), Math.abs(x.r || 0));
    const groups = [...fam].map(([family, members]) => {
      members.sort((a, b) => {
        const A = L.labels[a], B = L.labels[b];
        return (B.supported ? 1 : 0) - (A.supported ? 1 : 0) || String(A.key || "").localeCompare(String(B.key || "")) || strength(B) - strength(A);
      });
      return { family, members };
    });
    groups.sort((a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family));
    return groups;
  }

  // ---- layout ----------------------------------------------------------------------------
  layout() {
    if (!this.layers) return super.layout();
    const { W, H, dpr } = this;
    const n = this.n;
    this.px = new Float32Array(n);
    this.py = new Float32Array(n);
    this.pr = new Float32Array(n);
    this.disks = [];
    const m = 14 * dpr;
    this.landscape = W > H * 1.2 && W / dpr >= 720;
    let field, eyes, arrow;
    const bands = [];
    const weight = (L) => (L.kind === "motor" ? 0.8 : L.kind === "trace" ? 0.95 : 0.85 + 0.45 * Math.sqrt(L.count / 256));
    const total = this.layers.reduce((s, L) => s + weight(L), 0);
    if (!this.landscape) {
      const S = Math.min(W * 0.4, H * 0.24);
      field = { x: (W - S) / 2, y: m, S };
      const E = Math.min(S * 0.28, ((W - S) / 2 - m) * 0.4);
      const side = (W - S) / 4 + m * 0.25;
      eyes = [{ x: side, y: m + S * 0.42, R: E }, { x: W - side, y: m + S * 0.42, R: E }];
      arrow = { x: W - side, y: m + S * 0.42 + E + Math.max(14 * dpr, E * 0.7), R: Math.max(8 * dpr, E * 0.4) };
      let y = m + S + 16 * dpr;
      const y1 = H - 20 * dpr;
      const gap = 6 * dpr;
      const avail = y1 - y - gap * (this.layers.length - 1);
      for (const L of this.layers) {
        const h = (avail * weight(L)) / total;
        const inner = { x: m, y, w: W - 2 * m, h };
        const split = W / dpr < 480 ? 0.6 : 0.64;
        bands.push({ L, rect: inner, title: { x: m + 4 * dpr, y: y + 10 * dpr },
          dots: { x: m + 4 * dpr, y: y + 15 * dpr, w: inner.w * split - 8 * dpr, h: h - 19 * dpr },
          probe: { x: m + inner.w * (split + 0.02), y: y + 4 * dpr, w: inner.w * (0.98 - split), h: h - 8 * dpr }, axis: "x" });
        y += h + gap;
      }
    } else {
      const S = Math.min(H * 0.42, W * 0.18);
      field = { x: m, y: m + 4 * dpr, S };
      const E = Math.min(S * 0.3, H * 0.12);
      eyes = [{ x: m + E, y: m + S + E + 24 * dpr, R: E }, { x: m + S - E, y: m + S + E + 24 * dpr, R: E }];
      arrow = { x: m + S / 2, y: m + S + 2 * E + 52 * dpr, R: Math.max(8 * dpr, E * 0.4) };
      let x = m + S + 20 * dpr;
      const x1 = W - m;
      const gap = 8 * dpr;
      const avail = x1 - x - gap * (this.layers.length - 1);
      for (const L of this.layers) {
        const w = (avail * weight(L)) / total;
        const ph = Math.min(H * 0.34, 150 * dpr);
        bands.push({ L, rect: { x, y: m, w, h: H - m - 20 * dpr }, title: { x: x + 4 * dpr, y: m + 10 * dpr },
          dots: { x: x + 4 * dpr, y: m + 16 * dpr, w: w - 8 * dpr, h: H - m - 20 * dpr - ph - 24 * dpr },
          probe: { x: x + 4 * dpr, y: H - 20 * dpr - ph, w: w - 8 * dpr, h: ph - 4 * dpr }, axis: "y" });
        x += w + gap;
      }
    }
    this.placeInputs(field, eyes, arrow);
    this.bands = bands;
    if (this.card) {
      const css = (v) => `${Math.round(v / dpr)}px`;
      const wide = W / dpr >= 480;
      if (!this.landscape && wide) {
        const w = (W - field.S) / 2 - 22 * dpr;
        Object.assign(this.card.style, { width: css(w), left: "auto", right: css(10 * dpr), top: css(8 * dpr) });
      } else if (this.landscape) {
        Object.assign(this.card.style, { width: css(Math.min(280 * dpr, W * 0.3)), left: "auto", right: css(10 * dpr), top: css(8 * dpr) });
      } else Object.assign(this.card.style, { width: "", left: "", right: "", top: "" });
    }
    for (const b of bands) this.placeLayer(b);
    this.dots.width = this.dots.height = Math.max(8, Math.round(field.S));
  }

  placeLayer(b) {
    const { L, dots } = b;
    const dpr = this.dpr;
    const g = this.ctx;
    g.font = `500 ${8.5 * dpr}px ${MONO}`;
    if (L.kind === "motor") {
      const r = Math.min(9 * dpr, dots.h * 0.22);
      for (let k = 0; k < L.count; k++) {
        const i = L.start + k;
        if (b.axis === "x") { this.px[i] = dots.x + dots.w * (0.25 + 0.25 * k); this.py[i] = dots.y + dots.h * 0.62; }
        else { this.px[i] = dots.x + dots.w * 0.5; this.py[i] = dots.y + dots.h * (0.3 + 0.2 * k); }
        this.pr[i] = r;
      }
      b.groupBoxes = [];
      return;
    }
    // Groups flow in lines (rows mode) or columns (columns mode); each group a block of R
    // neuron rows under its label; the largest cell that fits wins.
    const groups = L.groups;
    const labelH = 11 * dpr;
    const gap = 10 * dpr, lineGap = 5 * dpr;
    const lw = groups.map((gr) => g.measureText(`${FAMILY_NAME[gr.family] || gr.family} ${gr.members.length}`).width + 6 * dpr);
    const W0 = dots.w, H0 = dots.h;
    const flow = (c, R) => {
      // lines of groups; returns placements or null
      const out = [];
      let x = 0, y = 0;
      const lineH = labelH + R * c;
      for (let j = 0; j < groups.length; j++) {
        const cols = Math.ceil(groups[j].members.length / R);
        const w = Math.max(cols * c, lw[j]);
        if (w > W0) return null;
        if (x > 0 && x + w > W0) { x = 0; y += lineH + lineGap; }
        out.push({ j, x, y, w, cols });
        x += w + gap;
      }
      return y + lineH <= H0 ? { out, lineH } : null;
    };
    let best = null;
    for (let c = 15 * dpr; c >= 2 * dpr && !best; c -= 0.25 * dpr) {
      for (let R = Math.max(1, Math.floor((H0 - labelH) / c)); R >= 1; R--) {
        const f = flow(c, R);
        if (f) { best = { c, R, ...f }; break; }
      }
    }
    if (!best) {
      const c = 2 * dpr, R = Math.max(1, Math.floor((H0 - labelH) / c));
      best = { c, R, ...(flow(c, R) || { out: groups.map((gr, j) => ({ j, x: 0, y: 0, w: W0, cols: Math.ceil(gr.members.length / R) })), lineH: H0 }) };
    }
    // Centre each line.
    const lines = new Map();
    for (const q of best.out) {
      const e = lines.get(q.y) || 0;
      lines.set(q.y, Math.max(e, q.x + q.w));
    }
    b.groupBoxes = [];
    for (const q of best.out) {
      const gr = groups[q.j];
      const shift = (W0 - lines.get(q.y)) / 2;
      const x0 = dots.x + shift + q.x, y0 = dots.y + q.y + labelH;
      const rows = Math.min(best.R, gr.members.length);
      gr.members.forEach((k, t) => {
        const i = L.start + k;
        this.px[i] = x0 + (Math.floor(t / rows) + 0.5) * best.c;
        this.py[i] = y0 + ((t % rows) + 0.5) * best.c;
        this.pr[i] = Math.max(1.1 * dpr, best.c * 0.3);
      });
      b.groupBoxes.push({ gr, x: x0, y: y0 - labelH, w: q.w, h: labelH + rows * best.c, label: [x0, y0 - 3 * dpr] });
    }
  }

  placeMotor() { /* the motor neurons are placed with their layer */ }

  // ---- the static layer: frames, titles, group labels, probe labels -------------------------
  drawStatic() {
    super.drawStatic();
    if (!this.bands) return;
    const g = this.static.getContext("2d");
    const { dpr } = this;
    g.textBaseline = "alphabetic";
    for (const b of this.bands) {
      const { L, rect } = b;
      g.fillStyle = rgba(L.rgb, 0.025);
      roundRect(g, rect.x, rect.y, rect.w, rect.h, 8 * dpr);
      g.fill();
      g.strokeStyle = rgba(L.rgb, 0.08);
      g.lineWidth = dpr;
      g.stroke();
      g.font = `600 ${9 * dpr}px ${MONO}`;
      g.textAlign = "left";
      g.fillStyle = rgba(L.rgb, 0.7);
      const what = L.kind === "trace" ? `trace · ${L.count} · ${this.W / dpr < 480 ? "last move" : "the last move, fed back"}` : L.kind === "motor" ? "motor" : `${L.name} · ${L.count}`;
      g.fillText(what, b.title.x, b.title.y);
      g.font = `500 ${8.5 * dpr}px ${MONO}`;
      for (const box of b.groupBoxes || []) {
        g.fillStyle = box.gr.family === "mixed" || box.gr.family === "silent" ? "rgba(150,165,190,0.38)" : "rgba(200,215,240,0.55)";
        g.fillText(`${FAMILY_NAME[box.gr.family] || box.gr.family} ${box.gr.members.length}`, box.label[0], box.label[1]);
      }
      // Every neuron, faintly, so the groups read when the layer is quiet.
      g.fillStyle = rgba(L.rgb, 0.16);
      for (let k = 0; k < L.count; k++) {
        const i = L.start + k;
        if (this.hidden[i]) continue;
        g.beginPath(); g.arc(this.px[i], this.py[i], Math.max(0.8 * dpr, this.pr[i] * 0.7), 0, Math.PI * 2); g.fill();
      }
      // Supported roles: a thin amber ring.
      if (L.labels) {
        g.strokeStyle = rgba(EXC, 0.75);
        g.lineWidth = Math.max(1, 0.9 * dpr);
        L.labels.forEach((x, k) => {
          if (!x.supported) return;
          const i = L.start + k;
          g.beginPath(); g.arc(this.px[i], this.py[i], this.pr[i] + 1.6 * dpr, 0, Math.PI * 2); g.stroke();
        });
      }
      this.drawProbeLabels(g, b);
    }
  }

  probeRows(b) {
    const P = b.L.probes || [];
    if (!P.length) return [];
    const head = 11 * this.dpr;
    const rowH = Math.min(17 * this.dpr, (b.probe.h - head) / P.length);
    return P.map((p, j) => ({ p, y: b.probe.y + head + j * rowH, h: rowH }));
  }

  drawProbeLabels(g, b) {
    const rows = this.probeRows(b);
    if (!rows.length) return;
    const { dpr } = this;
    const pr = b.probe;
    g.font = `500 ${8 * dpr}px ${MONO}`;
    g.textAlign = "left";
    g.fillStyle = "rgba(150,170,200,0.5)";
    g.fillText("what it knows", pr.x, pr.y + 7 * dpr);
    const fs = Math.max(7 * dpr, Math.min(8.5 * dpr, rows[0].h * 0.55));
    for (const { p, y, h } of rows) {
      const good = this.probeGood(p);
      g.font = `500 ${fs}px ${MONO}`;
      g.textAlign = "left";
      g.fillStyle = good ? "rgba(210,222,245,0.72)" : "rgba(150,165,190,0.42)";
      g.fillText(p.title, pr.x, y + h * 0.66);
      g.textAlign = "right";
      g.font = `500 ${fs * 0.92}px ${MONO}`;
      g.fillStyle = good ? "rgba(170,190,220,0.55)" : "rgba(150,165,190,0.35)";
      g.fillText(this.probeScore(p), pr.x + pr.w, y + h * 0.66);
      const bx = this.barX(b);
      g.fillStyle = "rgba(120,160,220,0.07)";
      g.fillRect(bx.x, y + h * 0.28, bx.w, h * 0.44);
    }
  }

  barX(b) {
    const w = b.probe.w;
    return { x: b.probe.x + w * 0.46, w: w * 0.3 };
  }

  probeScore(p) {
    const s = p.score || {};
    if (p.kind === "num") return s.r2 < 0.1 ? "n/a" : `R² ${s.r2.toFixed(2).replace(/^0/, "")}`;
    if (s.insufficient) return "n/a";
    return `${Math.round(100 * s.balanced)}% (${Math.round(100 * s.chance)})`;
  }

  probeGood(p) {
    const s = p.score || {};
    return p.kind === "num" ? s.r2 >= 0.1 : !s.insufficient && s.balanced >= s.chance + 0.1;
  }

  // ---- a move ------------------------------------------------------------------------------
  delays(origin) {
    if (!this.bands) return super.delays(origin);
    const delay = new Float32Array(this.n);
    const nb = this.bands.length;
    this.bandDelay = [];
    this.bands.forEach((b, j) => {
      const d0 = 0.16 + (0.72 * j) / Math.max(1, nb - 1);
      this.bandDelay.push(d0);
      const { L, dots } = b;
      for (let k = 0; k < L.count; k++) {
        const i = L.start + k;
        const along = b.axis === "x" ? (this.px[i] - dots.x) / Math.max(1, dots.w) : (this.py[i] - dots.y) / Math.max(1, dots.h);
        delay[i] = Math.min(1, d0 + 0.08 * along);
      }
    });
    for (let i = 0; i < this.offset; i++) {
      delay[i] = 0.08 * Math.hypot(this.px[i] - origin[0], this.py[i] - origin[1]) / Math.max(1, this.field.S);
    }
    return { delay, far: 1 };
  }

  push(state) {
    super.push(state);
    if (state.headings) this.heading = state.headings[0];
    if (!this.bands || !state.nframes) return;
    const a = this.last;
    for (const b of this.bands) {
      const L = b.L;
      const lo = L.start - this.offset;
      for (const p of L.probes || []) {
        const z = p.b.map((bias, c) => {
          let s = bias;
          const w = p.w[c];
          for (let k = 0; k < w.length; k++) s += w[k] * a[lo + k];
          return s;
        });
        let t;
        if (p.kind === "num") {
          const [r0, r1] = p.range || [0, 1];
          t = [Math.max(0, Math.min(1, (z[0] - r0) / Math.max(1e-9, r1 - r0)))];
          t.value = z[0];
        } else if (p.kind === "bin") t = [sigmoid(z[0])];
        else {
          const mx = Math.max(...z);
          const e = z.map((v) => Math.exp(v - mx));
          const s = e.reduce((u, v) => u + v, 0);
          t = e.map((v) => v / s);
        }
        this.probeTarget[`${L.key}:${p.key}`] = t;
      }
    }
    this.boardKey = null;
  }

  drawFronts(g, now) {
    if (!this.bands) return super.drawFronts(g, now);
    const { dpr } = this;
    for (const w of this.waves) {
      const dt0 = now - w.t0;
      if (dt0 < 0 || dt0 > this.frontMs + PLAY_MS + 200) continue;
      // The inputs light first, then each layer as the front reaches it.
      const f = this.field;
      const a0 = 0.1 * Math.max(0, 1 - dt0 / 260);
      if (a0 > 0) {
        g.fillStyle = `rgba(120,200,255,${a0})`;
        roundRect(g, f.x - 6 * dpr, f.y - 6 * dpr, f.S + 12 * dpr, f.S + 12 * dpr, 10 * dpr);
        g.fill();
      }
      this.bands.forEach((b, j) => {
        const t = dt0 - (this.bandDelay ? this.bandDelay[j] : 0) * this.frontMs;
        if (t < 0 || t > 340) return;
        const p = t / 340;
        const r = b.rect;
        const L = b.L;
        // A soft edge of light sweeping across the layer, then fading.
        const along = b.axis === "x" ? r.x + p * r.w : r.y + p * r.h;
        const grad = b.axis === "x" ? g.createLinearGradient(along - 60 * dpr, 0, along + 10 * dpr, 0)
          : g.createLinearGradient(0, along - 60 * dpr, 0, along + 10 * dpr);
        grad.addColorStop(0, rgba(L.rgb, 0));
        grad.addColorStop(0.85, rgba(L.rgb, 0.11 * (1 - p)));
        grad.addColorStop(1, rgba(L.rgb, 0));
        g.fillStyle = grad;
        roundRect(g, r.x, r.y, r.w, r.h, 8 * dpr);
        g.fill();
      });
    }
  }

  // ---- the frame's top layer: probe bars, the selected neuron, its receptive field --------
  overlay(g, now) {
    if (!this.bands) return;
    const { dpr } = this;
    g.globalCompositeOperation = "source-over";
    for (const b of this.bands) {
      const bx = this.barX(b);
      for (const { p, y, h } of this.probeRows(b)) {
        const key = `${b.L.key}:${p.key}`;
        const target = this.probeTarget[key];
        if (!target) continue;
        if ((p.kind === "num" || (p.score && p.score.insufficient)) && !this.probeGood(p)) continue; // "n/a": no reading shown
        const shown = this.probeShown[key] || target.map(() => 0);
        for (let c = 0; c < target.length; c++) shown[c] += (target[c] - shown[c]) * 0.18;
        this.probeShown[key] = shown;
        const alpha = this.probeGood(p) ? 0.85 : 0.3;
        if (p.kind === "move") {
          const seg = bx.w / 3;
          let best = 0;
          for (let c = 1; c < 3; c++) if (shown[c] > shown[best]) best = c;
          for (let c = 0; c < 3; c++) {
            g.fillStyle = rgba(MOTOR_RGB[c], alpha * (c === best ? 1 : 0.45));
            const hh = h * 0.5 * Math.max(0.08, shown[c]);
            g.fillRect(bx.x + c * seg + seg * 0.15, y + h * 0.75 - hh, seg * 0.7, hh);
          }
        } else {
          g.fillStyle = rgba(b.L.rgb, alpha);
          g.fillRect(bx.x, y + h * 0.3, bx.w * Math.max(0.02, shown[0]), h * 0.4);
        }
      }
    }
    const i = this.active();
    if (i === null) return;
    const L = this.layerOf.get(i);
    if (!L) return;
    this.drawField(g, i, L);
    const r = this.pr[i];
    g.strokeStyle = "rgba(255,255,255,0.95)";
    g.lineWidth = 1.5 * dpr;
    g.beginPath(); g.arc(this.px[i], this.py[i], r + 4 * dpr, 0, Math.PI * 2); g.stroke();
    this.updateCard(i, L, now);
  }

  // The receptive field on the brain's own field (the blocked plane) and in the eye (fovea).
  drawField(g, i, L) {
    const rf = this.rfOf(i, L);
    if (!rf) return;
    const f = this.field;
    const c = f.S / 24;
    g.globalCompositeOperation = "source-over";
    g.fillStyle = "rgba(0,0,0,0.55)";
    g.fillRect(f.x, f.y, f.S, f.S);
    g.globalCompositeOperation = "lighter";
    const plane = rf.blocked;
    for (let q = 0; q < PLANE; q++) {
      const v = plane[q];
      const a = (Math.abs(v) - RF_FLOOR) / (1 - RF_FLOOR);
      if (a <= 0) continue;
      g.fillStyle = rgba(v > 0 ? EXC : INH, 0.25 + 0.7 * a);
      g.fillRect(f.x + (q % 24) * c + 0.5, f.y + Math.floor(q / 24) * c + 0.5, c - 1, c - 1);
    }
    const eye = this.eyes[0];
    const spec = this.spec.fovea;
    for (let q = 0; q < 81; q++) {
      const v = rf.fovea[q];
      if (Math.abs(v) < RF_FLOOR) continue;
      const k = spec.start + q;
      const R = Math.max(2 * this.dpr, eye.R * 0.13) * (0.6 + Math.abs(v));
      g.fillStyle = rgba(v > 0 ? EXC : INH, Math.min(0.9, Math.abs(v)));
      g.beginPath(); g.arc(this.px[k], this.py[k], R * 0.5, 0, Math.PI * 2); g.fill();
    }
    g.globalCompositeOperation = "source-over";
  }

  rfOf(i, L) {
    if (!L.rf) return null;
    if (!L.rfData) L.rfData = decodeInt8(L.rf);
    const k = i - L.start;
    const n = this.offset;
    const base = k * n;
    const plane = (start, len) => {
      let mx = 1e-9;
      for (let q = 0; q < len; q++) mx = Math.max(mx, Math.abs(L.rfData[base + start + q]));
      const out = new Float32Array(len);
      for (let q = 0; q < len; q++) out[q] = L.rfData[base + start + q] / mx;
      return out;
    };
    const sp = this.spec;
    return { blocked: plane(sp.blocked.start, PLANE), you: plane(sp.you.start, PLANE), self: plane(sp.self.start, PLANE),
      fovea: plane(sp.fovea.start, 81) };
  }

  // The selected neuron's field on the arena, in the arena's frame (main.js draws it).
  boardOverlay() {
    const i = this.active();
    if (i === null || this.heading === null) return null;
    const L = this.layerOf.get(i);
    const key = `${i}:${this.heading}`;
    if (this.boardKey === key) return this.board;
    const rf = L && this.rfOf(i, L);
    this.board = rf ? { values: toWorld(rf.blocked, this.heading), exc: EXC, inh: INH, floor: RF_FLOOR } : null;
    this.boardKey = key;
    return this.board;
  }

  // ---- picking and the card ------------------------------------------------------------------
  pick(e) {
    if (!this.layerOf) return null;
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) * this.dpr, y = (e.clientY - rect.top) * this.dpr;
    let best = null, bd = Infinity;
    for (const [i] of this.layerOf) {
      if (this.hidden[i]) continue;
      const d = Math.hypot(this.px[i] - x, this.py[i] - y);
      if (d < bd) { bd = d; best = i; }
    }
    return best !== null && bd <= Math.max(9 * this.dpr, this.pr[best] * 2.5) ? best : null;
  }

  active() { return this.sel !== null ? this.sel : this.hover; }

  setHover(i) {
    if (i === this.hover) return;
    this.hover = i;
    this.canvas.style.cursor = i === null ? "" : "pointer";
    this.cardFor = null;
    if (this.active() === null) this.hideCard();
  }

  select(i) {
    this.sel = i;
    this.cardFor = null;
    if (this.active() === null) this.hideCard();
  }

  hideCard() { if (this.card) this.card.classList.remove("on"); }

  updateCard(i, L, now) {
    if (!this.card) return;
    const k = i - L.start;
    if (this.cardFor !== i) {
      this.cardFor = i;
      const x = L.labels ? L.labels[k] : null;
      const name = L.kind === "motor" ? `motor · ${["left", "straight", "right"][k] || k}` : `${L.name} · ${k}`;
      let html = `<div class="zh"><span class="zn" style="color:${rgba(L.rgb, 1)}">${esc(name)}</span>`;
      if (x && x.family && FAMILY_NAME[x.family]) html += `<span class="zf">${esc(FAMILY_NAME[x.family])}</span>`;
      if (x && x.supported) html += `<span class="zs">causal</span>`;
      html += `</div>`;
      if (L.kind === "motor") html += `<div class="zr">the move ${ARROWS[k] || ""} is read from these three</div>`;
      else if (!x) html += `<div class="zr dim">no introspection for this brain</div>`;
      else if (x.silent) html += `<div class="zr dim">barely moves (fires on ${Math.round(100 * (x.fires || 0))}% of positions)</div>`;
      else if (x.mixed) html += `<div class="zr dim">mixed: no single feature explains it</div><div class="ze">closest: ${esc(x.best)} φ ${fmt(x.phi)} · r ${fmt(x.r)}</div>`;
      else {
        html += `<div class="zr">${esc(x.role)}</div>`;
        if (x.kind === "tracks") html += `<div class="ze">r ${fmt(x.r)}</div>`;
        else html += `<div class="ze">φ ${fmt(x.phi)} · fires ${pct(x.rate_with)} with, ${pct(x.rate_without)} without</div>`;
      }
      if (x && x.causal) {
        html += `<div class="zc${x.causal.clear ? " ok" : ""}">${esc(x.causal.effect)} · n ${x.causal.n}</div>`;
      } else if (x && !x.silent && !x.mixed && L.kind !== "motor") html += `<div class="zc dim">causal check: not tested</div>`;
      html += `<div class="za"><span>now</span><i><b></b></i><em></em></div>`;
      if (L.rf) html += `<div class="zk"><span class="e"></span>excites <span class="n"></span>inhibits · its field on the board</div>`;
      this.card.innerHTML = html;
      this.card.classList.add("on");
      this.cardBar = this.card.querySelector(".za b");
      this.cardVal = this.card.querySelector(".za em");
    }
    const got = this.value(i - this.offset, now);
    const v = got ? got.v : this.last ? this.last[i - this.offset] : 0;
    const lo = L.act_lo ? L.act_lo[k] : -0.1, hi = L.act_hi ? L.act_hi[k] : 1;
    const t = Math.max(0, Math.min(1, (v - Math.min(lo, -0.1)) / Math.max(1e-3, Math.max(hi, 0.05) - Math.min(lo, -0.1))));
    if (this.cardBar) this.cardBar.style.width = `${(100 * t).toFixed(1)}%`;
    if (this.cardVal) this.cardVal.textContent = v.toFixed(2);
  }
}

function fmt(v) { return typeof v === "number" ? (v >= 0 ? "+" : "") + v.toFixed(2) : "-"; }
function pct(v) { return typeof v === "number" ? `${Math.round(100 * v)}%` : "-"; }
