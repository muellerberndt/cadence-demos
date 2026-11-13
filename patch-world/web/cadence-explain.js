/* Cadence demos: small explanations, the same on every demo page.
 *
 * Any element with data-explain="..." gets a small question mark and a card. The card opens when
 * the pointer rests on the element 140 ms, stays while the pointer is on the element or inside the
 * card, and closes 450 ms after the pointer has left both; a part under the card on show opens
 * after a rest of 400 ms. Keyboard focus opens it at once; a tap
 * or a click on the question mark keeps it open until a click elsewhere or Escape. The card lets
 * the pointer through to what lies under it until it is kept open.
 *
 *   <button data-explain="Starts a new game.">New game</button>
 *   <div data-explain="..." data-explain-title="The map" data-explain-mark="none">...</div>
 *
 * data-explain-title gives the card a title; data-explain-mark="none" leaves the question mark out
 * (the element itself is the mark, as a brain region drawn on a canvas is).
 *
 * A canvas draws regions the DOM does not know. CadenceExplain.spot(container, box, text, opts)
 * puts an invisible spot over a box of the container (pixels from its top left); opts.title,
 * opts.mark ('none' or a corner: 'top-right', the default), opts.id. CadenceExplain.clearSpots(container)
 * removes the spots of a container, for a page that lays its canvas out again.
 *
 * A page shown inside the demos site (in a frame) gets the class "embedded" on <html>; elements
 * with data-standalone show only on the page opened by itself, since the site shows the title,
 * what the demo shows and what to try. A link with data-help opens the demo's help page.
 */
(function () {
  'use strict';
  if (window.CadenceExplain) return;
  var root = document.documentElement;
  try { if (window.self !== window.top) root.classList.add('embedded'); } catch (e) { root.classList.add('embedded'); }

  var OPEN_MS = 140, COVERED_MS = 400, CLOSE_MS = 450, MARGIN = 6;
  var card = null, owner = null, kept = false, timerOpen = 0, timerClose = 0;
  var pending = null; // the part whose card opens when its timer runs out

  function ensureCard() {
    if (card) return card;
    card = document.createElement('div');
    card.className = 'cx-card';
    card.setAttribute('role', 'tooltip');
    card.hidden = true;
    document.body.appendChild(card);
    return card;
  }

  function fill(el) {
    var c = ensureCard();
    c.textContent = '';
    var title = el.getAttribute('data-explain-title');
    if (title) { var h = document.createElement('b'); h.className = 'cx-title'; h.textContent = title; c.appendChild(h); }
    String(el.getAttribute('data-explain') || '').split(/\n\s*\n/).forEach(function (para) {
      var p = document.createElement('p'); p.textContent = para.trim(); c.appendChild(p);
    });
  }

  function place(el) {
    var c = card, r = el.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
    c.style.left = '0px'; c.style.top = '0px';
    var w = c.offsetWidth, h = c.offsetHeight;
    var below = r.bottom + 8, above = r.top - h - 8;
    var top = below + h <= vh - 4 || above < 4 ? below : above;
    var left = Math.min(Math.max(4, r.left + r.width / 2 - w / 2), vw - w - 4);
    c.style.left = Math.round(left) + 'px';
    c.style.top = Math.round(Math.min(Math.max(4, top), vh - h - 4)) + 'px';
  }

  function open(el, keep) {
    clearTimeout(timerOpen); clearTimeout(timerClose); timerOpen = timerClose = 0; pending = null;
    owner = el; kept = !!keep;
    fill(el);
    card.hidden = false;
    card.classList.toggle('kept', kept);
    place(el);
    el.setAttribute('aria-describedby', 'cx-card');
    card.id = 'cx-card';
  }

  function close() {
    clearTimeout(timerOpen); clearTimeout(timerClose); timerOpen = timerClose = 0;
    if (owner) owner.removeAttribute('aria-describedby');
    owner = null; kept = false;
    if (card) { card.hidden = true; card.classList.remove('kept'); }
  }

  function inCard(ev) {
    if (!card || card.hidden || !ev) return false;
    var r = card.getBoundingClientRect();
    return ev.clientX >= r.left - MARGIN && ev.clientX <= r.right + MARGIN && ev.clientY >= r.top - MARGIN && ev.clientY <= r.bottom + MARGIN;
  }

  // A part under the card on show opens after a longer rest: a pointer that only crosses the card
  // leaves it as it is, a pointer that rests on the covered part gets that part's card.
  function soonOpen(el, ev) {
    if (kept || owner === el) { clearTimeout(timerClose); timerClose = 0; return; }
    clearTimeout(timerClose); timerClose = 0;
    clearTimeout(timerOpen);
    pending = el;
    timerOpen = setTimeout(function () { timerOpen = 0; pending = null; if (!kept) open(el, false); }, inCard(ev) ? COVERED_MS : OPEN_MS);
  }

  function soonClose() {
    clearTimeout(timerOpen); timerOpen = 0; pending = null;
    if (kept || !owner || timerClose) return;
    timerClose = setTimeout(function () { timerClose = 0; if (!kept) close(); }, CLOSE_MS);
  }

  function addMark(el, where) {
    var mark = document.createElement('span');
    mark.className = 'cx-q' + (where ? ' cx-at ' + where : '');
    mark.setAttribute('aria-hidden', 'true');
    mark.textContent = '?';
    mark.addEventListener('click', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      if (kept && owner === el) close(); else open(el, true);
    });
    el.appendChild(mark);
    return mark;
  }

  function bind(el) {
    if (el.__cx) return;
    el.__cx = true;
    if (el.getAttribute('data-explain-mark') !== 'none') addMark(el, el.getAttribute('data-explain-mark') === 'corner' ? 'top-right' : '');
    el.addEventListener('pointerenter', function (ev) { if (ev.pointerType === 'mouse') soonOpen(el, ev); });
    el.addEventListener('pointerleave', function (ev) { if (ev.pointerType === 'mouse' && !inCard(ev)) soonClose(); });
    el.addEventListener('focus', function () { if (!kept) open(el, false); });
    el.addEventListener('blur', function () { if (!kept && owner === el) soonClose(); });
    if (el.classList.contains('cx-spot')) {
      el.addEventListener('click', function (ev) { ev.stopPropagation(); if (kept && owner === el) close(); else open(el, true); });
    }
  }

  function scan(scope) {
    var list = (scope || document).querySelectorAll('[data-explain]');
    for (var i = 0; i < list.length; i++) bind(list[i]);
  }

  function spot(container, box, text, opts) {
    opts = opts || {};
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    var el = document.createElement('span');
    el.className = 'cx-spot';
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.setAttribute('data-explain', text);
    if (opts.title) { el.setAttribute('data-explain-title', opts.title); el.setAttribute('aria-label', 'Explain ' + opts.title); }
    if (opts.id) el.setAttribute('data-spot', opts.id);
    el.style.left = Math.round(box.x) + 'px'; el.style.top = Math.round(box.y) + 'px';
    el.style.width = Math.round(box.w) + 'px'; el.style.height = Math.round(box.h) + 'px';
    el.setAttribute('data-explain-mark', 'none');
    container.appendChild(el);
    bind(el);
    if (opts.mark !== 'none') addMark(el, opts.mark || 'top-right');
    return el;
  }

  function clearSpots(container) {
    var list = container.querySelectorAll('.cx-spot');
    for (var i = 0; i < list.length; i++) { if (list[i] === owner) close(); list[i].remove(); }
  }

  document.addEventListener('pointermove', function (ev) {
    if (ev.pointerType !== 'mouse' || kept || !owner) return;
    if (inCard(ev)) { clearTimeout(timerClose); timerClose = 0; return; }
    // the pointer on a part whose card is about to open: that card takes over, nothing closes
    if (pending && pending.contains(ev.target)) return;
    if (!owner.contains(ev.target)) soonClose();
  }, { passive: true });
  document.addEventListener('pointerdown', function (ev) {
    if (kept && card && !card.contains(ev.target) && !(owner && owner.contains(ev.target))) close();
  });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && owner) close(); });
  window.addEventListener('scroll', function () { if (owner && !kept) close(); else if (owner) place(owner); }, true);
  window.addEventListener('resize', function () { if (owner) place(owner); });

  function start() { ensureCard(); scan(document); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  window.CadenceExplain = { scan: scan, spot: spot, clearSpots: clearSpots, open: function (el) { open(el, true); }, close: close };
})();
