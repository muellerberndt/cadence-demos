import { useEffect, useRef } from "react";
import { DrawState, drawArena, newDrawState, pickRobot } from "../arena/draw";
import { Frame, Spec } from "../arena/types";

const W = 1000, H = 640, RADIUS = 10;

export function ArenaCanvas({ frame, specs, frameIndex, selected, onSelect, dealt }: {
  frame: Frame | null; specs: Spec[]; frameIndex: number; selected: number | null; onSelect: (i: number | null) => void; dealt: number[];
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const state = useRef<DrawState>(newDrawState(0));
  useEffect(() => { state.current = newDrawState(specs.length); }, [specs]);
  useEffect(() => {
    const c = ref.current; if (!c || !frame || !specs.length) return;
    const ctx = c.getContext("2d")!;
    drawArena(ctx, W, H, RADIUS, frame, specs, state.current, frameIndex, selected, dealt);
  }, [frame, specs, frameIndex, selected, dealt]);
  return (
    <canvas
      ref={ref} width={W} height={H} className="block w-full h-auto cursor-crosshair"
      onClick={(e) => {
        if (!frame) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const px = (e.clientX - rect.left) * W / rect.width, py = (e.clientY - rect.top) * H / rect.height;
        const hit = pickRobot(W, H, RADIUS, frame, px, py);
        onSelect(hit === null ? null : hit === selected ? null : hit);
      }}
    />
  );
}
