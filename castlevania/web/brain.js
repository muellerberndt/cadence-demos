// The brain, drawn as an animal brain seen from the left side: front (prefrontal) on the left,
// the visual cortex at the back on the right. Every mark is read from one decision's real state
// (simon/player.py snapshot): the eye's maps, the settle sweep by sweep, the projections'
// strengths (|weight x presynaptic activation|), the strongest synapses, the motor slots and
// their choice probabilities, and the recall memory's slots with the moments they hold. Where an
// animal region is named, the label says which Cadence population plays that role.
(function () {
  const W = 1000, H = 900;
  const PAL = { bg: "#0b090e", outline: "rgba(190,170,210,0.16)", gyri: "rgba(190,170,210,0.06)",
    text: "#e9e3ee", dim: "#9c90a8", warm: [255, 150, 70], cool: [80, 170, 255], gold: [255, 205, 90],
    violet: [150, 110, 200] };

  // where each population sits (a stylized lateral view), and how its neurons are laid out
  const REGIONS = {
    prefrontal: { cx: 150, cy: 475, w: 175, h: 100, cols: 16, rows: 8, rot: -0.55,
      label: "prefrontal", role: "prefrontal region (128): carries the working trace of recent moments" },
    association: { cx: 590, cy: 195, w: 250, h: 105, cols: 16, rows: 8, rot: 0.05,
      label: "association", role: "association region (128): the hub every other region reads and writes" },
    module_0: { cx: 650, cy: 450, w: 220, h: 180, cols: 16, rows: 16, rot: 0.16,
      label: "module 0", role: "first hidden module (256): reads the visual and body maps" },
  };
  const MOTOR = { x: 318, top: 150, label: "motor strip", role: "motor neurons (10): one per choice in four slots",
    groups: [["horizontal", ["left", "none", "right"]], ["vertical", ["up", "none", "down"]], ["whip", ["no", "B"]], ["jump", ["no", "A"]]] };
  const V1 = { x0: 790, y0: 250, cell: 5.6, gap: 12,
    maps: [["scene", "scene"], ["motion", "motion"], ["ahead", "fovea ahead"], ["behind", "fovea behind"]],
    role: "sensory population (827): the eye's readings, clamped each decision; drawn where an animal's visual cortex sits" };
  const S1 = { x: 452, y: 300, role: "sensory population: the body readings and one-hot stage, block, body state and floor (drawn as the body-sense strip)" };
  const THAL = { x: 560, y: 560, r: 30, role: "where the eye's 827 readings enter: drawn where an animal's thalamus relays vision; its glow is the mean input" };
  const STRI = { x: 415, y: 560, role: "the motor choice: a softmax over each slot's motor neurons (plays the role of the striatum)" };
  const HIPPO = { x0: 330, x1: 760, y: 690, sag: 34, role: "recall memory: one cell per slot (a moment of this game); gold = attended by this decision's read" };
  const VTA = { x: 560, y: 850, role: "dopamine: silent. The brain plays frozen; no outcome reaches it (plays the role of the midbrain dopamine nucleus)" };

  function rgb(c, a) { return `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`; }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function b64bytes(s) { const r = atob(s), out = new Uint8Array(r.length); for (let i = 0; i < r.length; i++) out[i] = r.charCodeAt(i); return out; }

  function gridPositions(R) {
    const pts = [], c = Math.cos(R.rot), s = Math.sin(R.rot);
    for (let i = 0; i < R.rows; i++) for (let j = 0; j < R.cols; j++) {
      const u = (j + 0.5) / R.cols - 0.5, v = (i + 0.5) / R.rows - 0.5;
      // a gentle bulge: cortex curves
      const bx = u * R.w, by = v * R.h + Math.sin((u + 0.5) * Math.PI) * -R.h * 0.12;
      pts.push([R.cx + bx * c - by * s, R.cy + bx * s + by * c]);
    }
    return pts;
  }
  const POS = {};
  for (const [k, R] of Object.entries(REGIONS)) POS[k] = gridPositions(R);
  POS.motor = [];
  { let y = MOTOR.top; for (const [, labels] of MOTOR.groups) { for (let j = 0; j < labels.length; j++) { POS.motor.push([MOTOR.x, y]); y += 22; } y += 16; } }
  const V1POS = {}; // map name -> [x0, y0]
  V1.maps.forEach(([k], i) => { V1POS[k] = [V1.x0 + (i % 2) * (16 * V1.cell + V1.gap), V1.y0 + Math.floor(i / 2) * (12 * V1.cell + 30)]; });
  const SLICE = { scene: [0, 192], motion: [192, 384], ahead: [384, 576], body: [576, 588], behind: [588, 780] };
  function sensoryPos(i) {
    for (const k of ["scene", "motion", "ahead", "behind"]) {
      const [a, b] = SLICE[k];
      if (i >= a && i < b) { const j = i - a, [x0, y0] = V1POS[k]; return [x0 + ((j % 16) + 0.5) * V1.cell, y0 + (Math.floor(j / 16) + 0.5) * V1.cell]; }
    }
    return [S1.x + 8, S1.y + ((i % 60) * 2.2)];
  }
  function hippoPos(k, n) {
    const t = n > 1 ? k / (n - 1) : 0.5;
    return [HIPPO.x0 + (HIPPO.x1 - HIPPO.x0) * t, HIPPO.y + Math.sin(t * Math.PI) * HIPPO.sag - 18 * Math.sin(t * Math.PI * 2)];
  }
  const ANCHOR = {
    sensory: [V1.x0 + 40, V1.y0 + 110], module_0: [REGIONS.module_0.cx, REGIONS.module_0.cy],
    association: [REGIONS.association.cx, REGIONS.association.cy], prefrontal: [REGIONS.prefrontal.cx, REGIONS.prefrontal.cy],
    motor: [MOTOR.x, MOTOR.top + 120], recall: [HIPPO.x0 + 80, HIPPO.y + 10], recall_1: [HIPPO.x0 + 160, HIPPO.y + 20],
    next: [HIPPO.x1 - 160, HIPPO.y + 20], next_1: [HIPPO.x1 - 80, HIPPO.y + 10],
  };
  function neuronPos(pop, i) {
    if (POS[pop]) return POS[pop][i] || ANCHOR[pop];
    if (pop === "sensory") return sensoryPos(i);
    return ANCHOR[pop] || [W / 2, H / 2];
  }

  // the silhouette: a lateral view of a cerebrum, cerebellum and brainstem (frame only)
  function silhouette(ctx) {
    ctx.save();
    ctx.lineWidth = 2; ctx.strokeStyle = PAL.outline;
    ctx.beginPath();
    ctx.moveTo(90, 430);
    ctx.bezierCurveTo(60, 250, 200, 90, 420, 75);
    ctx.bezierCurveTo(640, 55, 900, 120, 965, 330);
    ctx.bezierCurveTo(990, 430, 960, 540, 880, 590);
    ctx.bezierCurveTo(820, 630, 760, 640, 700, 625);
    ctx.bezierCurveTo(600, 660, 470, 655, 360, 620);
    ctx.bezierCurveTo(250, 640, 140, 560, 90, 430);
    ctx.stroke();
    // cerebellum and brainstem
    ctx.beginPath(); ctx.ellipse(835, 655, 105, 62, -0.15, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(640, 640); ctx.bezierCurveTo(650, 720, 620, 800, 600, 870); ctx.moveTo(700, 640); ctx.bezierCurveTo(710, 720, 690, 800, 670, 870); ctx.stroke();
    // a few sulci
    ctx.strokeStyle = PAL.gyri; ctx.lineWidth = 1.5;
    const sulci = [[[430, 80], [400, 250], [440, 430]], [[300, 120], [330, 300], [270, 470]], [[600, 70], [610, 200], [560, 330]], [[760, 110], [740, 260], [800, 400]], [[180, 420], [400, 470], [620, 520]]];
    for (const [a, b, c] of sulci) { ctx.beginPath(); ctx.moveTo(...a); ctx.quadraticCurveTo(...b, ...c); ctx.stroke(); }
    ctx.restore();
  }

  function tractPath(a, b, bend) {
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, dx = b[0] - a[0], dy = b[1] - a[1];
    return [a, [mx - dy * bend, my + dx * bend], b];
  }
  function quadAt(p, t) {
    const [a, c, b] = p, u = 1 - t;
    return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
  }
  const TRACTS = [
    ["sensory>module_0", "sensory", "module_0", 0.12], ["module_0>association", "module_0", "association", 0.18],
    ["association>module_0", "association", "module_0", -0.18], ["prefrontal>association", "prefrontal", "association", 0.15],
    ["association>motor", "association", "motor", 0.12], ["motor>association", "motor", "association", -0.14],
    ["recall>association", "recall", "association", 0.10], ["recall_1>association", "recall_1", "association", 0.06],
    ["next>association", "next", "association", -0.06], ["next_1>association", "next_1", "association", -0.10],
  ];

  class BrainView {
    constructor(canvas, opts = {}) {
      this.canvas = canvas; this.ctx = canvas.getContext("2d");
      this.snap = null; this.cache = null; this.hover = null; this.thumbs = new Map(); this.opts = opts;
      this.regionsForHover = [];
      if (!opts.offline) canvas.addEventListener("mousemove", (e) => this.onMove(e));
      if (!opts.offline) canvas.addEventListener("mouseleave", () => { this.hover = null; });
    }
    setSnap(snap) {
      if (!snap || !snap.trajectory) return;
      this.snap = snap;
      const t = snap.trajectory, regions = {};
      for (const [k, list] of Object.entries(t.regions)) regions[k] = list.map(b64bytes);
      const memory = {};
      for (const [k, s] of Object.entries(t.memory || {})) memory[k] = b64bytes(s);
      const maxB = Math.max(1e-6, ...Object.values(snap.bundles || {}).map(([p, n]) => p + n));
      const maxT = Math.max(1e-6, ...(snap.threads || []).map((r) => Math.abs(r[4])));
      this.cache = { regions, memory, sweeps: t.sweeps, change: t.change, maxB, maxT };
      for (const top of (snap.memory && snap.memory.top) || []) {
        if (top.thumb && !this.thumbs.has(top.decision)) {
          const img = new Image(); img.src = "data:image/png;base64," + top.thumb; this.thumbs.set(top.decision, img);
        }
      }
      if (this.thumbs.size > 200) { const keys = [...this.thumbs.keys()].slice(0, this.thumbs.size - 200); keys.forEach((k) => this.thumbs.delete(k)); }
    }
    onMove(e) {
      const r = this.canvas.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width * W, y = (e.clientY - r.top) / r.height * H;
      this.hover = null;
      for (const h of this.regionsForHover) if (x >= h[0] && x <= h[2] && y >= h[1] && y <= h[3]) { this.hover = { x, y, text: h[4] }; break; }
    }
    // phase: 0..1 through the settle (sweep = phase * sweeps); clock: ms, for the pulses
    draw(phase = 1, clock = 0) {
      const ctx = this.ctx, cw = this.canvas.width, ch = this.canvas.height;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = PAL.bg; ctx.fillRect(0, 0, cw, ch);
      const s = Math.min(cw / W, ch / H);
      ctx.setTransform(s, 0, 0, s, (cw - W * s) / 2, (ch - H * s) / 2);
      this.regionsForHover = [];
      silhouette(ctx);
      const snap = this.snap, c = this.cache;
      if (!snap || !c) { ctx.fillStyle = PAL.dim; ctx.font = "22px system-ui"; ctx.fillText("waiting for the first decision", 360, 450); return; }
      const sweep = Math.min(c.sweeps, Math.max(0, Math.round(phase * c.sweeps)));
      const settled = sweep >= c.sweeps;
      // a recorded settle may keep every n-th sweep: pick the kept state nearest this point of the settle
      const at = (n) => Math.min(n - 1, Math.round((sweep / Math.max(1, c.sweeps)) * (n - 1)));
      const span = {};
      for (const pop of Object.keys(c.regions)) { const last = c.regions[pop][c.regions[pop].length - 1]; let lo = 255, hi = 0; for (const v of last) { lo = Math.min(lo, v); hi = Math.max(hi, v); } span[pop] = [lo, Math.max(hi, lo + 8)]; }
      // each region coloured over its own range at this decision (its settled minimum to maximum)
      const act = (pop, i) => { const a = c.regions[pop]; if (!a) return 0; const [lo, hi] = span[pop]; return Math.max(0, Math.min(1, (a[at(a.length)][i] - lo) / (hi - lo))); };
      // activity per region at this sweep (for the pulses along the tracts)
      const level = {};
      for (const pop of Object.keys(c.regions)) { const a = c.regions[pop][at(c.regions[pop].length)]; let m = 0; for (const v of a) m += v; level[pop] = m / a.length / 255; }
      level.sensory = Math.min(1, snap.drive * 2.2); ["recall", "recall_1", "next", "next_1"].forEach((k) => { level[k] = 0.5; });

      // 1. tracts (bundled projections): warm = excitatory flow, cool = inhibitory flow
      ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
      for (const [key, a, b, bend] of TRACTS) {
        const flow = (snap.bundles || {})[key]; if (!flow) continue;
        const p = tractPath(ANCHOR[a], ANCHOR[b], bend);
        const [pos, neg] = flow, total = (pos + neg) / c.maxB;
        const width = 1.5 + 10 * Math.sqrt(total);
        for (const [amount, col, off] of [[pos, PAL.warm, -0.35], [neg, PAL.cool, 0.35]]) {
          if (amount <= 0) continue;
          const share = amount / (pos + neg);
          ctx.strokeStyle = rgb(col, 0.10 + 0.45 * Math.sqrt(amount / c.maxB));
          ctx.lineWidth = Math.max(1, width * share);
          ctx.beginPath();
          const q = p.map(([x, y]) => [x + off * width * 0.5, y + off * width * 0.5]);
          ctx.moveTo(...q[0]); ctx.quadraticCurveTo(...q[1], ...q[2]); ctx.stroke();
        }
        // pulses: messages in flight, faster and brighter while the brain is still moving
        const n = 3, moving = settled ? 0.25 : 1;
        for (let k = 0; k < n; k++) {
          const t = ((clock / (settled ? 2400 : 700)) + k / n + (bend + 1) * 0.37) % 1;
          const [x, y] = quadAt(p, t);
          const g = ctx.createRadialGradient(x, y, 0, x, y, 9 + width * 0.6);
          g.addColorStop(0, rgb(pos >= neg ? PAL.warm : PAL.cool, 0.55 * moving * Math.min(1, 0.3 + level[a])));
          g.addColorStop(1, rgb(PAL.warm, 0));
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 9 + width * 0.6, 0, Math.PI * 2); ctx.fill();
        }
      }
      // 2. the strongest synapses: thin threads between the actual neurons
      for (const [pa, ia, pz, iz, v] of snap.threads || []) {
        const A = neuronPos(pa, ia), Z = neuronPos(pz, iz), m = Math.abs(v) / c.maxT;
        if (m < 0.08) continue;
        ctx.strokeStyle = rgb(v > 0 ? PAL.warm : PAL.cool, 0.06 + 0.4 * m);
        ctx.lineWidth = 0.6 + 1.6 * m;
        ctx.beginPath(); const p = tractPath(A, Z, 0.08); ctx.moveTo(...p[0]); ctx.quadraticCurveTo(...p[1], ...p[2]); ctx.stroke();
      }
      ctx.restore();

      // 3. the visual cortex: the eye's four maps (its input neurons)
      const eye = snap.eye;
      for (const [k, label] of V1.maps) {
        const [x0, y0] = V1POS[k], vals = eye[k];
        for (let i = 0; i < 12; i++) for (let j = 0; j < 16; j++) {
          const v = vals[i * 16 + j];
          if (k === "motion") { const a = Math.max(-1, Math.min(1, v * 2)); ctx.fillStyle = a >= 0 ? rgb(mix([25, 20, 30], PAL.warm, a), 1) : rgb(mix([25, 20, 30], PAL.cool, -a), 1); }
          else { const t = Math.max(0, Math.min(1, (v + 0.6) / 1.2)); ctx.fillStyle = rgb([20 + 220 * t, 18 + 200 * t, 26 + 205 * t], 1); }
          ctx.fillRect(x0 + j * V1.cell, y0 + i * V1.cell, V1.cell - 0.4, V1.cell - 0.4);
        }
        ctx.fillStyle = PAL.dim; ctx.font = "15px system-ui"; ctx.fillText(label, x0, y0 + 12 * V1.cell + 17);
        this.regionsForHover.push([x0, y0, x0 + 16 * V1.cell, y0 + 12 * V1.cell, V1.role + " — " + label]);
      }
      ctx.fillStyle = PAL.text; ctx.font = "600 17px system-ui"; ctx.fillText("visual cortex", V1.x0, V1.y0 - 12);

      // 4. the body-sense strip: body readings and one-hot readings
      {
        const rows = [["body", eye.body], ["stage", eye.stage], ["block", eye.block], ["state", eye.state], ["floor", eye.floor]];
        let y = S1.y;
        for (const [name, vals] of rows) {
          for (let j = 0; j < vals.length; j++) {
            const t = Math.max(0, Math.min(1, (vals[j] + 0.6) / 1.2));
            ctx.fillStyle = rgb(mix([35, 28, 42], PAL.gold, t), 1);
            ctx.fillRect(S1.x + j * 5.2, y, 4.4, 9);
          }
          ctx.fillStyle = PAL.dim; ctx.font = "12px system-ui"; ctx.fillText(name, S1.x - 46, y + 9);
          y += 15;
        }
        this.regionsForHover.push([S1.x - 50, S1.y, S1.x + 100, y, S1.role]);
      }

      // 5. cortical regions, neuron by neuron, at this sweep
      ctx.save(); ctx.globalCompositeOperation = "lighter";
      for (const [pop, R] of Object.entries(REGIONS)) {
        const pts = POS[pop];
        for (let i = 0; i < pts.length; i++) {
          const v = act(pop, i), [x, y] = pts[i];
          const col = mix([60, 30, 80], PAL.gold, Math.min(1, v * 1.15));
          ctx.fillStyle = rgb(col, 0.4 + 0.6 * v);
          ctx.beginPath(); ctx.arc(x, y, 2.4 + 2.2 * v, 0, Math.PI * 2); ctx.fill();
          if (v > 0.55) { const g = ctx.createRadialGradient(x, y, 0, x, y, 11); g.addColorStop(0, rgb(PAL.gold, 0.35 * v)); g.addColorStop(1, rgb(PAL.gold, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fill(); }
        }
      }
      ctx.restore();
      for (const [pop, R] of Object.entries(REGIONS)) {
        ctx.fillStyle = PAL.text; ctx.font = "600 17px system-ui";
        ctx.fillText(R.label, R.cx - R.w / 2, R.cy - R.h / 2 - 16);
        this.regionsForHover.push([R.cx - R.w / 2, R.cy - R.h / 2, R.cx + R.w / 2, R.cy + R.h / 2, R.role]);
      }

      // 6. the motor strip and the choice (striatum)
      {
        let i = 0;
        ctx.font = "13px system-ui";
        MOTOR.groups.forEach(([name, labels], g) => {
          const probs = (snap.probs || [])[g] || [];
          const chosen = [snap.act[0] + 1, snap.act[1] + 1, snap.act[2], snap.act[3]][g];
          labels.forEach((lab, j) => {
            const [x, y] = POS.motor[i], v = act("motor", i);
            const on = settled && j === chosen;
            ctx.save(); ctx.globalCompositeOperation = "lighter";
            const g2 = ctx.createRadialGradient(x, y, 0, x, y, on ? 20 : 12);
            g2.addColorStop(0, rgb(on ? [255, 90, 90] : PAL.gold, 0.25 + 0.7 * v)); g2.addColorStop(1, rgb(PAL.gold, 0));
            ctx.fillStyle = g2; ctx.beginPath(); ctx.arc(x, y, on ? 20 : 12, 0, Math.PI * 2); ctx.fill(); ctx.restore();
            ctx.fillStyle = on ? "#ff6b6b" : rgb(mix([70, 50, 90], PAL.gold, v), 1);
            ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = on ? PAL.text : PAL.dim; ctx.fillText(lab, x + 13, y + 4);
            if (probs[j] !== undefined) { ctx.fillStyle = rgb(PAL.violet, 0.8); ctx.fillRect(x - 58, y - 3, 40 * probs[j], 6); }
            i++;
          });
          ctx.fillStyle = PAL.dim; ctx.fillText(name, MOTOR.x - 132, POS.motor[i - labels.length][1] + 4);
        });
        ctx.fillStyle = PAL.text; ctx.font = "600 17px system-ui"; ctx.fillText("motor strip", MOTOR.x - 40, MOTOR.top - 24);
        this.regionsForHover.push([MOTOR.x - 120, MOTOR.top - 10, MOTOR.x + 70, POS.motor[9][1] + 10, MOTOR.role + "; the violet bars are each choice's probability (the striatum's softmax)"]);
      }
      // striatum: one ring per slot, its arc the chosen action's probability
      {
        ctx.font = "13px system-ui";
        (snap.probs || []).forEach((p, g) => {
          const x = STRI.x - 45 + (g % 2) * 46, y = STRI.y - 20 + Math.floor(g / 2) * 46;
          const chosen = [snap.act[0] + 1, snap.act[1] + 1, snap.act[2], snap.act[3]][g];
          ctx.strokeStyle = "rgba(150,110,200,0.25)"; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(x, y, 15, 0, Math.PI * 2); ctx.stroke();
          ctx.strokeStyle = settled ? "#ff6b6b" : rgb(PAL.violet, 0.9); ctx.beginPath(); ctx.arc(x, y, 15, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * (p[chosen] || 0)); ctx.stroke();
        });
        ctx.fillStyle = PAL.dim; ctx.fillText("striatum: the choice", STRI.x - 70, STRI.y + 66);
        this.regionsForHover.push([STRI.x - 70, STRI.y - 40, STRI.x + 30, STRI.y + 70, STRI.role]);
      }

      // 7. thalamus: where the eye's readings enter
      {
        const v = Math.min(1, snap.drive * 2.2), m = Math.min(1, snap.motion * 12);
        ctx.save(); ctx.globalCompositeOperation = "lighter";
        const g = ctx.createRadialGradient(THAL.x, THAL.y, 0, THAL.x, THAL.y, THAL.r + 18);
        g.addColorStop(0, rgb(mix(PAL.gold, PAL.warm, m), 0.35 + 0.5 * v)); g.addColorStop(1, rgb(PAL.warm, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(THAL.x, THAL.y, THAL.r + 18, THAL.r + 8, 0, 0, Math.PI * 2); ctx.fill();
        // the optic radiation to the visual cortex (inputs, not synapses)
        ctx.strokeStyle = rgb(PAL.gold, 0.12 + 0.35 * m); ctx.lineWidth = 3; ctx.setLineDash([6, 6]); ctx.lineDashOffset = -clock / 40;
        ctx.beginPath(); ctx.moveTo(THAL.x + 20, THAL.y - 10); ctx.quadraticCurveTo(760, 520, V1.x0 + 10, V1.y0 + 150); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();
        ctx.fillStyle = PAL.dim; ctx.font = "13px system-ui"; ctx.fillText("thalamus: inputs enter", THAL.x - 60, THAL.y + 52);
        this.regionsForHover.push([THAL.x - 50, THAL.y - 40, THAL.x + 50, THAL.y + 55, THAL.role]);
      }

      // 8. hippocampus: the recall memory's slots, the attended ones lit, a thread to the moment held
      const mem = snap.memory || {};
      if (mem.slots) {
        const n = mem.slots, w = mem.weights || [], ages = mem.ages || [];
        ctx.save(); ctx.globalCompositeOperation = "lighter";
        for (let k = 0; k < n; k++) {
          const [x, y] = hippoPos(k, n), a = w[k] || 0, held = (ages[k] ?? -1) >= 0;
          ctx.fillStyle = held ? rgb(mix(PAL.violet, PAL.gold, Math.min(1, a * 3)), 0.35 + 0.65 * Math.min(1, a * 3)) : "rgba(60,50,70,0.5)";
          ctx.beginPath(); ctx.arc(x, y, 2.4 + 6 * Math.min(1, a * 2), 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();
        ctx.fillStyle = PAL.text; ctx.font = "600 17px system-ui"; ctx.fillText("hippocampus: recall memory", HIPPO.x0, HIPPO.y - 30);
        ctx.fillStyle = PAL.dim; ctx.font = "13px system-ui";
        ctx.fillText(`${mem.held} of ${mem.capacity} slots hold moments of this game; ${mem.heads} read heads`, HIPPO.x0, HIPPO.y + 62);
        this.regionsForHover.push([HIPPO.x0, HIPPO.y - 30, HIPPO.x1, HIPPO.y + 50, HIPPO.role]);
        const top = (mem.top || [])[0];
        if (top) {
          const [sx, sy] = hippoPos(top.slot, n), img = this.thumbs.get(top.decision);
          const tx = 120, ty = 760, tw = 120, th = 112;
          ctx.strokeStyle = rgb(PAL.gold, 0.7); ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(sx - 120, ty - 20, tx + tw, ty + th / 2); ctx.stroke();
          if (img && img.complete) { ctx.imageSmoothingEnabled = false; ctx.drawImage(img, tx, ty, tw, th); }
          ctx.strokeStyle = rgb(PAL.gold, 0.8); ctx.strokeRect(tx, ty, tw, th);
          ctx.fillStyle = PAL.text; ctx.font = "13px system-ui";
          ctx.fillText(`read: decision ${top.decision}`, tx, ty - 8);
          ctx.fillStyle = PAL.dim; ctx.fillText(`${top.ago} decisions ago, weight ${top.weight}`, tx, ty + th + 16);
        }
        // what the two heads recall, and what they expect next (the scene part of each region)
        const maps = [["recall", "recalled (head 1)"], ["recall_1", "recalled (head 2)"], ["next", "expected next (1)"], ["next_1", "expected next (2)"]];
        maps.forEach(([k, label], i) => {
          const a = c.memory[k]; if (!a) return;
          const x0 = 290 + i * 98, y0 = 790, cell = 5;
          let lo = 255, hi = 0; for (const v of a) { lo = Math.min(lo, v); hi = Math.max(hi, v); } hi = Math.max(hi, lo + 4);
          for (let r = 0; r < 12; r++) for (let q = 0; q < 16; q++) { const v = (a[r * 16 + q] - lo) / (hi - lo); ctx.fillStyle = rgb([20 + 120 * v, 18 + 160 * v, 30 + 220 * v], 1); ctx.fillRect(x0 + q * cell, y0 + r * cell, cell - 0.4, cell - 0.4); }
          ctx.fillStyle = PAL.dim; ctx.font = "11px system-ui"; ctx.fillText(label, x0, y0 + 12 * cell + 13);
          this.regionsForHover.push([x0, y0, x0 + 16 * cell, y0 + 12 * cell, "the scene part of the recall memory's " + k + " region (827 neurons, one per eye reading), scaled to its own range: what the memory hands the association region"]);
        });
      }

      // 9. neuromodulators and plasticity: shown at their true (idle) state in frozen play
      ctx.fillStyle = "rgba(60,60,90,0.6)"; ctx.beginPath(); ctx.ellipse(VTA.x + 160, VTA.y - 10, 16, 10, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = PAL.dim; ctx.font = "12px system-ui";
      ctx.fillText("dopamine: silent · arousal: off · synapses changed: 0 (frozen play)", VTA.x + 60, VTA.y + 22);
      this.regionsForHover.push([VTA.x + 60, VTA.y - 25, VTA.x + 420, VTA.y + 28, VTA.role]);

      // 10. the settle: sweep, the largest change per sweep falling to the tolerance
      {
        const x0 = 30, y0 = 34, w = 200, h = 44;
        ctx.fillStyle = PAL.text; ctx.font = "600 17px system-ui";
        ctx.fillText(settled ? `settled in ${c.sweeps} sweeps` : `settling: sweep ${sweep} of ${c.sweeps}`, x0, y0);
        const ch2 = c.change || [], lg = (v) => Math.log10(Math.max(v, 1e-6));
        const top = 0, bot = -5;
        ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 1;
        const ty = y0 + 12 + (top - lg(3e-3)) / (top - bot) * h;
        ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x0, ty); ctx.lineTo(x0 + w, ty); ctx.stroke(); ctx.setLineDash([]);
        ctx.strokeStyle = rgb(PAL.gold, 0.9); ctx.lineWidth = 2; ctx.beginPath();
        for (let k = 0; k <= Math.min(sweep, ch2.length - 1); k++) {
          const x = x0 + (k / Math.max(1, ch2.length - 1)) * w, y = y0 + 12 + (top - lg(ch2[k])) / (top - bot) * h;
          if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.fillStyle = PAL.dim; ctx.font = "12px system-ui"; ctx.fillText("largest change per sweep; dashed: tolerance", x0, y0 + h + 30);
      }

      if (this.hover) {
        ctx.font = "15px system-ui";
        const words = this.hover.text.split(" "), lines = []; let line = "";
        for (const wd of words) { if ((line + " " + wd).length > 48) { lines.push(line); line = wd; } else line = line ? line + " " + wd : wd; }
        lines.push(line);
        const bw = 400, bh = 22 * lines.length + 14, bx = Math.min(W - bw - 10, this.hover.x + 14), by = Math.min(H - bh - 10, this.hover.y + 14);
        ctx.fillStyle = "rgba(20,16,26,0.95)"; ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.fillRect(bx, by, bw, bh); ctx.strokeRect(bx, by, bw, bh);
        ctx.fillStyle = PAL.text; lines.forEach((l, i) => ctx.fillText(l, bx + 10, by + 24 + i * 22));
      }
    }
  }
  window.BrainView = BrainView;
  window.BRAIN_VIEW_SIZE = [W, H];
})();
