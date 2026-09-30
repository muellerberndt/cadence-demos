/* Live 3D view of the settling brain: retina planes feed population clouds,
   sampled functional wiring, per-patch settled state and repair oscillation,
   motor column on the right. Drag to rotate, wheel to zoom. Data arrives via
   window.BV (filled by the page's websocket handler) and GET /graph. */

/* global THREE */
(function () {
  const container = document.getElementById("brain3d");
  if (!container || typeof THREE === "undefined") return;
  let W = container.clientWidth || 380, H = container.clientHeight || 320;
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setSize(W, H);
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, W / H, 1, 2000);
  function fit() {
    W = container.clientWidth || W; H = container.clientHeight || H;
    if (W < 10 || H < 10) return;
    renderer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(fit).observe(container);
  window.BV = window.BV || {};
  window.BV.requestResize = () => setTimeout(fit, 50);
  camera.position.set(0, 60, 430);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 0.95));
  const key = new THREE.DirectionalLight(0xffffff, 0.7);
  key.position.set(120, 200, 180);
  scene.add(key);
  const world = new THREE.Group();
  scene.add(world);

  // ---- interaction: drag rotate, wheel zoom, gentle idle spin ----
  let dragging = false, lastX = 0, lastY = 0;
  let lastInteract = -1e9;  // time-based idle spin; a counter can get stuck
  renderer.domElement.style.cursor = "grab";
  renderer.domElement.addEventListener("mousedown", (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    lastInteract = performance.now();
  });
  window.addEventListener("mouseup", () => { dragging = false; });
  window.addEventListener("blur", () => { dragging = false; });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    world.rotation.y += (e.clientX - lastX) * 0.005;
    world.rotation.x += (e.clientY - lastY) * 0.005;
    world.rotation.x = Math.max(-0.9, Math.min(0.9, world.rotation.x));
    lastX = e.clientX; lastY = e.clientY;
    lastInteract = performance.now();
  });
  renderer.domElement.addEventListener("wheel", (e) => {
    e.preventDefault();
    camera.position.z = Math.max(140, Math.min(700,
      camera.position.z + e.deltaY * 0.4));
    lastInteract = performance.now();
  }, {passive: false});

  // ---- node positions per functional group ----
  const positions = [];   // flat list of THREE.Vector3
  const groupOf = [];     // group name per node
  let counts = null;      // {periphery, fovea, pops: [...], motor}

  function grid(nx, ny, cx, cy, cz, sx, sy) {
    const out = [];
    for (let r = 0; r < ny; r++)
      for (let c = 0; c < nx; c++)
        out.push(new THREE.Vector3(
          cx, cy + (ny / 2 - r) * sy, cz + (c - nx / 2) * sx));
    return out;
  }
  function cloud(n, cx, cy, cz, radius, seed) {
    const out = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const t = n === 1 ? 0.5 : i / (n - 1);
      const y = 1 - 2 * t;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const a = golden * (i + (seed || 0));
      out.push(new THREE.Vector3(
        cx + radius * r * Math.cos(a) * 0.85,
        cy + radius * y,
        cz + radius * r * Math.sin(a) * 0.85));
    }
    return out;
  }

  function buildLayout(graphMeta) {
    counts = {periphery: graphMeta.n_periphery, fovea: graphMeta.n_fovea,
              pops: graphMeta.populations, motor: graphMeta.motor};
    positions.length = 0; groupOf.length = 0;
    const push = (list, name) => {
      for (const p of list) { positions.push(p); groupOf.push(name); }
    };
    const ps = graphMeta.periphery_shape || [20, 32];
    const fs = graphMeta.fovea_shape || [6, 64];
    push(grid(ps[1], ps[0], -150, 30, 0, 172.8 / ps[1], 108 / ps[0]), "periphery");
    push(grid(fs[1], fs[0], -150, -78, 0, 185.6 / fs[1], 30 / fs[0]), graphMeta.fovea_label || "fovea");
    const anchors = {
      scene: [-58, 34, 0, 42], aim: [-58, -66, 0, 30],
      integration: [28, -8, 0, 40], reflection: [98, -4, 0, 26],
      hidden: [-40, 20, 0, 42], policy: [80, -4, 0, 35],
      reflection1: [-4, 12, 0, 30], reflection2: [38, -28, 0, 26],
    };
    let seed = 0;
    for (const p of counts.pops) {
      const [x, y, z, r] = anchors[p.name] || [30, 0, 0, 30];
      push(cloud(p.count, x, y, z, r * Math.sqrt(p.count / 32), seed += 11),
           p.name);
    }
    push(grid(1, counts.motor, 165, 0, 0, 0, 15), "motor");
  }

  function buildLabels() {
    labelGroup = new THREE.Group();
    const seen = {};
    for (let i = 0; i < positions.length; i++) {
      const g = groupOf[i];
      if (!seen[g]) seen[g] = {n: 0, x: 0, top: -1e9};
      seen[g].n += 1; seen[g].x += positions[i].x;
      seen[g].top = Math.max(seen[g].top, positions[i].y);
    }
    for (const [name, agg] of Object.entries(seen)) {
      const label = makeLabel(name.toUpperCase());
      label.position.set(agg.x / agg.n, agg.top + 12, 0);
      labelGroup.add(label);
    }
    world.add(labelGroup);
  }

  // ---- meshes ----
  let labelGroup = null;
  function makeLabel(text) {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 56;
    const ctx = canvas.getContext("2d");
    ctx.font = "600 30px ui-monospace, Menlo, monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(210,210,228,0.92)";
    ctx.shadowColor = "#000"; ctx.shadowBlur = 8;
    ctx.fillText(text, 128, 28);
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial(
      {map: texture, transparent: true, depthTest: false}));
    sprite.scale.set(46, 10, 1);
    return sprite;
  }

  let nodes = null, dummy = new THREE.Object3D();
  let colorAttr = null;
  let edgeLines = null, edgeMeta = null, edgeColors = null;
  const KIND_COLOR = [new THREE.Color(0x5a7ba6),   // input wiring
                     new THREE.Color(0x9a6fd0),    // state readback
                     new THREE.Color(0xe0a63c)];   // prediction-error readback

  function buildMeshes(graph) {
    buildLayout(graph);
    const n = positions.length;
    nodes = new THREE.InstancedMesh(
      new THREE.SphereGeometry(1.9, 8, 8),
      new THREE.MeshLambertMaterial({}), n);
    nodes.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < n; i++) {
      dummy.position.copy(positions[i]);
      dummy.scale.setScalar(1);
      dummy.updateMatrix();
      nodes.setMatrixAt(i, dummy.matrix);
      nodes.setColorAt(i, new THREE.Color(0x2a2a35));
    }
    colorAttr = nodes.instanceColor;
    world.add(nodes);

    const patchBase = counts.periphery + counts.fovea;
    const verts = [];
    edgeMeta = [];
    let strongest = 0.001;
    for (const [, , , w] of graph.edges) strongest = Math.max(strongest, Math.abs(w));
    for (const [kind, s, t, w] of graph.edges) {
      const si = kind === 0 ? s : patchBase + s;
      const ti = patchBase + t;
      if (!positions[si] || !positions[ti]) continue;
      verts.push(positions[si].x, positions[si].y, positions[si].z,
                 positions[ti].x, positions[ti].y, positions[ti].z);
      edgeMeta.push({kind, si, ti,
                     w: 0.3 + 0.7 * Math.min(1, Math.abs(w) / strongest)});
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    edgeColors = new Float32Array(edgeMeta.length * 6);
    geo.setAttribute("color", new THREE.BufferAttribute(edgeColors, 3));
    geo.attributes.color.setUsage(THREE.DynamicDrawUsage);
    edgeLines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.85,
      blending: THREE.AdditiveBlending, depthWrite: false}));
    world.add(edgeLines);
    buildLabels();
  }

  function nodeActivity(i, BV) {
    const patchBase = counts.periphery + counts.fovea;
    if (i < counts.periphery)
      return BV.retina_p ? Math.abs(BV.retina_p[i]) / 0.6 : 0.2;
    if (i < patchBase)
      return BV.retina_f ? Math.abs(BV.retina_f[i - counts.periphery]) / 0.6 : 0.2;
    const j = i - patchBase;
    return now.s && j < now.s.length ? Math.abs(now.s[j]) / 0.6 : 0.2;
  }

  let builtVersion = 0;
  function teardown() {
    if (nodes) { world.remove(nodes); nodes.geometry.dispose();
                 nodes.material.dispose(); nodes = null; }
    if (edgeLines) { world.remove(edgeLines); edgeLines.geometry.dispose();
                     edgeLines.material.dispose(); edgeLines = null;
                     edgeMeta = null; edgeColors = null; }
    if (labelGroup) {
      for (const sprite of labelGroup.children) {
        sprite.material.map.dispose(); sprite.material.dispose();
      }
      world.remove(labelGroup); labelGroup = null;
    }
    now.s = null; now.e = null;
  }

  // ---- live coloring ----
  const now = {s: null, e: null};
  const cold = new THREE.Color(0x3565d0), hot = new THREE.Color(0xe0483c);
  const dimmed = new THREE.Color(0x54546a), errCol = new THREE.Color(0xf5a524);
  const tmp = new THREE.Color();
  let pulse = 0, lastAdmitted = -1;

  function tick(t) {
    requestAnimationFrame(tick);
    const BV = window.BV || {};
    const version = BV.graphVersion || (BV.graph ? 1 : 0);
    if (BV.graph && version !== builtVersion) {
      teardown();
      buildMeshes(BV.graph);
      builtVersion = version;
    }
    if (!nodes) { renderer.render(scene, camera); return; }
    if (BV.admitted !== undefined && lastAdmitted >= 0 &&
        BV.admitted > lastAdmitted) pulse = 1;
    if (BV.admitted !== undefined) lastAdmitted = Math.max(lastAdmitted, BV.admitted);
    pulse *= 0.96;
    if (!dragging && t - lastInteract > 3000) world.rotation.y += 0.0022;

    const patchBase = counts.periphery + counts.fovea;
    const st = BV.state, er = BV.errors;
    if (st) {
      if (!now.s || now.s.length !== st.length) {
        now.s = st.slice(); now.e = (er || st.map(() => 0)).slice();
      }
      for (let i = 0; i < st.length; i++) {
        now.s[i] += (st[i] - now.s[i]) * 0.16;
        now.e[i] += ((er ? er[i] : 0) - now.e[i]) * 0.16;
      }
    }
    const sec = t / 1000;
    for (let i = 0; i < positions.length; i++) {
      let scale = 1, colorSet = false;
      if (i < counts.periphery && BV.retina_p) {
        const v = (BV.retina_p[i] + 0.6) / 1.2;
        tmp.setScalar(0.09 + 0.38 * Math.max(0, Math.min(1, v)));
        colorSet = true;
      } else if (i >= counts.periphery && i < patchBase && BV.retina_f) {
        const v = (BV.retina_f[i - counts.periphery] + 0.6) / 1.2;
        tmp.setRGB(0.1 + 0.4 * v, 0.1 + 0.35 * v, 0.13 + 0.3 * v);
        colorSet = true;
      } else if (i >= patchBase && now.s) {
        const j = i - patchBase;
        if (j < now.s.length) {
          const v = Math.max(-0.6, Math.min(0.6, now.s[j])) / 0.6;
          tmp.copy(dimmed).lerp(v >= 0 ? hot : cold, Math.abs(v));
          const err = Math.min(1, Math.abs(now.e[j]) * 3);
          if (err > 0.05) {
            tmp.lerp(errCol, 0.45 * err);
            scale = 1 + 0.55 * err * (1 + Math.sin(sec * 9 + j * 1.7));
          } else {
            scale = 1 + 0.5 * Math.abs(v);
          }
          colorSet = true;
        } else if (BV.buttons) {  // motor nodes follow decoded buttons
          const m = j - now.s.length;
          if (BV.buttons[m]) { tmp.setHex(0x46a758); scale = 1.7; }
          else tmp.copy(dimmed);
          colorSet = true;
        }
      }
      if (colorSet) {
        if (pulse > 0.04) {
          const wave = Math.max(0, 1 - Math.abs(
            (positions[i].x + 160) / 330 - (1 - pulse)) * 6);
          tmp.lerp(new THREE.Color(0x46a758), 0.6 * wave * pulse);
        }
        nodes.setColorAt(i, tmp);
      }
      dummy.position.copy(positions[i]);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      nodes.setMatrixAt(i, dummy.matrix);
    }
    nodes.instanceMatrix.needsUpdate = true;
    if (nodes.instanceColor) nodes.instanceColor.needsUpdate = true;
    if (edgeLines && edgeMeta) {
      // Dendrites/axons: brightness follows the source neuron's activity,
      // fading toward the target so signal direction reads at a glance.
      for (let e = 0; e < edgeMeta.length; e++) {
        const meta = edgeMeta[e];
        const act = Math.min(1, nodeActivity(meta.si, BV));
        const base = KIND_COLOR[meta.kind];
        // Anatomy stays visible at rest; activity and learning add glow.
        const glow = meta.w * (0.42 + 0.58 * act) * (1 + 1.2 * pulse);
        const o = e * 6;
        edgeColors[o] = base.r * glow;
        edgeColors[o + 1] = base.g * glow;
        edgeColors[o + 2] = base.b * glow;
        edgeColors[o + 3] = base.r * glow * 0.45;
        edgeColors[o + 4] = base.g * glow * 0.45;
        edgeColors[o + 5] = base.b * glow * 0.45;
      }
      edgeLines.geometry.attributes.color.needsUpdate = true;
    }
    renderer.render(scene, camera);
  }
  requestAnimationFrame(tick);

  fetch("/graph").then((r) => r.json()).then((g) => { window.BV = window.BV || {}; window.BV.graph = g; });
})();
