// The brain explainer's small interactions: the regions that light their routes, the lesson's two
// modes, the sleep curve, the chart's tooltips and the line naming the brains the page carries.
(() => {
  'use strict';
  const root = document.documentElement;
  try { if (window.self !== window.top) root.classList.add('embedded'); } catch (e) { root.classList.add('embedded'); }

  const ready = (fn) => (document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', fn) : fn());

  ready(() => {
    // --- figure 1: point at a part to light its routes --------------------------------------------
    const net = document.querySelector('.xp-net');
    const info = document.getElementById('xp-net-info');
    if (net && info) {
      const nodes = [...net.querySelectorAll('.nd')];
      const routes = [...net.querySelectorAll('.rt[data-a]')];
      const fallback = info.innerHTML;
      let pinned = null;
      const show = (id) => {
        if (!id) {
          net.classList.remove('focusing');
          for (const r of routes) r.classList.remove('lit');
          for (const n of nodes) n.classList.remove('lit', 'on');
          info.innerHTML = fallback;
          return;
        }
        const near = new Set([id]);
        for (const r of routes) {
          const lit = r.dataset.a === id || r.dataset.b === id;
          r.classList.toggle('lit', lit);
          if (lit) { near.add(r.dataset.a); near.add(r.dataset.b); }
        }
        for (const n of nodes) {
          n.classList.toggle('lit', near.has(n.dataset.id));
          n.classList.toggle('on', n.dataset.id === id);
        }
        net.classList.add('focusing');
        const node = nodes.find((n) => n.dataset.id === id);
        info.innerHTML = node ? node.dataset.info : fallback;
      };
      for (const n of nodes) {
        n.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') show(n.dataset.id); });
        n.addEventListener('focus', () => show(n.dataset.id));
        n.addEventListener('click', (e) => {
          e.stopPropagation();
          pinned = pinned === n.dataset.id ? null : n.dataset.id;
          show(pinned);
        });
        n.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pinned = pinned === n.dataset.id ? null : n.dataset.id; show(pinned); }
          if (e.key === 'Escape') { pinned = null; show(null); n.blur(); }
        });
      }
      net.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') show(pinned); });
      net.addEventListener('click', () => { pinned = null; show(null); });
      net.addEventListener('focusout', (e) => { if (!net.contains(e.relatedTarget)) show(pinned); });
    }

    // --- figure 7: the lesson after a pistachio, or after a correction ------------------------------
    for (const fig of document.querySelectorAll('.xp-lesson')) {
      const buttons = [...fig.querySelectorAll('.xp-switch button')];
      const note = fig.querySelector('[data-note]');
      const notes = { pistachio: fig.dataset.notePistachio || '', correction: fig.dataset.noteCorrection || '' };
      for (const b of buttons) {
        b.addEventListener('click', () => {
          fig.dataset.mode = b.dataset.mode;
          for (const o of buttons) o.setAttribute('aria-pressed', String(o === b));
          if (note) note.textContent = notes[b.dataset.mode] || '';
        });
      }
    }

    // --- figure 8: lessons push neurons to the ceiling; sleep halves the efficacies -----------------
    const sleepSvg = document.getElementById('xp-sleep');
    const dots = document.getElementById('xp-sleep-dots');
    const slider = document.getElementById('xp-scale');
    const readout = document.getElementById('xp-sleep-readout');
    if (sleepSvg && dots && slider && readout) {
      const NS = 'http://www.w3.org/2000/svg';
      const base = [0.4, 0.8, 1.2, 1.6, 2.0, 2.4, 2.9, 3.4];
      const X = (v) => 50 + (Math.min(v, 8) + 2) * 39;
      const Y = (a) => 200 - ((a + 0.15) / 1.2) * 180;
      const act = (v) => (v >= 0 ? Math.tanh(v / 2) : 0.1 * Math.tanh(v / 2));
      const slope = (v) => { const t = Math.tanh(v / 2); return v >= 0 ? 0.5 * (1 - t * t) : 0.05 * (1 - t * t); };
      const parts = base.map(() => {
        const tan = document.createElementNS(NS, 'line');
        tan.setAttribute('class', 'tan');
        tan.setAttribute('stroke-width', '3');
        tan.setAttribute('stroke-linecap', 'round');
        const dot = document.createElementNS(NS, 'circle');
        dot.setAttribute('class', 'dot');
        dot.setAttribute('r', '5.5');
        dot.setAttribute('stroke', '#10191d');
        dot.setAttribute('stroke-width', '1.5');
        dots.append(tan, dot);
        return { tan, dot };
      });
      let scale = 2.56;
      const draw = () => {
        let top = 0, room = 0;
        base.forEach((b, i) => {
          const v = b * scale, a = act(v), k = slope(v);
          const x = X(v), y = Y(a);
          const hot = a > 0.98;
          top += hot ? 1 : 0;
          room += k / 0.5;
          const { tan, dot } = parts[i];
          dot.setAttribute('cx', x.toFixed(1));
          dot.setAttribute('cy', y.toFixed(1));
          dot.setAttribute('fill', hot ? '#f2b33d' : '#4fe3e8');
          const dx = 0.32 * 39, dy = k * 0.32 * 150;
          tan.setAttribute('x1', (x - dx).toFixed(1)); tan.setAttribute('y1', (y + dy).toFixed(1));
          tan.setAttribute('x2', (x + dx).toFixed(1)); tan.setAttribute('y2', (y - dy).toFixed(1));
          tan.setAttribute('stroke', hot ? 'rgba(242,179,61,0.55)' : 'rgba(95,208,142,0.85)');
        });
        slider.value = String(Math.log2(scale));
        readout.innerHTML = `efficacies <b>×${scale.toFixed(2)}</b> · at the ceiling: <b>${top} of ${base.length}</b> · room to learn: <b>${Math.round((100 * room) / base.length)}%</b> of the steepest`;
      };
      const set = (s) => { scale = Math.min(4, Math.max(0.25, s)); draw(); };
      document.getElementById('xp-lessons')?.addEventListener('click', () => set(scale * 1.6));
      document.getElementById('xp-sleep-btn')?.addEventListener('click', () => set(scale * 0.5));
      document.getElementById('xp-reset')?.addEventListener('click', () => set(2.56));
      slider.addEventListener('input', () => set(2 ** Number(slider.value)));
      draw();
    }

    // --- figure 9: the chart's tooltips ---------------------------------------------------------------
    const chart = document.getElementById('xp-chart');
    if (chart) {
      const tip = document.createElement('div');
      tip.className = 'xp-tip';
      tip.hidden = true;
      document.body.append(tip);
      const place = (e) => { tip.style.left = `${Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8)}px`; tip.style.top = `${e.clientY - tip.offsetHeight - 10}px`; };
      for (const h of chart.querySelectorAll('.hit')) {
        h.addEventListener('pointerenter', (e) => { tip.innerHTML = h.getAttribute('data-tip') || ''; tip.hidden = false; place(e); });
        h.addEventListener('pointermove', place);
        h.addEventListener('pointerleave', () => { tip.hidden = true; });
      }
    }

    // --- the brains the page carries (their version files beside the brains) -------------------------
    const line = document.getElementById('xp-brains');
    if (line && window.fetch) {
      const files = ['pack/trained/version.json', 'pack/trained-names/version.json'];
      Promise.all(files.map((f) => fetch(f).then((r) => (r.ok ? r.json() : null)).catch(() => null))).then((found) => {
        const names = found.filter(Boolean).map((v) => `${v.label || v.step || 'a trained brain'}, founder ${v.founder}`);
        if (names.length) line.textContent = `The page carries: ${names.join('; ')}.`;
      }).catch(() => {});
    }
  });
})();
