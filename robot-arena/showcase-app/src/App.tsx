import { useMemo } from "react";
import { ArenaCanvas } from "./components/ArenaCanvas";
import { BrainInspector } from "./components/BrainInspector";
import { FightSummary } from "./components/FightSummary";
import { LeaguePanel } from "./components/LeaguePanel";
import { Standings } from "./components/Standings";
import { PALETTE } from "./arena/types";
import { useLeague } from "./useLeague";

export default function App() {
  const L = useLeague();
  const colors = useMemo(() => Object.fromEntries(L.specs.map((s, i) => [s.name, PALETTE[i % PALETTE.length]])), [L.specs]);
  const seconds = (L.frameIndex * 0.05).toFixed(1);
  return (
    <div className="min-h-screen">
      <header className="max-w-[1400px] mx-auto px-4 pt-6 pb-3 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="kicker">Cadence · continuing brains in the ring</div>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">Cadence Showcase League</h1>
        </div>
        <p className="text-sm text-muted max-w-xl leading-relaxed">
          The best-licensed survivors of lineage evolution on a 192-CPU machine, each with one continuing Cadence brain wired to every motor, fight round after round <em className="text-ink not-italic font-medium">live, in your browser</em>.
          Every brain learns from every fight; their brains are saved here after each one and come back the next time you open the page. Watch the damage per fight and the ladder move.
        </p>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted tnum">
          {L.ready && <span className={`px-2 py-1 rounded-lg border ${L.playing ? "border-aroused/60 text-aroused" : "border-line"}`}>{L.playing ? "live" : "paused"}</span>}
          {L.ready && <span>{L.achieved} moments/s shown · brains {L.msPerMoment.toFixed(1)} ms/moment</span>}
        </div>
      </header>

      {!L.ready && (
        <main className="max-w-[1400px] mx-auto px-4 py-16">
          <div className="card p-8 max-w-xl mx-auto text-center">
            <div className="kicker mb-3">Waking the league</div>
            <div className="h-2 rounded bg-line overflow-hidden"><div className="h-full bg-aroused transition-all" style={{ width: `${Math.round(100 * L.progress)}%` }} /></div>
            <p className="text-sm text-muted mt-3">{L.error ? <span className="text-hplow">{L.error}</span> : L.status}</p>
            <p className="text-xs text-muted mt-6 leading-relaxed">Python and the released Cadence library load into a web worker (about 15 MB the first time); the six brains are checkpoints of 100 to 120 KB each. Nothing leaves your browser.</p>
          </div>
        </main>
      )}

      {L.ready && (
        <main className="max-w-[1400px] mx-auto px-4 pb-12 grid gap-4 lg:grid-cols-[1fr_320px]">
          <section className="card overflow-hidden relative">
            <ArenaCanvas frame={L.frame} specs={L.specs} frameIndex={L.frameIndex} selected={L.selected} onSelect={L.setSelected} dealt={L.tallies.dealt} />
            {L.results && <FightSummary results={L.results.results} eloDelta={L.results.eloDelta} colors={colors} onNext={() => L.nextFight()} countdown={L.countdown} autoContinue={L.autoContinue} onToggleAuto={() => L.setAutoContinue(!L.autoContinue)} />}
            <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-t border-line">
              <button className="btn" onClick={() => L.setPlaying(!L.playing)}>{L.playing ? "Pause" : "Play"}</button>
              <div className="flex gap-1">
                {([1, 2, 0] as const).map((s) => (
                  <button key={s} className={`btn ${L.speed === s ? "btn-active" : ""}`} onClick={() => L.setSpeed(s)}>{s === 0 ? "as fast as they settle" : `${s}×`}</button>
                ))}
              </div>
              <button className="btn" onClick={() => L.nextFight()}>New fight</button>
              <span className="ml-auto text-xs text-muted tnum">fight {L.league.fights.length + 1} · moment {L.frameIndex} / {L.duration} · {seconds} s · ring {L.frame ? L.frame.zone.toFixed(1) : "10.0"} m</span>
            </div>
          </section>
          <aside className="card p-4">
            <h2 className="kicker mb-2">Standings</h2>
            <Standings frame={L.frame} specs={L.specs} selected={L.selected} onSelect={L.setSelected} tallies={L.tallies} elo={L.league.elo} />
            <div className="mt-4 text-[11px] text-muted leading-relaxed space-y-1">
              <div><i className="inline-block w-2 h-2 rounded-full mr-1.5 bg-calm" />calm: one settled state, no learning</div>
              <div><i className="inline-block w-2 h-2 rounded-full mr-1.5 bg-aroused" />aroused: sampling and learning</div>
              <div>The ring closes to 3.5 m over 100 s; outside it, robots burn. Closing in on a rival and damage dealt pay; damage taken hurts; placement pays at the end.</div>
              <div>In the ring a brain is calm unless an outcome contradicts its forecast: a hard hit, the burn, a placement. Then it is aroused, samples and learns, and settles back.</div>
            </div>
          </aside>
          <div className="lg:col-span-2"><BrainInspector frame={L.frame} specs={L.specs} selected={L.selected} /></div>
          <div className="lg:col-span-2"><LeaguePanel league={L.league} roster={L.roster} manifest={L.manifest} onReset={() => L.resetLeague()} persisted={L.persisted} describe={L.describe} /></div>
          <footer className="lg:col-span-2 text-xs text-muted leading-relaxed max-w-4xl">
            Built on <a className="underline hover:text-ink" href="https://github.com/muellerberndt/cadence">Cadence</a> {L.manifest?.cadence}: a brain is one neural graph that settles into agreement every moment; routine is equilibrium, surprise and want trigger learning.
            The arena, the robots and the league are open at <a className="underline hover:text-ink" href="https://github.com/muellerberndt/cadence-robot-arena">cadence-robot-arena</a>. The same Python runs here in Pyodide as ran the leagues on a laptop and on 192 vCPUs.
          </footer>
        </main>
      )}
    </div>
  );
}
