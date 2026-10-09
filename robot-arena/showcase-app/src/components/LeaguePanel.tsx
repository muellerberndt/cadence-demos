import { PALETTE } from "../arena/types";
import { LeagueRecord } from "../useLeague";

function Spark({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return <span className="text-xs text-muted">first fights</span>;
  const w = 140, h = 28, lo = Math.min(...values) - 5, hi = Math.max(...values) + 5;
  const pts = values.map((v, k) => `${(k / (values.length - 1)) * w},${h - ((v - lo) / (hi - lo)) * h}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} className="w-[140px] h-7"><polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" /></svg>;
}

function Bars({ values, color }: { values: number[]; color: string }) {
  if (!values.length) return <span className="text-xs text-muted">–</span>;
  const w = 140, h = 28, max = Math.max(1, ...values), bw = w / values.length;
  return <svg viewBox={`0 0 ${w} ${h}`} className="w-[140px] h-7">{values.map((v, k) => <rect key={k} x={k * bw + 0.5} y={h - (v / max) * h} width={Math.max(1, bw - 1)} height={(v / max) * h} fill={color} opacity={0.45 + 0.55 * (k + 1) / values.length} />)}</svg>;
}

export function LeaguePanel({ league, roster, manifest, onReset, persisted, describe }: {
  league: LeagueRecord; roster: any[]; manifest: any; onReset: () => void; persisted: string; describe: any;
}) {
  const colors: Record<string, string> = Object.fromEntries(roster.map((r, i) => [r.name, PALETTE[i % PALETTE.length]]));
  const ladder = roster.map((r) => {
    const fights = league.fights.filter((f) => f.results.some((x) => x.name === r.name));
    const places = fights.map((f) => f.results.find((x) => x.name === r.name)!.place);
    const wins = places.filter((p) => p === 1).length;
    const elos = fights.map((f) => f.elo_after[r.name]);
    const dealt = fights.map((f) => f.results.find((x) => x.name === r.name)!.dealt);
    const brain = describe?.robots?.[r.name]?.brain;
    return { ...r, eloNow: league.elo[r.name] ?? 1000, fightsHere: fights.length, wins, meanPlace: places.length ? places.reduce((a, b) => a + b, 0) / places.length : null, elos, dealt, brain };
  }).sort((a, b) => b.eloNow - a.eloNow);
  const evo = manifest?.league?.evolution || [];
  // getting better: league-wide damage per fight, early against late
  const perFight = league.fights.map((f) => f.results.reduce((a, r) => a + r.dealt, 0) / Math.max(1, f.results.length));
  const k = Math.max(1, Math.floor(perFight.length / 3));
  const early = perFight.length >= 2 ? perFight.slice(0, k).reduce((a, b) => a + b, 0) / k : null;
  const late = perFight.length >= 2 ? perFight.slice(-k).reduce((a, b) => a + b, 0) / k : null;
  const sweeps = league.fights.reduce((a, f) => a + f.results.reduce((b, r) => b + r.learning_sweeps, 0), 0);
  const calmLate = perFight.length ? 1 - league.fights.slice(-k).reduce((a, f) => a + f.results.reduce((b, r) => b + r.aroused_share, 0) / f.results.length, 0) / k : null;
  const lineages = Array.from(new Set(evo.flatMap((g: any) => Object.keys(g.lineages)))) as string[];
  const lcol: Record<string, string> = { Dozer: "#f6e05e", Mantis: "#f6ad55", Crab: "#b794f4" };
  return (
    <section className="card p-4 md:p-5 space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="kicker">The league in this browser</h2>
        <span className="text-xs text-muted">{league.fights.length} fights here · {(league.totalMoments / 1000).toFixed(0)}k brain moments lived here · brains {persisted === "fresh" ? "as they arrived" : persisted === "restored" ? "restored from your last visit" : "saved after the last fight"}</span>
        <button className="btn ml-auto text-xs" onClick={onReset}>Reset the brains to how they arrived</button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {[
          [league.fights.length, "fights in this browser"],
          [(league.totalMoments / 1000).toFixed(0) + "k", "brain moments lived here"],
          [sweeps >= 1000 ? (sweeps / 1000).toFixed(0) + "k" : sweeps, "learning sweeps so far"],
          [early === null ? "–" : `${early.toFixed(0)} → ${late!.toFixed(0)}`, "damage per robot per fight, first third → last third"],
          [calmLate === null ? "–" : `${Math.round(100 * calmLate)}%`, "calm moments, last fights"],
        ].map(([v, l], i) => <div key={i} className="rounded-xl border border-line px-3 py-2"><b className="block text-lg tnum">{v as any}</b><span className="text-[11px] text-muted leading-tight block">{l as any}</span></div>)}
      </div>
      <div className="overflow-auto">
        <table className="w-full text-sm tnum min-w-[720px]">
          <thead><tr className="text-muted text-xs"><th className="text-left font-medium py-1">#</th><th className="text-left font-medium">robot</th><th className="text-left font-medium">body</th><th className="text-right font-medium">elo here</th><th className="text-right font-medium">fights</th><th className="text-right font-medium">wins</th><th className="text-right font-medium">mean place</th><th className="text-left font-medium pl-4">elo over your fights</th><th className="text-left font-medium pl-4">damage dealt per fight</th><th className="text-right font-medium">arrived with</th></tr></thead>
          <tbody>
            {ladder.map((r, k) => (
              <tr key={r.name} className="border-t border-line">
                <td className="py-2">{k + 1}</td>
                <td className="font-semibold"><span className="inline-block w-2.5 h-2.5 rounded-sm mr-2" style={{ background: colors[r.name] }} />{r.name}</td>
                <td className="text-muted text-xs">{r.blueprint.chassis} · {r.blueprint.parts.map((p: any) => p.weapon || p.kind).join(", ")}</td>
                <td className="text-right">{r.eloNow.toFixed(0)}</td>
                <td className="text-right">{r.fightsHere}</td>
                <td className="text-right">{r.wins}</td>
                <td className="text-right">{r.meanPlace === null ? "–" : r.meanPlace.toFixed(2)}</td>
                <td className="pl-4"><Spark values={r.elos} color={colors[r.name]} /></td>
                <td className="pl-4"><Bars values={r.dealt} color={colors[r.name]} /></td>
                <td className="text-right text-xs text-muted">gen {r.generation} of the {r.lineage} line · {r.fights} fights, elo {Math.round(r.elo)} · {r.brain ? `${(r.brain.age / 1000).toFixed(0)}k moments lived` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid md:grid-cols-2 gap-5">
        <div>
          <h3 className="kicker mb-2">Where they come from</h3>
          <p className="text-sm text-muted leading-relaxed">
            Three champions of a laptop league (Mantis, Dozer, Crab) founded lineages on a 192-vCPU machine for one hour: 189 mutants of their bodies and
            genes were born with newborn brains, raised in a nursery, and fought 32 royales at a time; every generation the weakest third retired.
            Four generations and 3,840 royales later these six were the best of 192. Their mutations: {roster.slice(0, 6).map((r) => `${r.name}: ${(r.mutations || []).join("; ") || "a copy"}`).join(" · ")}.
          </p>
        </div>
        <div>
          <h3 className="kicker mb-2">Who dominated, generation by generation</h3>
          <div className="flex gap-2 items-end h-28">
            {evo.map((g: any) => {
              const total = Object.values(g.lineages as Record<string, number>).reduce((a: number, b: number) => a + b, 0) || 1;
              return (
                <div key={g.generation} className="flex-1 flex flex-col-reverse rounded overflow-hidden h-full" title={`generation ${g.generation}: ${Object.entries(g.lineages).map(([l, c]) => `${l} ${c}`).join(", ")}; podium ${g.podium.join(", ")}`}>
                  {lineages.map((l) => <div key={l} style={{ height: `${100 * ((g.lineages[l] || 0) / total)}%`, background: lcol[l] || "#888" }} />)}
                </div>
              );
            })}
          </div>
          <div className="flex gap-4 mt-2 text-xs text-muted">{lineages.map((l) => <span key={l}><i className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5 align-[-1px]" style={{ background: lcol[l] || "#888" }} />{l} line</span>)}<span>generations 1 to {evo.length}; the Dozer line took 80 % of the places first and lost ground every generation after</span></div>
        </div>
      </div>
    </section>
  );
}
