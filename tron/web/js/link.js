// The page's line to the brain worker (js/worker.js): one promise per request, answered in order.

export class Link {
  constructor(onStatus = () => {}) {
    this.worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
    this.waiting = new Map();
    this.rid = 1;
    this.worker.onmessage = (event) => {
      const data = event.data;
      if (data.status) { onStatus(data.status); return; }
      const entry = this.waiting.get(data.rid);
      if (!entry) return;
      this.waiting.delete(data.rid);
      if (data.error) entry.reject(new Error(data.error));
      else entry.resolve(data.result);
    };
    this.worker.onerror = (event) => {
      const error = new Error(event.message || "the brain worker failed");
      for (const entry of this.waiting.values()) entry.reject(error);
      this.waiting.clear();
    };
  }

  call(op, payload = {}) {
    return new Promise((resolve, reject) => {
      const rid = this.rid++;
      this.waiting.set(rid, { resolve, reject });
      this.worker.postMessage({ rid, op, ...payload });
    });
  }
}
