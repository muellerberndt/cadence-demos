import { Frame, MODE_NAME, PALETTE, Spec, THEME, modeColor } from "../arena/types";

export function Standings({ frame, specs, selected, onSelect, tallies, elo }: {
  frame: Frame | null; specs: Spec[]; selected: number | null; onSelect: (i: number | null) => void;
  tallies: { dealt: number[]; aroused: number[]; alive: number[]; sweeps: number[] }; elo: Record<string, number>;
}) {
  if (!frame || !specs.length) return null;
  const rows = specs.map((s, i) => ({ i, s, hp: frame.robots[i][3], mode: frame.robots[i][4] }))
    .sort((a, b) => Number(a.mode === 9) - Number(b.mode === 9) || b.hp - a.hp);
  return (
    <div className="space-y-1.5">
      {rows.map(({ i, s, hp, mode }) => {
        const la = tallies.alive[i] || 0, ar = tallies.aroused[i] || 0, sw = tallies.sweeps[i] || 0;
        const share = Math.max(0, hp / s.hp);
        return (
          <button key={s.name} onClick={() => onSelect(selected === i ? null : i)}
            className={`w-full text-left rounded-xl px-3 py-2.5 border transition-colors ${selected === i ? "border-aroused/70 bg-panel2" : "border-transparent hover:bg-panel2/70"}`}>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="font-semibold text-sm truncate">{s.name}</span>
              <span className="text-[11px] text-muted truncate">{s.lineage ? `${s.lineage} line` : s.chassis}</span>
              <span className="ml-auto text-xs tnum text-muted">{Math.round(elo[s.name] ?? 1000)}</span>
            </div>
            <div className="mt-1.5 h-1.5 rounded bg-line overflow-hidden">
              <div className="h-full" style={{ width: `${100 * share}%`, background: mode === 9 ? THEME.dead : share > 0.35 ? THEME.hp : THEME.hpLow }} />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted tnum">
              <span className="inline-flex items-center gap-1.5"><i className="inline-block w-2 h-2 rounded-full" style={{ background: modeColor(mode) }} />{MODE_NAME[mode]}</span>
              <span>hp {hp.toFixed(0)}</span>
              <span>dealt {(tallies.dealt[i] || 0).toFixed(0)}</span>
              {la > 0 && <span>learning {Math.round(100 * ar / la)}% · {sw >= 1000 ? (sw / 1000).toFixed(1) + "k" : sw} sweeps</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}
