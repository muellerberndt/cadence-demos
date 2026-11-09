"""Print the readings of the receipts in ``evidence/`` as the README quotes them.

    python training/readings.py [evidence]
"""

import json
import sys
from pathlib import Path

ev = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "evidence")


def load(name):
    p = ev / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def f0(x):
    return f"{x:,.0f}"


r = load("controls")
if r:
    s, n = r["summary"], len(r["seeds"])
    p = s["paired_live_minus_frozen_age"]
    print(f"controls ({n} seeds, {r['settings']['moments']:,} moments): "
          f"age live {f0(s['live']['mean_age'])} [{f0(s['live']['mean_age_ci95'][0])}, {f0(s['live']['mean_age_ci95'][1])}], "
          f"frozen {f0(s['frozen']['mean_age'])} [{f0(s['frozen']['mean_age_ci95'][0])}, {f0(s['frozen']['mean_age_ci95'][1])}], "
          f"random {f0(s['random']['mean_age'])}; intake {s['live']['income_per_moment']:.3f} / "
          f"{s['frozen']['income_per_moment']:.3f} / {s['random']['income_per_moment']:.3f}; paired {f0(p['mean'])} "
          f"[{f0(p['ci95'][0])}, {f0(p['ci95'][1])}], {p['live_outlived_twin']}/{p['pairs']}; "
          f"died share {s['live']['died_share']:.2f} / {s['frozen']['died_share']:.2f}")
    import statistics as st
    for kind in ("live", "frozen", "random"):
        rows = [x for q in r["per_seed"] for x in q["rows"] if x["kind"] == kind]
        per = {k: st.mean(1000 * x["stats"][k] / max(x["age"], 1) for x in rows)
               for k in ("wasted", "drink", "moves", "berry_summer", "nut")}
        causes = {c: sum(1 for x in rows if x["cause"] == c) for c in {x["cause"] for x in rows}}
        print(f"   {kind}: per 1000 moments " + ", ".join(f"{k} {v:.1f}" for k, v in per.items()) + f"; causes {causes}")
for name in ("heat-on", "heat-off"):
    r = load(name)
    if r:
        s = r["summary"]
        p = s["paired_live_minus_frozen_age"]
        print(f"{name}: live {f0(s['live']['mean_age'])}, frozen {f0(s['frozen']['mean_age'])}, paired {f0(p['mean'])} "
              f"[{f0(p['ci95'][0])}, {f0(p['ci95'][1])}], {p['live_outlived_twin']}/{p['pairs']}")
r = load("flip")
if r:
    s = r["summary"]
    for k in ("live", "frozen"):
        v = s[k]
        acc = [a for a in v["acceptance_per_bin"]]
        print(f"flip {k}: acceptance summer last 100 {acc[s['flip_bin'] - 1]:.2f}, winter bins "
              + ", ".join("-" if a is None else f"{a:.2f}" for a in acc[s['flip_bin']:]) +
              f"; berries/100 summer {v['summer_berries_per_100']:.2f}, winter first300 {v['winter_first_300_per_100']:.2f}, "
              f"last500 {v['winter_last_500_per_100']:.2f}; poisonings per creature {v['winter_poisonings_per_creature']:.2f}")
r = load("seasons")
if r:
    s = r["summary"]
    for k in ("live", "frozen"):
        print(f"seasons {k}: " + "; ".join(
            f"{name} first300 {x['first_300_per_100']:.3f} [{x['first_300_ci95'][0]:.3f}, {x['first_300_ci95'][1]:.3f}] "
            f"season {x['season_per_100']:.3f} acc {x['acceptance'] if x['acceptance'] is None else round(x['acceptance'], 3)}"
            for name, x in zip(s["seasons"], s[k])))
r = load("evolution")
if r:
    s = r["summary"]
    for k in ("before", "after"):
        v = s[k]
        print(f"evolution {k}: age {f0(v['mean_age'])} [{f0(v['mean_age_ci95'][0])}, {f0(v['mean_age_ci95'][1])}], "
              f"intake {v['income_per_moment']:.3f} [{v['income_ci95'][0]:.3f}, {v['income_ci95'][1]:.3f}], "
              f"brain cost {v['brain_cost_per_moment']:.4f}, learning sweeps {v['learning_sweeps_per_moment']:.1f}, {v['structures']}")
r = load("competition")
if r:
    s = r["summary"]
    print(f"competition: evolved share {s['evolved_share_of_learners_at_end']:.3f} [{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}], "
          f"evolved hold all {s['worlds_evolved_hold_all']}, gen0 hold all {s['worlds_generation0_hold_all']} of {s['worlds']}; "
          f"births {s['births_after']} vs {s['births_before']}")
r = load("caches")
if r:
    s = r["summary"]
    print(f"caches: on {s['nuts_per_1000_recall_on']:.2f} off {s['nuts_per_1000_recall_off']:.2f} paired "
          f"{s['paired_on_minus_off']:.3f} [{s['paired_ci95'][0]:.3f}, {s['paired_ci95'][1]:.3f}] "
          f"on better {s['on_better']} off better {s['off_better']} of {s['pairs']}")
