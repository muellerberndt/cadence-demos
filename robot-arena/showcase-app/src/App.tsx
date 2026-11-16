import { useEffect, useMemo } from "react";
import { ArenaCanvas } from "./components/ArenaCanvas";
import { BrainInspector } from "./components/BrainInspector";
import { FightSummary } from "./components/FightSummary";
import { LeaguePanel } from "./components/LeaguePanel";
import { Standings } from "./components/Standings";
import { PALETTE } from "./arena/types";
import { explain } from "./explain";
import { useLeague } from "./useLeague";

export default function App() {
  const L = useLeague();
  const colors = useMemo(() => Object.fromEntries(L.specs.map((s, i) => [s.name, PALETTE[i % PALETTE.length]])), [L.specs]);
  const seconds = (L.frameIndex * 0.05).toFixed(1);
  // after every render: parts that appeared get their question marks
  useEffect(() => { explain()?.scan(); });
  return (
    <div className="min-h-screen">
      <header className="max-w-[1400px] mx-auto px-4 pt-6 pb-3 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div data-standalone>
          <div className="kicker">Cadence · brains that learn while they fight</div>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">Cadence Showcase League</h1>
        </div>
        <p data-standalone className="text-sm text-muted max-w-xl leading-relaxed">
          Six robots, each with one continuing Cadence brain, fight <em className="text-ink not-italic font-medium">live, in your browser</em>. A brain stays calm while things go as usual; a surprise wakes its learning (amber).
        </p>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted tnum">
          {L.ready && <span data-explain="Live: the fight runs. Paused: the fight waits for you." data-explain-mark="none" className={`px-2 py-1 rounded-lg border ${L.playing ? "border-aroused/60 text-aroused" : "border-line"}`}><span>{L.playing ? "live" : "paused"}</span></span>}
          {L.ready && <span data-explain="How many moments a second the page shows, and how long the six brains take for one moment in your browser. The ring runs 20 moments a second at 1×." data-explain-mark="none"><span>{L.achieved} moments/s shown · brains {L.msPerMoment.toFixed(1)} ms/moment</span></span>}
        </div>
      </header>

      {!L.ready && (
        <main className="max-w-[1400px] mx-auto px-4 py-16">
          <div className="card p-8 max-w-xl mx-auto text-center">
            <div className="kicker mb-3">Waking the league</div>
            <div className="h-2 rounded bg-line overflow-hidden"><div className="h-full bg-aroused transition-all" style={{ width: `${Math.round(100 * L.progress)}%` }} /></div>
            <p className="text-sm text-muted mt-3">{L.error ? <span className="text-hplow">{L.error}</span> : L.status}</p>
            <p className="text-xs text-muted mt-6 leading-relaxed">Python and the released Cadence library load into a web worker (about 15 MB the first time); the six brains are checkpoints of 100 to 120 KB each. Nothing leaves your browser.</p>
            <p className="text-xs mt-3"><a data-help href="help.html" target="_blank" rel="noopener" className="underline text-muted hover:text-ink">What is this page?</a></p>
          </div>
        </main>
      )}

      {L.ready && (
        <main className="max-w-[1400px] mx-auto px-4 pb-12 grid gap-4 lg:grid-cols-[1fr_320px] items-start">
          <section className="card overflow-hidden relative">
            <ArenaCanvas frame={L.frame} specs={L.specs} frameIndex={L.frameIndex} selected={L.selected} onSelect={L.setSelected} dealt={L.tallies.dealt} />
            <span className="ring-label" data-explain="Six robots fight in a ring that closes from 10 m to 3.5 m; outside it they burn. Damage dealt and closing in on a rival pay; damage taken and the burn hurt; placement pays at the end. The halo under a robot is its brain's mode: blue calm, amber aroused and learning. Click a robot to watch its brain." data-explain-title="The ring">The ring · click a robot</span>
            {L.results && <FightSummary results={L.results.results} eloDelta={L.results.eloDelta} colors={colors} onNext={() => L.nextFight()} countdown={L.countdown} autoContinue={L.autoContinue} onToggleAuto={() => L.setAutoContinue(!L.autoContinue)} />}
            <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-t border-line">
              <button className="btn" data-explain="Pauses the fight, or lets it run again." data-explain-mark="none" onClick={() => L.setPlaying(!L.playing)}><span>{L.playing ? "Pause" : "Play"}</span></button>
              <div className="flex gap-1" data-explain="How fast the fight is shown. 1× is the ring's own time, 20 moments a second, when your machine keeps up; 2× is twice that; as fast as they settle shows each moment as soon as the six brains have answered it." data-explain-mark="none">
                {([1, 2, 0] as const).map((s) => (
                  <button key={s} className={`btn ${L.speed === s ? "btn-active" : ""}`} onClick={() => L.setSpeed(s)}>{s === 0 ? "as fast as they settle" : `${s}×`}</button>
                ))}
              </div>
              <button className="btn" data-explain="Leaves this fight and starts a new one. The brains keep what they learned so far." data-explain-mark="none" onClick={() => L.nextFight()}>New fight</button>
              <a className="btn help-link" data-help href="help.html" target="_blank" rel="noopener" data-explain="Everything this page shows, explained in full." data-explain-mark="none">Help</a>
              <span className="ml-auto text-xs text-muted tnum" data-explain="The fight's number in this browser; the moment, out of 2,400 at most; the time, at 20 moments a second; the ring's radius, closing from 10 m to 3.5 m." data-explain-mark="none"><span>fight {L.league.fights.length + 1} · moment {L.frameIndex} / {L.duration} · {seconds} s · ring {L.frame ? L.frame.zone.toFixed(1) : "10.0"} m</span></span>
            </div>
          </section>
          <aside className="card p-4">
            <h2 className="kicker mb-2" data-explain="The six robots of this fight, strongest first. Each row: hit points, damage dealt, the brain's mode at this moment, and in this fight the share of moments it spent learning and the learning sweeps it did. The number at the right is its rating in this browser. Click a row to watch that brain." data-explain-title="Standings">Standings</h2>
            <Standings frame={L.frame} specs={L.specs} selected={L.selected} onSelect={L.setSelected} tallies={L.tallies} elo={L.league.elo} />
            <div className="mt-4 text-[11px] text-muted leading-relaxed space-y-1">
              <div data-explain="Calm: the brain answers from one settled state of all its neurons and learns nothing. A brain is calm while things go as usual." data-explain-mark="none" className="cursor-help"><i className="inline-block w-2 h-2 rounded-full mr-1.5 bg-calm" />calm: one settled state, no learning</div>
              <div data-explain="Aroused: an outcome surprised the brain, or what the ring pays it fell below what its life usually brings. It samples its commands, learns from what they bring, and settles back to calm." data-explain-mark="none" className="cursor-help"><i className="inline-block w-2 h-2 rounded-full mr-1.5 bg-aroused" />aroused: sampling and learning</div>
            </div>
          </aside>
          <div className="lg:col-span-2"><BrainInspector specs={L.specs} selected={L.selected} anatomy={L.anatomy} inspectQueue={L.inspectQueue} history={L.history} /></div>
          <div className="lg:col-span-2"><LeaguePanel league={L.league} roster={L.roster} manifest={L.manifest} onReset={() => L.resetLeague()} persisted={L.persisted} describe={L.describe} /></div>
          <footer data-standalone className="lg:col-span-2 text-xs text-muted leading-relaxed max-w-4xl">
            Built on <a className="underline hover:text-ink" href="https://github.com/muellerberndt/cadence">Cadence</a> {L.manifest?.cadence}. The arena, the robots and the league are open at <a className="underline hover:text-ink" href="https://github.com/muellerberndt/cadence-demos/tree/main/robot-arena">cadence-demos/robot-arena</a>; the same Python that raised the brains runs here in Pyodide.
          </footer>
        </main>
      )}
    </div>
  );
}
