import { MutableRefObject, useEffect, useRef } from "react";
import { Anatomy, BRAIN_H, BRAIN_W, BrainView, Inspect } from "../arena/brainview";
import { Frame, PALETTE, Spec } from "../arena/types";
import { explain } from "../explain";

// The selected robot's brain, drawn from its real state every moment (see arena/brainview.ts).
// Every region and part carries a spot of the shared explanations, laid out again when the
// canvas changes size.
export function BrainInspector({ specs, selected, anatomy, inspectQueue, history }: {
  specs: Spec[]; selected: number | null; anatomy: Anatomy | null;
  inspectQueue: MutableRefObject<Inspect[]>; history: MutableRefObject<Map<number, Frame>>;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const view = useRef<BrainView | null>(null);
  const spec = selected !== null ? specs[selected] : null;

  const layoutSpots = () => {
    const X = explain(), w = wrap.current, c = ref.current, v = view.current;
    if (!X || !w || !c) return;
    X.clearSpots(w);
    if (!v || !c.clientWidth) return;
    const k = c.clientWidth / BRAIN_W;
    for (const p of v.parts()) X.spot(w, { x: p.x * k, y: p.y * k, w: p.w * k, h: p.h * k }, p.text, { title: p.title, mark: p.mark });
  };

  useEffect(() => {
    const canvas = ref.current; if (!canvas || !wrap.current) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = BRAIN_W * dpr; canvas.height = BRAIN_H * dpr;
    const v = new BrainView(canvas, wrap.current); view.current = v;
    (window as any).__brainView = v; // frame time and frame count, read by check_page.mjs
    let raf = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const q = inspectQueue.current;
      while (q.length) v.push(q.shift()!);
      v.draw(now);
    };
    raf = requestAnimationFrame(loop);
    const ro = new ResizeObserver(() => layoutSpots());
    ro.observe(canvas);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); view.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec !== null, inspectQueue]);

  useEffect(() => {
    if (view.current && anatomy && spec && anatomy.name === spec.name) {
      view.current.setAnatomy(anatomy, spec);
      view.current.setHistory((t) => history.current.get(t), selected!);
      layoutSpots();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anatomy, spec, selected, history]);

  return (
    <section className="card p-4 md:p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <h2 className="kicker" data-explain="The selected robot's brain, live: every dot is one of its neurons at the activity it settled to this moment, read from the brain in your browser. Regions are named for the role they play. Point at a region or its question mark for what it does." data-explain-title="Brain inspector">Brain inspector</h2>
        {spec && <span className="text-sm font-semibold" style={{ color: PALETTE[selected! % PALETTE.length] }}>{spec.name}</span>}
        {spec && <span className="text-xs text-muted">{spec.chassis} · {spec.parts.map((p) => p.weapon || p.kind).join(", ")} · {spec.inputs.length} senses · {spec.slots.length} motors</span>}
      </div>
      {spec ? (
        <div ref={wrap} className="relative">
          <canvas ref={ref} className="block w-full h-auto rounded-xl" style={{ aspectRatio: `${BRAIN_W} / ${BRAIN_H}`, background: "#070a12" }} />
        </div>
      ) : (
        <p className="text-sm text-muted">Click a robot in the ring or in the standings to watch its brain, moment by moment.</p>
      )}
    </section>
  );
}
