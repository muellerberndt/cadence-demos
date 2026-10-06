// Cadence eyes: the world (shapes the player drags, or that move on their own) lives in this
// page, which draws it into pixels. One Cadence brain in a worker sees nothing but those
// pixels: each tracked shape has an eye, a window of them, and every frame the brain answers
// where in each window its shape is; the eye jumps there. The brain view shows one eye's stream.
import { BrainScan, decodeAtlas } from "./brain_scan.js";
import { HELD_OUT, KINDS, ROTATES, TRAINED, backdrop, render } from "./shapes.js";

const $ = (id) => document.getElementById(id);
const PACK = new URL("pack/", import.meta.url).href;
const COLOURS = ["#46d07a", "#6aa8ff", "#ffb347", "#e07bd8", "#f2e15b", "#5fd3d3", "#ff7b72", "#b39dff"];
const MAX_EYES = 8;
const LABELS = {
  disc: "Disc", ring: "Ring", square: "Square", frame: "Frame", triangle: "Triangle", diamond: "Diamond",
  cross: "Cross", bar: "Bar", star: "Star", tee: "Tee", ell: "Ell", face: "Face",
};

let W = 160, H = 100, WIN = 26, BINS = 13, CELL = 2;
let EYE = { eye: "window" }; // the brain's description: a window eye or a foveated eye
let VIEW = 26; // side of an eye view: the window, or the fovea's receptors
let things = []; // {id, kind, x, y, size, level, angle, eye, colour}
let nextId = 1;
let bg = null;
let surface = null;
let ready = false;
let busy = false;
let lastSent = 0;
let lastTick = performance.now();
let result = null; // the brain's latest frame, scored
let selectedEye = null;
let selectedThing = null;
let drag = null;
const held = new Map();
const motion = new Map();
const history = [];
const doneTimes = [];
let scan = null;
let rng = 12345;
let UNSEEN = [...HELD_OUT]; // shapes the brain never saw while learning (from the pack)

const surfaceCanvas = $("surface");
const sctx = surfaceCanvas.getContext("2d");
const off = document.createElement("canvas");
const octx = off.getContext("2d");
const strip = $("strip");
const stctx = strip.getContext("2d");

function random() {
  rng ^= rng << 13; rng >>>= 0; rng ^= rng >>> 17; rng ^= rng << 5; rng >>>= 0;
  return (rng + 0.5) / 4294967296;
}
const uniform = (a, b) => a + (b - a) * random();

// -- the brain's workers: each holds the same brain and settles the eyes given to it, so
// several moving eyes settle in parallel. Every eye is one stream of the brain.

const POOL = Math.max(1, Math.min(6, (navigator.hardwareConcurrency || 4) - 2));
const pool = [];
function makeWorker(index) {
  const w = { worker: new Worker(new URL("worker.js", import.meta.url), { type: "module" }), seq: 0,
              waiting: new Map(), eyes: new Set(), index };
  w.worker.onmessage = (event) => {
    const m = event.data;
    if (m.status) { if (index === 0) $("loading").textContent = m.status; return; }
    const p = w.waiting.get(m.rid);
    if (!p) return;
    w.waiting.delete(m.rid);
    if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
  };
  return w;
}
function ask(w, op, data = {}, transfer = []) {
  return new Promise((resolve, reject) => {
    const rid = ++w.seq;
    w.waiting.set(rid, { resolve, reject });
    w.worker.postMessage({ ...data, op, rid }, transfer);
  });
}
function workerOf(id) { return pool.find((w) => w.eyes.has(id)); }
function call(op, data = {}) {
  if (op === "open") {
    const w = pool.reduce((a, b) => (b.eyes.size < a.eyes.size ? b : a));
    w.eyes.add(data.id);
    return ask(w, op, data);
  }
  if (op === "close" || op === "select") {
    const w = workerOf(data.id);
    if (op === "close" && w) w.eyes.delete(data.id);
    return w ? ask(w, op, data) : Promise.resolve(null);
  }
  if (op === "reset") pool.forEach((w) => w.eyes.clear());
  return Promise.all(pool.map((w) => ask(w, op, data)));
}

// -- shapes and eyes

function eyes() { return things.filter((t) => t.eye); }
function freeColour() {
  const used = new Set(eyes().map((t) => t.colour));
  return COLOURS.find((c) => !used.has(c)) || COLOURS[0];
}
function openEye(t) {
  if (t.eye || eyes().length >= MAX_EYES) return false;
  t.eye = true;
  t.colour = freeColour();
  call("open", { id: t.id, x: t.x, y: t.y });
  if (selectedEye === null) selectEye(t.id);
  return true;
}
function closeEye(t) {
  if (!t.eye) return;
  t.eye = false;
  call("close", { id: t.id });
  if (selectedEye === t.id) selectEye(eyes().length ? eyes()[0].id : null);
}
function selectEye(id) {
  selectedEye = id;
  if (id !== null) call("select", { id });
}
function add(kind, x, y, withEye = true) {
  const size = uniform(6, 10);
  const t = {
    id: nextId++, kind, size, level: uniform(0.4, 1.0),
    angle: ROTATES.has(kind) ? uniform(0, 2 * Math.PI) : 0,
    x: x ?? uniform(size, W - size), y: y ?? uniform(size, H - size), eye: false, colour: null,
  };
  if (x === undefined) {
    for (let k = 0; k < 60; k++) {
      const ok = things.every((o) => Math.hypot(o.x - t.x, o.y - t.y) >= 0.6 * (o.size + t.size) + 6);
      if (ok) break;
      t.x = uniform(size, W - size);
      t.y = uniform(size, H - size);
    }
  }
  things.push(t);
  if (withEye) openEye(t);
  return t;
}
function remove(t) {
  closeEye(t);
  things = things.filter((o) => o !== t);
  motion.delete(t.id);
  if (selectedThing === t.id) selectedThing = null;
}
function preset(name) {
  call("reset");
  things = [];
  selectedEye = null;
  selectedThing = null;
  motion.clear();
  result = null;
  const pick = (list) => list[Math.floor(random() * list.length)];
  if (name === "three") for (let k = 0; k < 3; k++) add(pick(TRAINED));
  if (name === "six") for (let k = 0; k < 6; k++) add(pick(TRAINED));
  if (name === "crowd") for (let k = 0; k < 12; k++) add(pick(TRAINED), undefined, undefined, k < 6);
  if (name === "unseen") {
    for (const kind of UNSEEN) add(kind);
    for (let k = 0; k < 2; k++) add(pick(TRAINED), undefined, undefined, false);
  }
}

// Shapes freeze, walk and dart on their own (pixels per second); a held shape waits.
function wander(dt, now) {
  for (const t of things) {
    let st = motion.get(t.id);
    if (!st || st.left <= 0) {
      const u = random();
      const mode = u < 0.35 ? "freeze" : u < 0.85 ? "walk" : "dart";
      const speed = { freeze: 0, walk: 6, dart: 30 }[mode];
      const [low, high] = { freeze: [0.6, 1.8], walk: [0.6, 2.0], dart: [0.15, 0.3] }[mode];
      const a = uniform(0, 2 * Math.PI);
      st = { vx: speed * Math.cos(a), vy: speed * Math.sin(a), left: uniform(low, high) };
      motion.set(t.id, st);
    }
    st.left -= dt;
    if ((held.get(t.id) || 0) > now || (drag && drag.id === t.id)) continue;
    const m = t.size / 2;
    let x = t.x + st.vx * dt;
    let y = t.y + st.vy * dt;
    if (x < m || x > W - m) st.vx = -st.vx;
    if (y < m || y > H - m) st.vy = -st.vy;
    t.x = Math.min(Math.max(x, m), W - m);
    t.y = Math.min(Math.max(y, m), H - m);
  }
}

// -- one brain frame

async function send(now) {
  busy = true;
  lastSent = now;
  const snapshot = new Map(things.map((t) => [t.id, { x: t.x, y: t.y }]));
  const busyWorkers = pool.filter((w) => w.eyes.size);
  try {
    const parts = await Promise.all(busyWorkers.map((w) => {
      const pixels = Float32Array.from(surface);
      return ask(w, "see", { pixels: pixels.buffer }, [pixels.buffer]);
    }));
    const r = { eyes: [], windows: [], sweeps: 0, worker_ms: 0, selected: selectedEye, activity: null };
    for (const part of parts) {
      r.eyes.push(...part.eyes);
      r.windows.push(...(part.windows || []));
      r.sweeps = Math.max(r.sweeps, part.sweeps);
      r.worker_ms = Math.max(r.worker_ms, part.worker_ms);
      if (part.selected === selectedEye) r.activity = part.activity;
    }
    onResult(r, snapshot);
  } catch (error) {
    $("state").textContent = "brain error";
    console.error(error);
  }
  busy = false;
}

function chebyshev(a, b) { return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])); }

// The foveated eye's bin of an offset from the gaze (tracker/fovea.py Fovea.bin_of).
function foveaBin(d) {
  const edges = EYE.edges;
  if (!(d >= edges[0] && d < edges[edges.length - 1])) return null;
  let r = 0;
  while (r + 1 < edges.length && edges[r + 1] <= d) r++;
  return EYE.bin_of_receptor[Math.min(Math.max(r, 0), EYE.receptors - 1)];
}

function onResult(r, snapshot) {
  if (EYE.eye === "fovea") {
    for (const e of r.eyes) {
      const own = snapshot.get(e.id);
      e.own = false;
      e.hit = false;
      if (!own) continue;
      const bx = foveaBin(own.x - e.gaze[0]), by = foveaBin(own.y - e.gaze[1]);
      e.inReach = bx !== null && by !== null;
      if (!e.inReach) continue;
      e.own = Math.max(Math.abs(bx - EYE.middle), Math.abs(by - EYE.middle)) <= 1;
      e.hit = !!e.answer && chebyshev(e.answer, [bx, by]) <= 1;
    }
    return finish(r);
  }
  const half = WIN / 2;
  for (const e of r.eyes) {
    const [gx, gy] = e.gaze;
    const ox = gx - half, oy = gy - half;
    const own = snapshot.get(e.id);
    let nearest = null, best = Infinity;
    for (const [id, p] of snapshot) {
      const x = p.x - ox, y = p.y - oy;
      if (x >= 0 && x < WIN && y >= 0 && y < WIN) {
        const d = (x - half) ** 2 + (y - half) ** 2;
        if (d < best) { best = d; nearest = id; }
      }
    }
    e.own = nearest === e.id;
    e.inReach = !!own && own.x - ox >= 0 && own.x - ox < WIN && own.y - oy >= 0 && own.y - oy < WIN;
    e.hit = false;
    if (own && e.answer) {
      const x = own.x - ox, y = own.y - oy;
      if (x >= 0 && x < WIN && y >= 0 && y < WIN) {
        e.hit = chebyshev(e.answer, [Math.floor(x / CELL), Math.floor(y / CELL)]) <= 1;
      }
    }
  }
  return finish(r);
}

function finish(r) {
  result = r;
  history.push(r.sweeps);
  if (history.length > 300) history.shift();
  const now = performance.now();
  doneTimes.push(now);
  while (doneTimes.length && now - doneTimes[0] > 2000) doneTimes.shift();
  const pill = $("state");
  pill.textContent = r.sweeps === 0 ? "equilibrium: no work" : `repair: ${r.sweeps} sweeps`;
  pill.className = "pill " + (r.sweeps === 0 ? "still" : "repair");
  $("sweeps").textContent = r.sweeps;
  $("ms").textContent = r.worker_ms.toFixed(0);
  $("fps").textContent = (doneTimes.length / 2).toFixed(0);
  $("own").textContent = r.eyes.length ? `${r.eyes.filter((e) => e.own).length} of ${r.eyes.length}` : "-";
  drawStrip();
  drawEyeViews(r);
  if (scan && r.activity) {
    const s = atob(r.activity);
    if (s.length === scan.n) {
      const act = new Float32Array(s.length);
      for (let i = 0; i < s.length; i++) act[i] = (s.charCodeAt(i) / 255) * 1.1 - 0.1;
      scan.step(act, { draw: false });
    }
  }
  const sel = things.find((t) => t.id === r.selected);
  $("legend").textContent = `Every module named; glow marks neurons that changed on this frame, the brain repairing. A brain in equilibrium cools. Showing the stream of ${sel ? `the ${sel.kind}'s eye` : "no eye"}.`;
}

// -- drawing

function colourOf(id) { const t = things.find((o) => o.id === id); return t && t.colour ? t.colour : "#ffffff"; }

function draw() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cw = Math.round(surfaceCanvas.clientWidth * dpr);
  const ch = Math.round(surfaceCanvas.clientHeight * dpr);
  if (surfaceCanvas.width !== cw || surfaceCanvas.height !== ch) { surfaceCanvas.width = cw; surfaceCanvas.height = ch; }
  if (!surface) return;
  if (off.width !== W) { off.width = W; off.height = H; }
  const img = octx.createImageData(W, H);
  for (let i = 0; i < W * H; i++) {
    const v = Math.round(Math.min(Math.max(surface[i], 0), 1) * 255);
    img.data[4 * i] = img.data[4 * i + 1] = img.data[4 * i + 2] = v;
    img.data[4 * i + 3] = 255;
  }
  octx.putImageData(img, 0, 0);
  sctx.imageSmoothingEnabled = false;
  sctx.drawImage(off, 0, 0, cw, ch);
  const k = cw / W;
  if (result) {
    for (const e of result.eyes) {
      const colour = colourOf(e.id);
      const [gx, gy] = e.gaze;
      if (EYE.eye === "fovea") {
        drawFovea(e, colour, gx, gy, k);
        continue;
      }
      const ox = gx - WIN / 2, oy = gy - WIN / 2;
      if ($("windows").checked) {
        sctx.strokeStyle = colour;
        sctx.globalAlpha = e.id === selectedEye ? 0.9 : 0.5;
        sctx.lineWidth = e.id === selectedEye ? 2.5 : 1.5;
        sctx.strokeRect(ox * k, oy * k, WIN * k, WIN * k);
        sctx.globalAlpha = 1;
      }
      if (e.answer) {
        sctx.strokeStyle = colour;
        sctx.lineWidth = 2.5;
        sctx.setLineDash(e.hit ? [] : [5, 4]);
        sctx.strokeRect((ox + e.answer[0] * CELL) * k, (oy + e.answer[1] * CELL) * k, CELL * k, CELL * k);
        sctx.setLineDash([]);
      }
    }
  }
  for (const t of things) {
    if (t.eye) {
      sctx.strokeStyle = t.colour;
      sctx.lineWidth = 2;
      sctx.beginPath();
      sctx.arc(t.x * k, t.y * k, (t.size * 0.62 + 1.5) * k, 0, 2 * Math.PI);
      sctx.globalAlpha = 0.35;
      sctx.stroke();
      sctx.globalAlpha = 1;
    }
    if (t.id === selectedThing) {
      sctx.strokeStyle = "rgba(255,255,255,0.85)";
      sctx.setLineDash([3, 3]);
      sctx.lineWidth = 1.5;
      sctx.beginPath();
      sctx.arc(t.x * k, t.y * k, (t.size * 0.62 + 3) * k, 0, 2 * Math.PI);
      sctx.stroke();
      sctx.setLineDash([]);
    }
  }
}

// A foveated eye: its fovea (solid), the reach of its periphery (dashed), and its answer, a box
// as large as the receptors of the answered bin, so it grows with eccentricity.
function drawFovea(e, colour, gx, gy, k) {
  const fine = EYE.inner + 0.5;
  const reach = EYE.edges[EYE.edges.length - 1];
  if ($("windows").checked) {
    sctx.strokeStyle = colour;
    sctx.globalAlpha = e.id === selectedEye ? 0.9 : 0.55;
    sctx.lineWidth = e.id === selectedEye ? 2.5 : 1.5;
    sctx.strokeRect((gx - fine) * k, (gy - fine) * k, 2 * fine * k, 2 * fine * k);
    sctx.globalAlpha = e.id === selectedEye ? 0.35 : 0.18;
    sctx.setLineDash([4, 6]);
    sctx.lineWidth = 1;
    sctx.strokeRect((gx - reach) * k, (gy - reach) * k, 2 * reach * k, 2 * reach * k);
    sctx.setLineDash([]);
    sctx.globalAlpha = 1;
  }
  if (e.answer) {
    const [bx, by] = e.answer;
    const x0 = gx + EYE.bin_lo[bx], x1 = gx + EYE.bin_hi[bx];
    const y0 = gy + EYE.bin_lo[by], y1 = gy + EYE.bin_hi[by];
    sctx.strokeStyle = colour;
    sctx.lineWidth = 2.5;
    sctx.setLineDash(e.hit ? [] : [5, 4]);
    sctx.strokeRect(x0 * k, y0 * k, (x1 - x0) * k, (y1 - y0) * k);
    sctx.setLineDash([]);
  }
}

function drawStrip() {
  const w = strip.width, h = strip.height;
  stctx.clearRect(0, 0, w, h);
  const peak = Math.max(64, ...history);
  const bw = w / 300;
  history.forEach((v, i) => {
    const x = w - (history.length - i) * bw;
    const y = h - 10 - (h - 24) * (v / peak);
    stctx.fillStyle = v === 0 ? "#363c49" : "#6aa8ff";
    stctx.fillRect(x, v === 0 ? h - 12 : y, Math.max(bw - 1, 1), v === 0 ? 2 : h - 10 - y);
  });
  stctx.fillStyle = "#98a1b3";
  stctx.font = "12px system-ui";
  stctx.fillText("settling sweeps per brain frame (flat: equilibrium held, no work)", 6, 13);
}

function drawEyeViews(r) {
  const box = $("eyeviews");
  if (!r.windows || box.children.length !== r.eyes.length) {
    box.innerHTML = "";
    r.eyes.forEach((e) => {
      const f = document.createElement("figure");
      const c = document.createElement("canvas");
      c.width = c.height = VIEW;
      const cap = document.createElement("figcaption");
      f.append(c, cap);
      f.onclick = () => selectEye(e.id);
      box.appendChild(f);
    });
  }
  if (!r.windows) return;
  r.eyes.forEach((e, i) => {
    const f = box.children[i];
    const c = f.querySelector("canvas");
    const t = things.find((o) => o.id === e.id);
    c.style.borderColor = colourOf(e.id);
    f.classList.toggle("sel", e.id === r.selected);
    f.querySelector("figcaption").textContent = t ? `${t.kind}${e.own ? "" : e.inReach ? " (catching up)" : " (lost)"}` : "";
    const g = c.getContext("2d");
    const s = atob(r.windows[i]);
    const moved = r.changes ? atob(r.changes[i]) : null;
    const img = g.createImageData(VIEW, VIEW);
    for (let j = 0; j < s.length; j++) {
      const v = s.charCodeAt(j);
      const m = moved ? moved.charCodeAt(j) : 0; // change since the last frame, shown in red
      img.data[4 * j] = Math.min(255, v + m);
      img.data[4 * j + 1] = img.data[4 * j + 2] = Math.max(0, v - m);
      img.data[4 * j + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  });
}

// -- the frame clock: the world and the display run every animation frame; the brain takes
// the newest pixels whenever it is free, at most at the chosen rate.

function tick(now) {
  const dt = Math.min((now - lastTick) / 1000, 0.1);
  lastTick = now;
  if (ready) {
    const paused = $("pause").checked;
    if (!paused && $("animate").checked) wander(dt, now);
    surface = render(H, W, things, bg);
    const rate = Number($("rate").value);
    if (!paused && !busy && now - lastSent >= 1000 / rate) send(now);
    draw();
  }
  if (scan) scan.draw(now);
  requestAnimationFrame(tick);
}

// -- the mouse and the keyboard

function surfacePoint(ev) {
  const r = surfaceCanvas.getBoundingClientRect();
  return [((ev.clientX - r.left) / r.width) * W, ((ev.clientY - r.top) / r.height) * H];
}
function hitTest(x, y) {
  let best = null, bestD = Infinity;
  for (const t of things) {
    const d = Math.hypot(t.x - x, t.y - y);
    if (d <= t.size * 0.6 + 1.5 && d < bestD) { best = t; bestD = d; }
  }
  return best;
}
surfaceCanvas.addEventListener("pointerdown", (ev) => {
  if (!ready || ev.button !== 0) return;
  surfaceCanvas.focus();
  const [x, y] = surfacePoint(ev);
  const t = hitTest(x, y);
  selectedThing = t ? t.id : null;
  if (t) {
    if (t.eye) selectEye(t.id);
    drag = { id: t.id, dx: t.x - x, dy: t.y - y };
    surfaceCanvas.classList.add("drag");
    surfaceCanvas.setPointerCapture(ev.pointerId);
  }
});
surfaceCanvas.addEventListener("pointermove", (ev) => {
  if (!drag) return;
  const t = things.find((o) => o.id === drag.id);
  if (!t) return;
  const [x, y] = surfacePoint(ev);
  const m = t.size / 2;
  t.x = Math.min(Math.max(x + drag.dx, m), W - m);
  t.y = Math.min(Math.max(y + drag.dy, m), H - m);
});
function endDrag() {
  if (drag) held.set(drag.id, performance.now() + 600);
  drag = null;
  surfaceCanvas.classList.remove("drag");
}
surfaceCanvas.addEventListener("pointerup", endDrag);
surfaceCanvas.addEventListener("pointercancel", endDrag);
surfaceCanvas.addEventListener("dblclick", (ev) => {
  const [x, y] = surfacePoint(ev);
  const t = hitTest(x, y);
  if (t) { if (t.eye) closeEye(t); else openEye(t); }
});
surfaceCanvas.addEventListener("contextmenu", (ev) => {
  ev.preventDefault();
  const [x, y] = surfacePoint(ev);
  const t = hitTest(x, y);
  if (t) remove(t);
});
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT") return;
  if (ev.key === " ") { ev.preventDefault(); $("pause").checked = !$("pause").checked; return; }
  const t = things.find((o) => o.id === selectedThing);
  if (!t) return;
  const step = ev.shiftKey ? 2 : 0.5;
  const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  if (moves[ev.key]) {
    ev.preventDefault();
    t.x = Math.min(Math.max(t.x + moves[ev.key][0], t.size / 2), W - t.size / 2);
    t.y = Math.min(Math.max(t.y + moves[ev.key][1], t.size / 2), H - t.size / 2);
    held.set(t.id, performance.now() + 600);
  } else if (ev.key === "Delete" || ev.key === "Backspace") {
    remove(t);
  } else if (ev.key === "e") {
    if (t.eye) closeEye(t); else openEye(t);
  }
});

// -- start

function palette() {
  const pal = $("palette");
  pal.innerHTML = "";
  for (const kind of [...KINDS].sort((a, b) => UNSEEN.includes(a) - UNSEEN.includes(b))) {
    const b = document.createElement("button");
    const unseen = UNSEEN.includes(kind);
    b.className = "add" + (unseen ? " unseen" : "");
    b.textContent = LABELS[kind];
    b.title = unseen ? "never seen while learning" : "seen while learning";
    b.onclick = () => ready && add(kind);
    pal.appendChild(b);
  }
}

function controls() {
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => ready && preset(b.dataset.preset)));
  $("clear").addEventListener("click", () => ready && preset("clear"));
  $("rate").addEventListener("input", (e) => { $("ratev").textContent = e.target.value; });
}

async function boot() {
  palette();
  controls();
  requestAnimationFrame(tick);
  try {
    const atlasPromise = fetch(PACK + "atlas.json").then((r) => r.json());
    for (let k = 0; k < POOL; k++) pool.push(makeWorker(k));
    const started = await Promise.all(pool.map((w) => ask(w, "start", { pack: PACK })));
    const { manifest, describe } = started[0];
    W = manifest.width; H = manifest.height; WIN = manifest.window; BINS = manifest.bins; CELL = WIN / BINS;
    if (manifest.trained_shapes) {
      UNSEEN = KINDS.filter((k) => !manifest.trained_shapes.includes(k));
      palette();
    }
    EYE = describe;
    if (EYE.eye === "fovea") {
      EYE.inner = manifest.fovea.inner;
      VIEW = EYE.receptors;
      $("about").textContent = "One Cadence brain runs in this page and follows every tracked shape. Each tracked shape has an eye that sees sharply at its centre and coarsely around it, and also sees what changed since the last frame. Every frame the brain answers, for each eye, where its own shape is, and the eye jumps there, a small step or a long saccade. The pixels are all the brain gets. While nothing moves it stays in equilibrium and does no settling at all.";
      $("legend-eye").textContent = "Each eye's solid square is its fovea and the dashed square how far it sees; the box is its answer, solid on its own shape and dashed off it, larger the farther out it points. The eye views show what each eye sees, with change in red.";
    } else {
      VIEW = WIN;
    }
    bg = backdrop(H, W, 0.1, 0.03, 7);
    const { atlas } = await atlasPromise;
    scan = new BrainScan($("scan"), decodeAtlas(atlas), {
      style: "brain", labels: $("labels"), strip: $("montage"), spin: true, spinRate: 0.05,
      labelCount: 8, labelTop: 8, heatDecay: 0.88, dpr: 1.5, lineBudget: 15000,
      particleBudget: 8000, montageRows: 6,
    });
    scan.onhover = (hit) => {
      if (hit) $("inspector").textContent = `${hit.region} · neuron ${hit.neuron} · activity ${hit.activation.toFixed(3)}`;
    };
    scan.fit();
    $("brainname").textContent = `${describe.neurons.toLocaleString()} neurons · ${describe.synapses.toLocaleString()} synapses · Cadence ${manifest.cadence} in Pyodide ${manifest.pyodide} · ${POOL} worker${POOL > 1 ? "s" : ""}`;
    $("loading").textContent = "brain ready";
    $("loading").className = "loading ready";
    ready = true;
    preset("six");
  } catch (error) {
    $("loading").textContent = `the brain did not load: ${error.message}`;
    $("loading").className = "loading failed";
    console.error(error);
  }
}
boot();

// A read-only handle for checks and the curious: the shapes and the brain's latest frame.
window.cadenceEyes = { get things() { return things; }, get result() { return result; }, get workers() { return pool.length; } };
