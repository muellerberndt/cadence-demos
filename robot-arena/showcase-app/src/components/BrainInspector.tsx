import { useEffect, useRef } from "react";
import { BrainHistory, drawBrain } from "../arena/brain";
import { Frame, PALETTE, Spec } from "../arena/types";

const W = 1240, H = 470;

export function BrainInspector({ frame, specs, selected }: { frame: Frame | null; specs: Spec[]; selected: number | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const hist = useRef<BrainHistory>({ level: [], reward: [] });
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (selected !== last.current) { hist.current = { level: [], reward: [] }; last.current = selected; }
    const c = ref.current; if (!c || !frame || selected === null || !specs[selected]) return;
    drawBrain(c.getContext("2d")!, W, H, selected, frame, specs[selected], hist.current);
  }, [frame, specs, selected]);
  const spec = selected !== null ? specs[selected] : null;
  return (
    <section className="card p-4 md:p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <h2 className="kicker">Brain inspector</h2>
        {spec && <span className="text-sm font-semibold" style={{ color: PALETTE[selected! % PALETTE.length] }}>{spec.name}</span>}
        {spec && <span className="text-xs text-muted">{spec.chassis} · {spec.parts.map((p) => p.weapon || p.kind).join(", ")} · {spec.inputs.length} senses · {spec.slots.length} motors</span>}
      </div>
      {spec ? (
        <canvas ref={ref} width={W} height={H} className="block w-full h-auto rounded-xl" />
      ) : (
        <p className="text-sm text-muted leading-relaxed max-w-3xl">
          Click a robot in the ring or in the standings to watch its brain, moment by moment: what it senses, how its association cortex settled,
          which command each motor slot chose, and whether the arousal law has it calm (routine, no learning) or aroused (sampling and learning).
        </p>
      )}
    </section>
  );
}
