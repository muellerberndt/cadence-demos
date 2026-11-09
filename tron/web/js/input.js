// The player's steering. Requests are absolute compass directions (0 N, 1 E, 2 S, 3 W) from
// the keys or a swipe, or relative turns from the on-screen buttons. Up to two turns queue, so
// a quick double turn works; a request to reverse, or to keep the current direction, is
// ignored. Each tick takes one queued turn and returns the relative move the host expects:
// 0 left, 1 straight, 2 right.

const KEYS = {
  ArrowUp: 0, KeyW: 0, ArrowRight: 1, KeyD: 1, ArrowDown: 2, KeyS: 2, ArrowLeft: 3, KeyA: 3,
};

export class Steering {
  constructor() {
    this.heading = 0;
    this.queue = [];
    this.enabled = false;
  }

  reset(heading) {
    this.heading = heading;
    this.queue = [];
  }

  sync(heading) {
    // The host's heading after a tick; queued turns stay planned from it.
    this.heading = heading;
  }

  planned() {
    return this.queue.length ? this.queue[this.queue.length - 1] : this.heading;
  }

  request(direction) {
    if (!this.enabled) return;
    const base = this.planned();
    if (direction === base || direction === (base + 2) % 4) return;
    if (this.queue.length >= 2) return;
    this.queue.push(direction);
  }

  turn(side) {
    // side -1 left, +1 right, relative to where the cycle will be heading.
    this.request((this.planned() + side + 4) % 4);
  }

  next() {
    if (!this.queue.length) return 1;
    const direction = this.queue.shift();
    const rel = (direction - this.heading + 4) % 4;
    this.heading = direction;
    if (rel === 1) return 2;
    if (rel === 3) return 0;
    return 1;
  }
}

export function bindSwipe(element, steering, { onTap }) {
  let start = null;
  element.addEventListener("pointerdown", (event) => {
    start = { x: event.clientX, y: event.clientY, id: event.pointerId, done: false };
  });
  element.addEventListener("pointermove", (event) => {
    if (!start || start.id !== event.pointerId || start.done) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.hypot(dx, dy) < 22) return;
    steering.request(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 1 : 3) : (dy > 0 ? 2 : 0));
    // Allow a second swipe in the same touch: restart from here.
    start = { x: event.clientX, y: event.clientY, id: event.pointerId, done: false };
    start.moved = true;
  });
  const end = (event) => {
    if (start && start.id === event.pointerId && !start.moved) onTap();
    start = null;
  };
  element.addEventListener("pointerup", end);
  element.addEventListener("pointercancel", () => { start = null; });
}
