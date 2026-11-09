// The brain inspector, drawn as a brain seen from the side. Every pixel comes from the selected
// robot's brain in this moment, as the worker read it from the brain itself (py/host.py):
// - each dot is one neuron of a Cadence population, at its settled activation;
// - the curved fibres are the strongest synapses of each projection, lit by |weight x presynaptic
//   activation| (warm excitatory, cool inhibitory);
// - the settle plays sweep by sweep from the recorded trajectory of the act (every eighth moment),
//   with the movement of every sweep falling toward the tolerance;
// - the gold or blue wash from the midbrain is the critic's reward prediction error of the moment;
// - the whole brain brightens when the arousal law has it aroused (sampling and learning);
// - synapses a learning step changed flash, thicker where the efficacy grew;
// - the hippocampus row is the recall memory's stored moments, lit when a moment reads them.
// Regions are named for the role their population plays; none of it claims to be the animal organ.

import { Frame, Spec } from "./types";

export type Anatomy = {
  name: string; neurons: number; synapses: number;
  populations: { name: string; index: number[] }[];
  tracts: { pre: string; post: string; synapses: number; drawn: number[]; from: number[]; to: number[]; w: number[] }[];
  sensory: number[]; motor: number[]; recall_capacity: number;
};
export type Inspect = {
  t: number; settles: number; learning_settles: number; learning_sweeps: number; sweeps?: number;
  movement?: number[]; state?: number[];
  trajectory?: { sweeps: number[]; neurons: number; q: string };
  plasticity: { changed: number; max: number; top: number[]; delta: number[]; pre: number[]; post: number[]; w: number[] };
  arousal: { mode: string; level: number; error: number; surprise: number; want: number; learned: boolean; heated_slot: number | null };
  rpe: number | null;
  recall?: { stored: number; capacity: number; reads: [number, number, number][] };
};

type Region = { key: string; title: string; role: string; cx: number; cy: number; rx: number; ry: number; hue: string };
const ROLE: Record<string, [string, string, string]> = {
  // population -> [title, the role it plays, colour]
  sensory: ["sensory cortex", "plays the role of the sensory cortex: every sense of the body enters here, as through the thalamus", "#5ec8ff"],
  association: ["association cortex", "plays the role of the association cortex: the region the motor cortex and the working trace read", "#9b8cff"],
  prefrontal: ["prefrontal cortex", "plays the role of the prefrontal cortex: the working trace of the last settled state feeds back here", "#ff8bd1"],
  motor: ["motor cortex", "plays the role of the motor strip: one group per motor, the strongest neuron of a group is its command", "#ffb347"],
  recall: ["hippocampus", "plays the role of the hippocampus: the recall memory's read of stored moments", "#7dffb0"],
  next: ["hippocampus", "the recall memory's forecast of the next event", "#62e39a"],
};
const W = 1240, H = 650, OY = 92; // the brain sits below a status band of OY pixels

function roleOf(name: string): [string, string, string] {
  if (ROLE[name]) return ROLE[name];
  if (name.startsWith("module_")) return ["cortex " + name.slice(7), "an intermediate cortical region between the senses and the association cortex", "#74a7ff"];
  return [name, "a population of the brain", "#9aa3b5"];
}

function decodeQ(q: string, neurons: number): Float32Array[] {
  const bin = atob(q); const n = Math.floor(bin.length / neurons); const out: Float32Array[] = [];
  for (let k = 0; k < n; k++) {
    const a = new Float32Array(neurons);
    for (let i = 0; i < neurons; i++) a[i] = (bin.charCodeAt(k * neurons + i) / 255) * 1.1 - 0.1;
    out.push(a);
  }
  return out;
}

function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
}

export class BrainView {
  private c: CanvasRenderingContext2D;
  private an: Anatomy | null = null;
  private spec: Spec | null = null;
  private regions = new Map<string, Region>();
  private pos = new Float32Array(0); // x, y per neuron
  private popOf = new Int16Array(0);
  private popNames: string[] = [];
  private act = new Float32Array(0);
  private sweepLabel = "";
  private replay: { frames: Float32Array[]; sweeps: number[]; started: number; t: number } | null = null;
  private last: Inspect | null = null;
  private wash: { start: number; value: number }[] = [];
  private flashes: { start: number; pre: number; post: number; grew: boolean; size: number }[] = [];
  private changedTotal = 0;
  private learnedMoments = 0;
  private moments = 0;
  private hover: { x: number; y: number } | null = null;
  private history: (t: number) => Frame | undefined = () => undefined;
  private robotIndex = 0;
  frameMs = 0;
  frames = 0;

  constructor(private canvas: HTMLCanvasElement) {
    this.c = canvas.getContext("2d")!;
    canvas.addEventListener("mousemove", (e) => {
      const r = canvas.getBoundingClientRect();
      this.hover = { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H - OY };
    });
    canvas.addEventListener("mouseleave", () => (this.hover = null));
  }

  setHistory(fn: (t: number) => Frame | undefined, robotIndex: number) { this.history = fn; this.robotIndex = robotIndex; }

  setAnatomy(an: Anatomy, spec: Spec) {
    this.an = an; this.spec = spec; this.replay = null; this.last = null; this.wash = []; this.flashes = [];
    this.changedTotal = 0; this.learnedMoments = 0; this.moments = 0;
    this.popNames = an.populations.map((p) => p.name);
    this.popOf = new Int16Array(an.neurons).fill(-1);
    an.populations.forEach((p, k) => p.index.forEach((i) => (this.popOf[i] = k)));
    this.act = new Float32Array(an.neurons);
    this.layout(an.populations);
  }

  // a side view: front (prefrontal) on the left, the senses at the back on the right, the motor
  // strip on top, the deep nuclei (the actor's choice, dopamine) below, the hippocampus low
  private layout(pops: Anatomy["populations"]) {
    const R = this.regions; R.clear();
    const mods = pops.filter((p) => p.name.startsWith("module_")).map((p) => p.name).sort();
    const cortex = [...mods, "association"];
    const put = (key: string, cx: number, cy: number, rx: number, ry: number) => {
      const [title, role, hue] = roleOf(key);
      R.set(key, { key, title, role, cx, cy, rx, ry, hue });
    };
    put("prefrontal", 255, 255, 100, 92);
    put("motor", 480, 92, 165, 40);
    put("sensory", 905, 265, 92, 112);
    cortex.forEach((k, i) => {
      const f = cortex.length === 1 ? 0.5 : i / (cortex.length - 1);
      put(k, 765 - f * 265, 245 + (i % 2) * 26, 92 - f * 10, 74);
    });
    if (pops.some((p) => p.name === "recall")) put("recall", 700, 410, 118, 32);
    if (pops.some((p) => p.name === "next")) put("next", 700, 452, 88, 16);
    this.pos = new Float32Array(this.an!.neurons * 2);
    for (const p of pops) {
      const r = R.get(p.name); if (!r) continue;
      if (p.name === "motor" && this.spec) { // one cluster per motor slot, in slot order
        let k = 0; const slots = this.spec.slots; const span = (2 * r.rx) / slots.length;
        slots.forEach((size, s) => {
          for (let j = 0; j < size; j++, k++) {
            const i = p.index[k]; if (i === undefined) continue;
            this.pos[2 * i] = r.cx - r.rx + span * (s + 0.5) + (j - (size - 1) / 2) * Math.min(13, span / (size + 1));
            this.pos[2 * i + 1] = r.cy + 6 * Math.sin(s * 1.7);
          }
        });
        continue;
      }
      const n = p.index.length;
      for (let k = 0; k < n; k++) { // a sunflower inside the region's ellipse
        const rr = Math.sqrt((k + 0.5) / n), th = k * 2.39996;
        this.pos[2 * p.index[k]] = r.cx + Math.cos(th) * rr * r.rx * 0.92;
        this.pos[2 * p.index[k] + 1] = r.cy + Math.sin(th) * rr * r.ry * 0.88;
      }
    }
  }

  push(ins: Inspect) {
    this.last = ins; this.moments++;
    if (ins.state) this.act.set(ins.state.slice(0, this.act.length));
    if (ins.trajectory) {
      this.replay = { frames: decodeQ(ins.trajectory.q, ins.trajectory.neurons), sweeps: ins.trajectory.sweeps, started: performance.now(), t: ins.t };
    }
    if (ins.rpe !== null && Math.abs(ins.rpe) > 0.02) this.wash.push({ start: performance.now(), value: ins.rpe });
    if (this.wash.length > 8) this.wash.shift();
    const p = ins.plasticity;
    if (p.changed) {
      this.changedTotal += p.changed; this.learnedMoments++;
      const now = performance.now(); const m = Math.max(1e-9, ...p.delta.map(Math.abs));
      p.top.slice(0, 24).forEach((_, k) => this.flashes.push({
        start: now, pre: p.pre[k], post: p.post[k], size: Math.abs(p.delta[k]) / m,
        grew: Math.abs(p.w[k]) >= Math.abs(p.w[k] - p.delta[k]),
      }));
      if (this.flashes.length > 72) this.flashes.splice(0, this.flashes.length - 72);
    }
  }

  draw(now: number) {
    const t0 = performance.now();
    const c = this.c; const an = this.an;
    c.setTransform(this.canvas.width / W, 0, 0, this.canvas.height / H, 0, 0);
    c.globalCompositeOperation = "source-over";
    c.fillStyle = "#070a12"; c.fillRect(0, 0, W, H);
    if (!an || !this.last) {
      c.fillStyle = "#8f98a9"; c.font = "14px Inter, system-ui, sans-serif";
      c.fillText(an ? "waiting for this brain's next moment…" : "reading the brain's anatomy…", 24, 36);
      this.tick(t0); return;
    }
    const ins = this.last;
    const aroused = ins.arousal.mode === "aroused";
    const glow = aroused ? 1.0 : 0.62;
    // the settle replay: a recorded trajectory plays over 700 ms, then rests on the settled state
    let act: Float32Array = this.act; this.sweepLabel = `moment ${ins.t} · settled in ${ins.sweeps ?? "?"} sweeps`;
    if (this.replay) {
      const u = (now - this.replay.started) / 700;
      if (u < 1.25) {
        const k = Math.min(this.replay.frames.length - 1, Math.floor(Math.max(0, u) * this.replay.frames.length));
        act = this.replay.frames[k];
        this.sweepLabel = `moment ${this.replay.t} · settling: sweep ${this.replay.sweeps[k]} of ${this.replay.sweeps[this.replay.sweeps.length - 1]}`;
      }
    }
    c.translate(0, OY);
    this.silhouette(c, glow);
    const DA = { x: 545, y: 470 };
    for (const w of this.wash) { // the critic's prediction error, spreading from the midbrain
      const age = (now - w.start) / 900; if (age > 1) continue;
      const a = Math.min(1, Math.abs(w.value) / 0.4) * (1 - age) * 0.55;
      const rad = 90 + age * 520;
      const g = c.createRadialGradient(DA.x, DA.y, 10, DA.x, DA.y, rad);
      const col = w.value > 0 ? "255,196,64" : "70,140,255";
      g.addColorStop(0, `rgba(${col},${a})`); g.addColorStop(0.6, `rgba(${col},${a * 0.35})`); g.addColorStop(1, `rgba(${col},0)`);
      c.fillStyle = g; c.fillRect(0, 0, W, H);
    }
    this.wash = this.wash.filter((w) => now - w.start < 900);
    c.globalCompositeOperation = "lighter";
    for (const tr of an.tracts) { // fibre tracts
      const rp = this.regions.get(tr.pre), rq = this.regions.get(tr.post);
      for (let k = 0; k < tr.from.length; k++) {
        const i = tr.from[k], j = tr.to[k], w = tr.w[k];
        const msg = Math.abs(w * Math.max(0, act[i])); if (msg < 0.01) continue;
        const x0 = this.pos[2 * i], y0 = this.pos[2 * i + 1], x1 = this.pos[2 * j], y1 = this.pos[2 * j + 1];
        const mx = rp && rq ? (rp.cx + rq.cx) / 2 : (x0 + x1) / 2, my = rp && rq ? (rp.cy + rq.cy) / 2 - 38 : (y0 + y1) / 2;
        const a = Math.min(0.6, msg * 0.5) * glow;
        c.strokeStyle = w > 0 ? `rgba(255,150,70,${a})` : `rgba(90,170,255,${a})`;
        c.lineWidth = 0.6 + Math.min(2.2, msg * 2.5);
        c.beginPath(); c.moveTo(x0, y0); c.quadraticCurveTo(mx, my, x1, y1); c.stroke();
      }
    }
    for (const f of this.flashes) { // plasticity
      const age = (now - f.start) / 1100; if (age > 1) continue;
      c.strokeStyle = `rgba(255,214,90,${(1 - age) * (0.15 + 0.5 * f.size)})`;
      c.lineWidth = (f.grew ? 2.2 : 0.8) * (1 - age * 0.5);
      this.flashCurve(c, f.pre, f.post);
    }
    this.flashes = this.flashes.filter((f) => now - f.start < 1100);
    for (let i = 0; i < an.neurons; i++) { // neurons
      const p = this.popOf[i]; const r = p >= 0 ? this.regions.get(this.popNames[p]) : undefined; if (!r) continue;
      const v = Math.max(0, Math.min(1, act[i]));
      const x = this.pos[2 * i], y = this.pos[2 * i + 1], rad = 1.6 + v * 4.2;
      c.fillStyle = hexA(r.hue, (0.18 + 0.82 * v) * glow);
      c.beginPath(); c.arc(x, y, rad, 0, 6.2832); c.fill();
      if (v > 0.55) { c.fillStyle = hexA(r.hue, 0.16 * v * glow); c.beginPath(); c.arc(x, y, rad * 3, 0, 6.2832); c.fill(); }
    }
    c.globalCompositeOperation = "source-over";
    this.labels(c, act, glow);
    this.deepNuclei(c, ins, DA);
    this.hippocampus(c, ins);
    c.setTransform(this.canvas.width / W, 0, 0, this.canvas.height / H, 0, 0);
    this.hud(c, ins, aroused);
    c.translate(0, OY);
    this.tooltip(c, act);
    this.tick(t0);
  }

  private flashCurve(c: CanvasRenderingContext2D, i: number, j: number) {
    const x0 = this.pos[2 * i], y0 = this.pos[2 * i + 1], x1 = this.pos[2 * j], y1 = this.pos[2 * j + 1];
    c.beginPath(); c.moveTo(x0, y0); c.quadraticCurveTo((x0 + x1) / 2, (y0 + y1) / 2 - 28, x1, y1); c.stroke();
  }

  private tick(t0: number) {
    const ms = performance.now() - t0;
    this.frameMs = this.frames ? 0.9 * this.frameMs + 0.1 * ms : ms; this.frames++;
  }

  private silhouette(c: CanvasRenderingContext2D, glow: number) {
    c.save();
    c.strokeStyle = `rgba(120,140,190,${0.22 + 0.12 * glow})`; c.lineWidth = 1.5;
    c.fillStyle = "rgba(30,38,60,0.35)";
    c.beginPath(); // the cerebrum
    c.moveTo(140, 300);
    c.bezierCurveTo(120, 120, 380, 40, 620, 60);
    c.bezierCurveTo(900, 70, 1060, 190, 1030, 330);
    c.bezierCurveTo(1010, 420, 900, 440, 820, 430);
    c.bezierCurveTo(760, 500, 620, 500, 560, 445);
    c.bezierCurveTo(430, 470, 250, 450, 170, 380);
    c.closePath(); c.fill(); c.stroke();
    c.beginPath(); c.ellipse(935, 445, 85, 45, -0.2, 0, 6.2832); c.stroke(); // the cerebellum
    c.beginPath(); c.moveTo(585, 470); c.bezierCurveTo(592, 520, 600, 545, 610, 560);
    c.moveTo(652, 470); c.bezierCurveTo(656, 520, 660, 545, 668, 560); c.stroke(); // the brainstem
    c.restore();
  }

  private labels(c: CanvasRenderingContext2D, act: Float32Array, glow: number) {
    c.font = "600 12px Inter, system-ui, sans-serif"; c.textAlign = "center";
    c.shadowColor = "rgba(5,8,14,0.95)"; c.shadowBlur = 6;
    for (const r of this.regions.values()) {
      if (r.key === "next") continue;
      c.fillStyle = hexA(r.hue, 0.55 + 0.35 * glow);
      c.fillText(r.title.toUpperCase(), r.cx, r.key === "motor" ? r.cy - r.ry - 30 : r.cy - r.ry - 8);
    }
    const spec = this.spec, an = this.an!, mr = this.regions.get("motor");
    if (spec && mr) { // every motor's group and the command its strongest neuron gives
      let k = 0; c.font = "10px Inter, system-ui, sans-serif";
      spec.slots.forEach((size, s) => {
        const idx = an.motor.slice(k, k + size); k += size;
        let best = 0; idx.forEach((i, j) => { if (act[i] > act[idx[best]]) best = j; });
        const x = mr.cx - mr.rx + ((2 * mr.rx) / spec.slots.length) * (s + 0.5);
        const label = (spec.motors[s]?.label || `motor ${s}`).replace(/ [+-]?\d+°$/, "");
        const cmd = size === 3 ? ["back", "hold", "fwd"][best] : size === 2 ? ["off", "on"][best] : String(best);
        const dy = s % 2 ? 14 : 0; // alternate rows so neighbouring motors' labels never collide
        c.fillStyle = "rgba(255,200,120,0.9)"; c.fillText(cmd, x, mr.cy - 22 - dy);
        c.fillStyle = "rgba(200,205,220,0.6)"; c.fillText(label.replace(" arm", ""), x, mr.cy + 28 + dy);
      });
    }
    c.textAlign = "left"; c.shadowBlur = 0;
  }

  private deepNuclei(c: CanvasRenderingContext2D, ins: Inspect, DA: { x: number; y: number }) {
    const bg = { x: 470, y: 365 }; const sampling = ins.arousal.mode === "aroused";
    c.fillStyle = sampling ? "rgba(255,179,71,0.85)" : "rgba(120,140,190,0.45)";
    c.beginPath(); c.ellipse(bg.x, bg.y, 44, 22, 0, 0, 6.2832); c.fill();
    c.fillStyle = "#0b0f19"; c.font = "600 10px Inter, system-ui, sans-serif"; c.textAlign = "center";
    c.fillText(sampling ? "SAMPLING" : "GREEDY", bg.x, bg.y + 4);
    c.fillStyle = "rgba(200,205,220,0.7)"; c.fillText("basal ganglia · the actor's choice", bg.x, bg.y + 38);
    const v = ins.rpe ?? 0, a = Math.min(1, Math.abs(v) / 0.4);
    c.fillStyle = v >= 0 ? `rgba(255,196,64,${0.3 + 0.7 * a})` : `rgba(70,140,255,${0.3 + 0.7 * a})`;
    c.beginPath(); c.arc(DA.x, DA.y, 13 + 6 * a, 0, 6.2832); c.fill();
    c.fillStyle = "rgba(200,205,220,0.7)";
    c.fillText(ins.rpe === null ? "dopamine · the critic's prediction error" : `dopamine · the critic's prediction error ${v >= 0 ? "+" : ""}${v.toFixed(3)}`, DA.x, DA.y + 34);
    c.textAlign = "left";
  }

  private hippocampus(c: CanvasRenderingContext2D, ins: Inspect) {
    const r = this.regions.get("recall"); if (!r || !ins.recall) return;
    const rc = ins.recall; const cells = Math.min(24, rc.stored);
    const x0 = r.cx - r.rx, y = r.cy + r.ry + 30, step = (2 * r.rx) / Math.max(1, cells);
    const reads = new Map<number, number>(rc.reads.map(([, age, wgt]) => [age, wgt]));
    c.font = "10px Inter, system-ui, sans-serif";
    for (let k = 0; k < cells; k++) { // the newest stored moments, oldest on the left; lit when read
      const wgt = reads.get(cells - 1 - k); const x = x0 + step * (k + 0.5);
      c.fillStyle = wgt !== undefined ? `rgba(125,255,176,${0.35 + 0.65 * wgt})` : "rgba(125,255,176,0.12)";
      c.beginPath(); c.arc(x, y, 4.5, 0, 6.2832); c.fill();
    }
    const top = rc.reads[0];
    if (top) { // a thread from the strongest read to the moment it stored, and that moment's ring
      const [, age, wgt] = top; const then = this.last!.t - age; const f = this.history(then);
      const k = cells - 1 - age; const x = k >= 0 ? x0 + step * (k + 0.5) : x0;
      const bx = 1085, by = 470;
      c.strokeStyle = `rgba(125,255,176,${0.3 + 0.6 * wgt})`; c.lineWidth = 1.2;
      c.beginPath(); c.moveTo(x, y); c.quadraticCurveTo((x + bx) / 2, y + 60, bx - 52, by); c.stroke();
      this.thumb(c, f, bx, by, 50);
      c.fillStyle = "rgba(200,205,220,0.75)"; c.textAlign = "center";
      c.fillText(f ? `reads moment ${then} (weight ${wgt.toFixed(2)})` : `reads moment ${then}, before this fight (${wgt.toFixed(2)})`, bx, by + 66);
      c.textAlign = "left";
    }
    c.fillStyle = "rgba(200,205,220,0.6)";
    c.fillText(`recall memory: ${rc.stored} of ${rc.capacity} moments stored`, x0, y + 20);
  }

  private thumb(c: CanvasRenderingContext2D, f: Frame | undefined, cx: number, cy: number, R: number) {
    c.strokeStyle = "rgba(255,122,69,0.6)"; c.lineWidth = 1;
    c.beginPath(); c.arc(cx, cy, R, 0, 6.2832); c.stroke();
    if (!f) return;
    c.beginPath(); c.setLineDash([3, 3]); c.arc(cx, cy, (R * f.zone) / 10, 0, 6.2832); c.stroke(); c.setLineDash([]);
    f.robots.forEach((row, i) => {
      if (row[4] === 9) return;
      c.fillStyle = i === this.robotIndex ? "#ffffff" : "rgba(160,170,190,0.8)";
      c.beginPath(); c.arc(cx + (row[0] / 10) * R, cy - (row[1] / 10) * R, i === this.robotIndex ? 3.5 : 2.5, 0, 6.2832); c.fill();
    });
  }

  private hud(c: CanvasRenderingContext2D, ins: Inspect, aroused: boolean) {
    // the status band: arousal on the left, the settle in the middle, plasticity on the right
    c.fillStyle = "rgba(14,18,30,0.9)"; c.fillRect(0, 0, W, OY - 8);
    c.font = "600 14px Inter, system-ui, sans-serif";
    c.fillStyle = aroused ? "#ffb347" : "#4fa3ff";
    c.fillText(aroused ? "AROUSED · learning on" : "CALM · routine, no learning", 20, 28);
    c.font = "12px Inter, system-ui, sans-serif"; c.fillStyle = "rgba(220,225,235,0.8)";
    c.fillText(`arousal level ${ins.arousal.level.toFixed(2)} · want ${ins.arousal.want.toFixed(2)}`, 20, 50);
    c.fillText(`${ins.settles} settles this moment, ${ins.learning_settles} of them learning`, 20, 70);
    const x0 = 360, y0 = 14, w = 280, h = 42; // the act's movement per sweep, log scale
    c.fillStyle = "rgba(220,225,235,0.85)"; c.fillText(this.sweepLabel, x0 + w + 14, y0 + 26);
    c.strokeStyle = "rgba(120,140,190,0.4)"; c.lineWidth = 1; c.strokeRect(x0, y0, w, h);
    const mv = ins.movement || [];
    if (mv.length) {
      const ly = (v: number) => y0 + h - ((Math.log10(Math.max(v, 1e-4)) + 4) / 4) * h;
      c.strokeStyle = "#9b8cff"; c.lineWidth = 1.5; c.beginPath();
      mv.forEach((v, k) => { const x = x0 + (k / Math.max(1, mv.length - 1)) * w; k ? c.lineTo(x, ly(v)) : c.moveTo(x, ly(v)); });
      c.stroke();
    }
    c.fillStyle = "rgba(200,205,220,0.5)"; c.font = "10px Inter, system-ui, sans-serif";
    c.fillText("the act's movement per sweep (log)", x0, y0 + h + 17);
    const p = ins.plasticity;
    c.font = "12px Inter, system-ui, sans-serif"; c.fillStyle = "rgba(255,214,90,0.95)";
    c.fillText(`${p.changed.toLocaleString()} synapses changed this moment`, 960, 28);
    c.fillStyle = "rgba(220,225,235,0.75)";
    c.fillText(`${this.changedTotal.toLocaleString()} changes in ${this.learnedMoments} of ${this.moments} moments watched`, 960, 50);
    c.fillStyle = "rgba(200,205,220,0.5)"; c.font = "10px Inter, system-ui, sans-serif";
    c.fillText(`${this.an!.neurons} neurons · ${this.an!.synapses.toLocaleString()} synapses · draw ${this.frameMs.toFixed(1)} ms`, 960, 70);
  }

  private tooltip(c: CanvasRenderingContext2D, act: Float32Array) {
    const h = this.hover; const an = this.an; if (!h || !an) return;
    let best = -1, bd = 64;
    for (let i = 0; i < an.neurons; i++) {
      const dx = this.pos[2 * i] - h.x, dy = this.pos[2 * i + 1] - h.y, d = dx * dx + dy * dy;
      if (d < bd && this.popOf[i] >= 0) { bd = d; best = i; }
    }
    let text = "";
    if (best >= 0) {
      const pop = this.popNames[this.popOf[best]]; const r = this.regions.get(pop);
      const si = an.sensory.indexOf(best), mi = an.motor.indexOf(best);
      const what = si >= 0 && this.spec ? `sense: ${this.spec.inputs[si]}` : mi >= 0 ? "a motor neuron" : pop;
      text = `${what} · activation ${act[best].toFixed(2)} · ${r ? r.role : pop}`;
    } else {
      for (const r of this.regions.values()) if (((h.x - r.cx) / r.rx) ** 2 + ((h.y - r.cy) / r.ry) ** 2 < 1) text = `${r.title} (${r.key}): ${r.role}`;
    }
    if (!text) return;
    c.font = "12px Inter, system-ui, sans-serif";
    const w = Math.min(W - 20, c.measureText(text).width + 16), x = Math.max(10, Math.min(W - w - 10, h.x + 12)), y = Math.max(10, h.y - 30);
    c.fillStyle = "rgba(10,14,24,0.92)"; c.fillRect(x, y, w, 22);
    c.fillStyle = "#e8ebf2"; c.fillText(text, x + 8, y + 15);
  }
}

export const BRAIN_W = W, BRAIN_H = H;
