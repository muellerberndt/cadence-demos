import { MutableRefObject, useEffect, useRef } from "react";
import { Anatomy, BRAIN_H, BRAIN_W, BrainView, Inspect } from "../arena/brainview";
import { Frame, PALETTE, Spec } from "../arena/types";

// The selected robot's brain, drawn from its real state every moment (see arena/brainview.ts).
export function BrainInspector({ specs, selected, anatomy, inspectQueue, history }: {
  specs: Spec[]; selected: number | null; anatomy: Anatomy | null;
  inspectQueue: MutableRefObject<Inspect[]>; history: MutableRefObject<Map<number, Frame>>;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const view = useRef<BrainView | null>(null);
  const spec = selected !== null ? specs[selected] : null;

  useEffect(() => {
    const canvas = ref.current; if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = BRAIN_W * dpr; canvas.height = BRAIN_H * dpr;
    const v = new BrainView(canvas); view.current = v;
    (window as any).__brainView = v; // frame time and frame count, read by check_page.mjs
    let raf = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const q = inspectQueue.current;
      while (q.length) v.push(q.shift()!);
      v.draw(now);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); view.current = null; };
  }, [spec !== null, inspectQueue]);

  useEffect(() => {
    if (view.current && anatomy && spec && anatomy.name === spec.name) {
      view.current.setAnatomy(anatomy, spec);
      view.current.setHistory((t) => history.current.get(t), selected!);
    }
  }, [anatomy, spec, selected, history]);

  return (
    <section className="card p-4 md:p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <h2 className="kicker">Brain inspector</h2>
        {spec && <span className="text-sm font-semibold" style={{ color: PALETTE[selected! % PALETTE.length] }}>{spec.name}</span>}
        {spec && <span className="text-xs text-muted">{spec.chassis} · {spec.parts.map((p) => p.weapon || p.kind).join(", ")} · {spec.inputs.length} senses · {spec.slots.length} motors</span>}
      </div>
      {spec ? (
        <>
          <canvas ref={ref} className="block w-full h-auto rounded-xl" style={{ aspectRatio: `${BRAIN_W} / ${BRAIN_H}`, background: "#070a12" }} />
          <p className="text-xs text-muted leading-relaxed mt-2 max-w-4xl">
            Every dot is a neuron of this robot's Cadence brain at its settled activation; regions are named for the role their population plays.
            Fibres are its strongest synapses, lit by weight × activity (warm excites, cool inhibits). Every eighth moment the act's settle replays sweep by sweep.
            Gold or blue from the midbrain is the critic's reward prediction error; synapses a learning step changed flash; the hippocampus row is the recall memory, lit where a moment reads it.
            Hover a neuron or a region.
          </p>
        </>
      ) : (
        <p className="text-sm text-muted leading-relaxed max-w-3xl">
          Click a robot in the ring or in the standings to watch its brain, moment by moment: its senses entering the cortex, the settle spreading through it,
          the command each motor slot chose, the critic's prediction error, arousal switching learning on, and the synapses that learning changes.
        </p>
      )}
    </section>
  );
}
