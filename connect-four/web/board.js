// The board: stones behind a frame with holes, one button per column, the brain's seven motor
// neurons as bars above the columns, and the replies the brain imagines as ghosts below them.
const NS = 'http://www.w3.org/2000/svg';
const ROWS = 6, COLUMNS = 7, U = 100;
const svg = (tag, attrs = {}, parent) => {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.append(node);
  return node;
};
const cx = (cell) => (cell % COLUMNS) * U + U / 2;
const cy = (cell) => (ROWS - 1 - Math.floor(cell / COLUMNS)) * U + U / 2;

export class Board {
  constructor({ board, motor, ghosts, onColumn, onHover }) {
    this.root = board; this.motorRoot = motor; this.ghostRoot = ghosts;
    this.onColumn = onColumn; this.onHover = onHover;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.cells = new Array(ROWS * COLUMNS).fill(0);
    this.stones = new Map();
    this.build();
  }

  build() {
    const s = this.svg = svg('svg', { viewBox: `0 0 ${COLUMNS * U} ${ROWS * U}`, class: 'board-svg', 'aria-hidden': 'true' }, this.root);
    const defs = svg('defs', {}, s);
    const mask = svg('mask', { id: 'holes' }, defs);
    svg('rect', { width: COLUMNS * U, height: ROWS * U, fill: 'white' }, mask);
    for (let k = 0; k < ROWS * COLUMNS; k++) svg('circle', { cx: cx(k), cy: cy(k), r: 39, fill: 'black' }, mask);
    const grad = (id, stops) => {
      const g = svg('radialGradient', { id, cx: '38%', cy: '32%', r: '75%' }, defs);
      stops.forEach(([o, c]) => svg('stop', { offset: o, 'stop-color': c }, g));
    };
    grad('stone-you', [['0%', '#ffd9a8'], ['45%', '#ff9f4a'], ['100%', '#c4561f']]);
    grad('stone-brain', [['0%', '#c9fff6'], ['45%', '#3fe0cf'], ['100%', '#0f8f88']]);
    const frame = svg('linearGradient', { id: 'frame', x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    svg('stop', { offset: '0%', 'stop-color': '#27325a' }, frame);
    svg('stop', { offset: '100%', 'stop-color': '#18203d' }, frame);
    svg('rect', { class: 'well', width: COLUMNS * U, height: ROWS * U, rx: 26 }, s);
    this.preview = svg('circle', { class: 'preview', r: 39, cx: -200, cy: -200 }, s);
    this.stoneLayer = svg('g', { class: 'stones' }, s);
    svg('rect', { class: 'frame', width: COLUMNS * U, height: ROWS * U, rx: 26, fill: 'url(#frame)', mask: 'url(#holes)' }, s);
    const rims = svg('g', { class: 'rims' }, s);
    for (let k = 0; k < ROWS * COLUMNS; k++) svg('circle', { cx: cx(k), cy: cy(k), r: 39.5 }, rims);
    this.marks = svg('g', { class: 'marks' }, s);
    const columns = document.createElement('div');
    columns.className = 'columns';
    this.buttons = [];
    for (let c = 0; c < COLUMNS; c++) {
      const b = document.createElement('button');
      b.className = 'column'; b.id = `col-${c}`; b.type = 'button';
      b.setAttribute('aria-label', `Drop a stone in column ${c + 1}`);
      b.addEventListener('click', () => this.onColumn?.(c));
      b.addEventListener('pointerenter', () => { this.hoverColumn = c; this.updatePreview(); this.onHover?.(c); });
      b.addEventListener('pointerleave', () => { if (this.hoverColumn === c) { this.hoverColumn = null; this.updatePreview(); this.onHover?.(null); } });
      columns.append(b); this.buttons.push(b);
    }
    this.root.append(columns);
    // motor bars
    this.bars = [];
    for (let c = 0; c < COLUMNS; c++) {
      const bar = document.createElement('div');
      bar.className = 'bar';
      bar.innerHTML = '<span class="track"><span class="before"></span><span class="fill"></span></span><span class="value"></span>';
      this.motorRoot.append(bar);
      this.bars.push({ root: bar, fill: bar.querySelector('.fill'), before: bar.querySelector('.before'), value: bar.querySelector('.value') });
    }
    // ghosts
    this.ghostCanvas = document.createElement('canvas');
    this.ghostCanvas.className = 'ghost-canvas';
    this.ghostCanvas.setAttribute('aria-label', 'The reply the brain imagines for each column it could play');
    this.ghostRoot.append(this.ghostCanvas);
    new ResizeObserver(() => this.drawGhosts()).observe(this.ghostRoot);
  }

  // owners: 42 entries of 0 (empty), 'you' or 'brain'
  set(owners, { line = [], last = null, animate = null } = {}) {
    const added = [];
    for (let k = 0; k < owners.length; k++) {
      const owner = owners[k];
      const node = this.stones.get(k);
      if (!owner && node) { node.remove(); this.stones.delete(k); continue; }
      if (owner && (!node || node.dataset.owner !== owner)) {
        node?.remove();
        const g = svg('g', { class: `stone ${owner}`, 'data-owner': owner, 'data-cell': k }, this.stoneLayer);
        svg('circle', { cx: cx(k), cy: cy(k), r: 40, fill: `url(#stone-${owner})` }, g);
        svg('circle', { class: 'gloss', cx: cx(k) - 11, cy: cy(k) - 13, r: 12 }, g);
        this.stones.set(k, g);
        added.push(k);
      }
    }
    this.cells = owners.slice();
    for (const [k, node] of this.stones) {
      node.classList.toggle('win', line.includes(k));
      node.classList.toggle('dim', line.length > 0 && !line.includes(k));
      node.classList.toggle('last', k === last);
    }
    this.updatePreview();
    if (animate !== null && added.includes(animate)) return this.drop(animate);
    return Promise.resolve();
  }

  drop(cell) {
    const node = this.stones.get(cell);
    if (!node || this.reduced) return Promise.resolve();
    const distance = cy(cell) + U * 0.6;
    const fall = 260 + 32 * (ROWS - Math.floor(cell / COLUMNS));
    const animation = node.animate([
      { transform: `translateY(${-distance}px)`, easing: 'cubic-bezier(.55,0,1,.45)' },
      { transform: 'translateY(0)', offset: 0.72, easing: 'cubic-bezier(0,.4,.5,1)' },
      { transform: 'translateY(-14px)', offset: 0.86, easing: 'cubic-bezier(.5,0,1,.5)' },
      { transform: 'translateY(0)' },
    ], { duration: fall });
    return animation.finished.catch(() => {});
  }

  setPlayable(legal, active, mode = 'play') {
    this.legal = legal; this.active = active; this.mode = mode;
    this.root.dataset.mode = mode;
    this.buttons.forEach((b, c) => {
      const ok = active && !!legal?.[c];
      b.disabled = !ok;
      b.setAttribute('aria-label', mode === 'teach' ? `Teach column ${c + 1}` : `Drop a stone in column ${c + 1}`);
    });
    this.updatePreview();
  }

  updatePreview() {
    const c = this.hoverColumn;
    const show = c !== null && c !== undefined && this.active && this.legal?.[c] && this.mode === 'play';
    if (!show) { this.preview.setAttribute('cx', -200); return; }
    let r = 0;
    while (r < ROWS && this.cells[r * COLUMNS + c]) r++;
    if (r >= ROWS) { this.preview.setAttribute('cx', -200); return; }
    this.preview.setAttribute('cx', cx(r * COLUMNS + c)); this.preview.setAttribute('cy', cy(r * COLUMNS + c));
  }

  // marks: a dashed ring for a stone under teaching, rings for a taught column
  setMarks({ ghostCell = null, taught = null } = {}) {
    this.marks.replaceChildren();
    if (ghostCell !== null) svg('circle', { class: 'ghost-ring', cx: cx(ghostCell), cy: cy(ghostCell), r: 36 }, this.marks);
    if (taught !== null) svg('circle', { class: 'taught-ring', cx: cx(taught), cy: cy(taught), r: 36 }, this.marks);
  }

  // motor: seven activations; chosen: the column played; legal: which columns had room
  setMotor(motor, { chosen = null, legal = null, before = null } = {}) {
    this.bars.forEach((bar, c) => {
      const v = motor ? motor[c] : 0;
      const h = Math.max(0, Math.min(1, v));
      bar.fill.style.transform = `scaleY(${h.toFixed(4)})`;
      bar.root.classList.toggle('chosen', chosen === c);
      bar.root.classList.toggle('blocked', !!legal && !legal[c]);
      bar.value.textContent = motor ? v.toFixed(2) : '';
      if (before) { bar.before.style.bottom = `calc(${(Math.max(0, Math.min(1, before[c])) * 100).toFixed(2)}% - 1px)`; bar.before.hidden = false; }
      else bar.before.hidden = true;
      bar.root.title = motor ? `Motor neuron ${c + 1}: activation ${v.toFixed(3)}` : `Motor neuron ${c + 1}`;
    });
    this.motorRoot.classList.toggle('empty', !motor);
  }

  // ghosts: the imagined candidates from the host, drawn on the present position
  setGhosts(candidates, owners) {
    this.ghosts = candidates ? { candidates, owners: owners.slice() } : null;
    this.drawGhosts();
  }

  drawGhosts() {
    const canvas = this.ghostCanvas, box = this.ghostRoot.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = Math.max(70, box.width), colW = W / COLUMNS;
    const cell = Math.min(7.5, (colW - 10) / COLUMNS), H = Math.round(cell * ROWS + 21);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
    const c = canvas.getContext('2d');
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    for (let col = 0; col < COLUMNS; col++) {
      const x0 = col * colW + (colW - cell * COLUMNS) / 2, y0 = 4;
      c.fillStyle = 'rgba(30,38,66,0.55)';
      c.beginPath(); c.roundRect(x0 - 3, y0 - 3, cell * COLUMNS + 6, cell * ROWS + 6, 4); c.fill();
      const item = this.ghosts?.candidates.find((g) => g.column === col);
      const owners = this.ghosts?.owners || [];
      let drop = -1, reply = -1;
      if (item) {
        drop = this.landing(owners, col);
        if (item.reply !== undefined) {
          const after = owners.slice(); if (drop >= 0) after[drop] = 'brain';
          reply = this.landing(after, item.reply);
        }
      }
      for (let k = 0; k < ROWS * COLUMNS; k++) {
        const x = x0 + (k % COLUMNS + 0.5) * cell, y = y0 + (ROWS - 1 - Math.floor(k / COLUMNS) + 0.5) * cell;
        const owner = owners[k];
        let fill = 'rgba(80,92,130,0.35)', r = cell * 0.28;
        if (owner === 'you') fill = 'rgba(255,159,74,0.55)';
        if (owner === 'brain') fill = 'rgba(63,224,207,0.55)';
        if (k === drop) { fill = 'rgba(120,255,240,0.95)'; r = cell * 0.4; }
        c.fillStyle = fill; c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
        if (k === reply) {
          c.strokeStyle = item.reply_wins ? 'rgba(255,90,110,1)' : 'rgba(255,190,120,1)';
          c.lineWidth = 1.6; c.beginPath(); c.arc(x, y, cell * 0.42, 0, Math.PI * 2); c.stroke();
        }
      }
      c.font = '600 9.5px Inter, system-ui, sans-serif'; c.textAlign = 'center';
      let caption = '';
      if (!this.ghosts) caption = '';
      else if (!item) caption = 'full';
      else if (item.wins) caption = 'wins';
      else if (item.draw) caption = 'draw';
      else caption = item.reply_wins ? `you ${item.reply + 1} · win` : `you ${item.reply + 1}`;
      c.fillStyle = item?.reply_wins ? 'rgba(255,120,135,0.95)' : item?.wins ? 'rgba(120,255,235,0.95)' : 'rgba(170,182,215,0.8)';
      c.fillText(caption, col * colW + colW / 2, y0 + cell * ROWS + 15);
    }
    this.ghostRoot.classList.toggle('empty', !this.ghosts);
  }

  landing(owners, col) {
    for (let r = 0; r < ROWS; r++) if (!owners[r * COLUMNS + col]) return r * COLUMNS + col;
    return -1;
  }
}
