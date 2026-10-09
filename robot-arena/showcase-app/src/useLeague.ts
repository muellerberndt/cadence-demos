// The league in the page: drives the worker, plays the frames it returns, keeps the ladder,
// and persists every brain (the library's own checkpoint bytes) and the record in the
// browser after each fight. One continuing life per robot: the brain that fights the next
// royale is the brain that fought this one, in this browser.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Frame, Result, Spec } from "./arena/types";
import { getItem, removeAll, setItem } from "./store/persist";

export type FightRecord = { id: number; seed: number; moments: number; when: string; results: Result[]; elo_after: Record<string, number> };
export type LeagueRecord = {
  version: 1; elo: Record<string, number>; fights: FightRecord[]; totalMoments: number; savedAt: string | null;
  owed: Record<string, [number, boolean] | null>; rosterKey?: string;
};
export type Speed = 1 | 2 | 0; // 0 = as fast as the brains settle

const PACK = "/pack/";
const DURATION = 1200, ZONE = 1000, BATCH = 6;

function eloUpdate(ratings: Record<string, number>, places: Record<string, number>, k = 32): Record<string, number> {
  const names = Object.keys(places), n = names.length, delta: Record<string, number> = {};
  names.forEach((x) => (delta[x] = 0));
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const a = names[i], b = names[j], expected = 1 / (1 + 10 ** ((ratings[b] - ratings[a]) / 400));
    const actual = places[a] === places[b] ? 0.5 : places[a] < places[b] ? 1 : 0;
    const change = (k / (n - 1)) * (actual - expected); delta[a] += change; delta[b] -= change;
  }
  return delta;
}

export function useLeague() {
  const workerRef = useRef<Worker | null>(null);
  const pending = useRef(new Map<number, { resolve: (v: any) => void; reject: (e: any) => void }>());
  const rid = useRef(0);
  const [status, setStatus] = useState("starting");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [manifest, setManifest] = useState<any>(null);
  const [describe, setDescribe] = useState<any>(null);
  const [specs, setSpecs] = useState<Spec[]>([]);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState<Speed>(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [results, setResults] = useState<{ results: Result[]; eloDelta: Record<string, number>; seed: number } | null>(null);
  const [league, setLeague] = useState<LeagueRecord>({ version: 1, elo: {}, fights: [], totalMoments: 0, savedAt: null, owed: {} });
  const [msPerMoment, setMsPerMoment] = useState(0);
  const [achieved, setAchieved] = useState(0); // moments per second shown
  const [tallies, setTallies] = useState<{ dealt: number[]; aroused: number[]; alive: number[]; sweeps: number[] }>({ dealt: [], aroused: [], alive: [], sweeps: [] });
  const [persisted, setPersisted] = useState<"fresh" | "restored" | "saved">("fresh");
  const [fightSeed, setFightSeed] = useState(0);
  const [autoContinue, setAutoContinue] = useState(true);
  const [countdown, setCountdown] = useState<number | null>(null);
  const autoRef = useRef(true); autoRef.current = autoContinue;
  const timerRef = useRef<number | null>(null);

  const buffer = useRef<Frame[]>([]);
  const fetching = useRef(false);
  const fightDone = useRef(false);
  const fightResults = useRef<any>(null);
  const playingRef = useRef(true); playingRef.current = playing;
  const speedRef = useRef<Speed>(1); speedRef.current = speed;
  const leagueRef = useRef(league); leagueRef.current = league;
  const specsRef = useRef<Spec[]>([]); specsRef.current = specs;
  const tallyRef = useRef({ dealt: [] as number[], aroused: [] as number[], alive: [] as number[], sweeps: [] as number[] });
  const shownCount = useRef(0), shownSince = useRef(performance.now());
  const arrived = useRef(0), arrivalRate = useRef(20), arrivalSince = useRef(performance.now());

  const call = useCallback((op: string, payload: any = {}) => {
    return new Promise<any>((resolve, reject) => {
      const id = ++rid.current;
      pending.current.set(id, { resolve, reject });
      workerRef.current!.postMessage({ rid: id, op, ...payload });
    });
  }, []);

  // boot the worker
  useEffect(() => {
    const worker = new Worker(new URL("./worker/league.worker.ts", import.meta.url), { type: "module" });
    workerRef.current = worker;
    worker.onmessage = (e: MessageEvent) => {
      const d = e.data;
      if (d.status !== undefined) { setStatus(d.status); if (d.progress !== undefined) setProgress(d.progress); return; }
      const p = pending.current.get(d.rid); if (!p) return; pending.current.delete(d.rid);
      d.error ? p.reject(new Error(d.error)) : p.resolve(d.result);
    };
    worker.onerror = (e) => setError(String(e.message || e));
    (async () => {
      try {
        const started = await call("start", { pack: PACK });
        setManifest(started.manifest); setDescribe(started.describe);
        const names: string[] = started.manifest.roster.map((r: any) => r.name);
        const rosterKey = names.join("|");
        const saved = await getItem<LeagueRecord>("league");
        const brains = await getItem<Record<string, string>>("brains");
        let record: LeagueRecord;
        if (saved && brains && saved.version === 1 && saved.rosterKey === rosterKey) {
          await call("restore", { brains, owed: saved.owed });
          record = saved; setPersisted("restored");
        } else {
          // a new roster in the pack: the saved lives of other robots stay out of the way
          if (saved) await removeAll();
          record = { version: 1, elo: Object.fromEntries(names.map((n) => [n, 1000])), fights: [], totalMoments: 0, savedAt: null, owed: {}, rosterKey };
        }
        setLeague(record); leagueRef.current = record;
        setReady(true);
        await newFight(record);
      } catch (err: any) { setError(String(err.message || err)); }
    })();
    return () => worker.terminate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const newFight = useCallback(async (record?: LeagueRecord) => {
    const rec = record || leagueRef.current;
    const names = (manifestRef.current?.roster || []).map((r: any) => r.name);
    const seed = Math.floor(Math.random() * 1_000_000);
    buffer.current = []; fightDone.current = false; fightResults.current = null; setResults(null); setCountdown(null);
    if (timerRef.current) { window.clearInterval(timerRef.current); timerRef.current = null; }
    const started = await call("new_fight", { names, seed, duration: DURATION, zone_moments: ZONE });
    const sp: Spec[] = started.robots; setSpecs(sp); specsRef.current = sp;
    tallyRef.current = { dealt: sp.map(() => 0), aroused: sp.map(() => 0), alive: sp.map(() => 0), sweeps: sp.map(() => 0) };
    setTallies({ ...tallyRef.current });
    setFrame(started.frame); setFrameIndex(0); setFightSeed(seed);
    void rec;
  }, [call]);
  const manifestRef = useRef<any>(null); manifestRef.current = manifest;

  // pump: keep the buffer filled while the fight runs
  const pump = useCallback(async () => {
    if (fetching.current || fightDone.current || !specsRef.current.length) return;
    if (buffer.current.length > 60) return;
    fetching.current = true;
    try {
      const out = await call("step", { n: BATCH });
      buffer.current.push(...out.frames);
      arrived.current += out.frames.length;
      setMsPerMoment(out.ms_per_moment);
      if (out.done) { fightDone.current = true; fightResults.current = out.results; }
    } catch (err: any) { setError(String(err.message || err)); }
    finally { fetching.current = false; }
  }, [call]);

  // the player: shows frames at the chosen speed, never faster than they arrive
  useEffect(() => {
    let raf = 0, acc = 0, last = performance.now();
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      const dt = (now - last) / 1000; last = now;
      if (!playingRef.current) { void pump(); return; }
      void pump();
      const sp = speedRef.current;
      // the arrival rate of frames from the worker, smoothed: "as fast as they settle" shows
      // frames at that rate instead of in bursts, nudged by how full the buffer is
      if (now - arrivalSince.current > 500) {
        const r = arrived.current / ((now - arrivalSince.current) / 1000);
        arrivalRate.current = 0.5 * arrivalRate.current + 0.5 * r; arrived.current = 0; arrivalSince.current = now;
      }
      const len = buffer.current.length;
      const target = sp === 0 ? Math.max(5, arrivalRate.current) * (len > 24 ? 1.5 : len < 4 ? 0.8 : 1.0) : 20 * sp;
      acc += dt * target; let n = Math.floor(acc); acc -= n; n = Math.min(n, len);
      if (acc > 4) acc = 4;
      if (n > 0) {
        let f: Frame | undefined;
        for (let k = 0; k < n; k++) { f = buffer.current.shift(); if (f) tally(f); }
        if (f) { setFrame(f); setFrameIndex(f.t); shownCount.current += n; }
        setTallies({ ...tallyRef.current });
      }
      if (now - shownSince.current > 1000) { setAchieved(Math.round(shownCount.current / ((now - shownSince.current) / 1000))); shownCount.current = 0; shownSince.current = now; }
      if (fightDone.current && buffer.current.length === 0 && fightResults.current) {
        const res = fightResults.current; fightResults.current = null;
        void finishFight(res);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pump]);

  function tally(f: Frame) {
    const t = tallyRef.current;
    for (const h of f.hits) t.dealt[h[3]] += h[2];
    f.robots.forEach((r, i) => { if (r[4] !== 9) { t.alive[i]++; if (r[4] === 1) t.aroused[i]++; if (r[9]) t.sweeps[i] += r[9][6] || 0; } });
  }

  const finishFight = useCallback(async (res: any) => {
    const rec = leagueRef.current;
    const places: Record<string, number> = {}; res.results.forEach((r: Result) => (places[r.name] = r.place));
    const delta = eloUpdate(rec.elo, places);
    const elo = { ...rec.elo }; Object.keys(delta).forEach((n) => (elo[n] = Math.round((elo[n] + delta[n]) * 10) / 10));
    const record: FightRecord = { id: rec.fights.length + 1, seed: res.seed, moments: res.moments, when: new Date().toISOString(), results: res.results, elo_after: elo };
    const next: LeagueRecord = { ...rec, elo, fights: [...rec.fights, record].slice(-200), totalMoments: rec.totalMoments + res.results.reduce((a: number, r: Result) => a + r.moments, 0), owed: res.owed, savedAt: new Date().toISOString() };
    setResults({ results: res.results, eloDelta: delta, seed: res.seed });
    setLeague(next); leagueRef.current = next;
    try {
      const saved = await call("save", {});
      const ok = await setItem("brains", saved.brains);
      await setItem("league", next);
      if (ok) setPersisted("saved");
    } catch (err: any) { setError(String(err.message || err)); }
    // continuous rounds: the next fight starts by itself after a short pause
    if (autoRef.current) {
      let left = 6; setCountdown(left);
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = window.setInterval(() => {
        if (!autoRef.current) { window.clearInterval(timerRef.current!); timerRef.current = null; setCountdown(null); return; }
        left -= 1; setCountdown(left);
        if (left <= 0) { window.clearInterval(timerRef.current!); timerRef.current = null; setCountdown(null); void newFight(); }
      }, 1000);
    }
  }, [call, newFight]);

  const resetLeague = useCallback(async () => {
    await removeAll();
    await call("reset", {});
    const names = (manifestRef.current?.roster || []).map((r: any) => r.name);
    const record: LeagueRecord = { version: 1, elo: Object.fromEntries(names.map((n: string) => [n, 1000])), fights: [], totalMoments: 0, savedAt: null, owed: {}, rosterKey: names.join("|") };
    setLeague(record); leagueRef.current = record; setPersisted("fresh");
    await newFight(record);
  }, [call, newFight]);

  const roster = useMemo(() => (manifest?.roster || []) as any[], [manifest]);
  return {
    status, progress, error, ready, manifest, describe, roster, specs, frame, frameIndex, playing, setPlaying, speed, setSpeed,
    selected, setSelected, results, league, msPerMoment, achieved, tallies, persisted, fightSeed,
    autoContinue, setAutoContinue, countdown,
    nextFight: () => newFight(), resetLeague, duration: DURATION,
  };
}
