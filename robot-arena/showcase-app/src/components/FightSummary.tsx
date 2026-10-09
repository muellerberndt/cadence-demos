import { Result } from "../arena/types";

export function FightSummary({ results, eloDelta, onNext, colors, countdown, autoContinue, onToggleAuto }: {
  results: Result[]; eloDelta: Record<string, number>; onNext: () => void; colors: Record<string, string>;
  countdown: number | null; autoContinue: boolean; onToggleAuto: () => void;
}) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-[#0b0e14]/70 backdrop-blur-sm rounded-2xl">
      <div className="card p-5 w-[min(560px,92%)] shadow-glow">
        <div className="kicker mb-1">Fight over</div>
        <h3 className="text-xl font-bold mb-3">{results[0].name} takes the ring</h3>
        <table className="w-full text-sm tnum">
          <thead><tr className="text-muted text-xs"><th className="text-left font-medium py-1">place</th><th className="text-left font-medium">robot</th><th className="text-right font-medium">dealt</th><th className="text-right font-medium">taken</th><th className="text-right font-medium">learning</th><th className="text-right font-medium">elo</th></tr></thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.name} className="border-t border-line">
                <td className="py-1.5">#{r.place}</td>
                <td><span className="inline-block w-2 h-2 rounded-sm mr-2" style={{ background: colors[r.name] }} />{r.name}</td>
                <td className="text-right">{r.dealt.toFixed(0)}</td>
                <td className="text-right">{r.taken.toFixed(0)}</td>
                <td className="text-right">{Math.round(100 * r.aroused_share)}% · {(r.learning_sweeps / 1000).toFixed(1)}k</td>
                <td className={`text-right ${eloDelta[r.name] >= 0 ? "text-hp" : "text-hplow"}`}>{eloDelta[r.name] >= 0 ? "+" : ""}{eloDelta[r.name].toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-muted mt-3">Every brain learned from this fight and was saved in this browser. The next fight starts with what they just learned.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" onClick={onNext}>{countdown !== null ? `Next fight in ${countdown} s` : "Next fight"}</button>
          <button className={`btn ${autoContinue ? "btn-active" : ""}`} onClick={onToggleAuto}>{autoContinue ? "Continuous rounds: on" : "Continuous rounds: off"}</button>
        </div>
      </div>
    </div>
  );
}
