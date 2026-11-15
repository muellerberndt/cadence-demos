# The brain view's live data (`viz`, format 1)

The 3D brain (`brain3d.js`, `brainlive.js`) and the brain panel (`brainview.js`) draw only what the
brain host reports. A host's `step` reply may carry one optional `viz` block per moment; every field
in it is optional, and a host fills only what it computes. A part with no data is drawn faint and
listed as "not in this brain yet" under "What it shows". Nothing is animated from made-up numbers.

Names: regions are the atlas ids of `atlas.js` (`retina`, `tectum`, `rotundus`, `wulst`, `arco`,
`place`, `map`, `records`, `heads`, `ncl`, `trace`, `words`, `ear`, `fieldl`, `ncm`, `vocal`,
`voice`, `striatum`, `vta`, `lc`, `bf`, ...). A unit is an index into the reply's `activity` buffer
(the layout of `describe().populations`). Places are table metres `[x, z]` (INTERFACES D1: +x the
parrot's left, +z the way it faces at rest). Angles are degrees.

## What the view reads from the reply as it stands

| Part | Field | Hosts |
| --- | --- | --- |
| Every neuron's glow, every region card | `buffers.activity`, `describe().populations` (`region` = atlas id) | both |
| Record slots: depth, fade, picture, sayable | `memory.records[]` (`slot`, `deep`, `faded`, `thumb`, `heard`), `memory.level` | both (hearing layer) |
| Word links: record to thing | `memory.records[].slow`, `.fast` over `memory.things` | both |
| A word stored (packet Field L, NCM, slot) | `heard_sound` (`slot`), `memory.write.revised` | both |
| One memory head (beam from NCM to the slots read) | `memory.read` (`slots`, `weights`) with `heard_sound` | both |
| A word said (packet slot, vocal, voice; the match) | `said` (placeholder) or `said_sound` (composed): `id` `you-<slot>`, `match` | both |
| The thing in focus (lit thing unit) | the page's focus (`state.focus`, from `focus`) | both |
| Map of things: place cells, things, focus, heading | `map` population (54 x 37 cells, x-major), `things[]` (`place`, `state`), `focus.place`, `buffers.angles[0]` | composed |
| Surprise: a sudden sound | `startle` | placeholder |
| Surprise: a thing that appears or moves | `focus.why` in {appeared, moved} | composed (when its focus picks) |
| Dopamine wash and the tracts it paid | `vta` (a number), `reward`, `paid[]` (`from`, `to`, `change`) | composed with `config.whole` |

## The `viz` block

```json
"viz": {
  "v": 1,
  "settle": {
    "frames": 16, "sweeps": 24, "kind": "residual",
    "regions": { "ncl": [0.12, 0.08, 0.03, ...], "arco": [...] },
    "tracts": [ { "from": "ncl", "to": "arco", "carried": [0.4, 0.38, ...] } ]
  },
  "surprise": {
    "units": [ [2401, 3.2], [2399, 2.1] ],
    "regions": { "tectum": 2.4 },
    "focus": { "place": [0.16, 0.26], "held": 7, "why": "moved", "returned": [ [0.3, -0.1, 0.6] ] }
  },
  "modulators": {
    "dopamine": { "level": 0.8, "why": "pistachio", "targets": { "striatum": 1, "ncl": 0.8 }, "paid": [ { "from": "ncl", "to": "vocal", "change": 3.1 } ] },
    "noradrenaline": { "level": 0.6, "why": "surprise", "targets": { "ncl": 1, "map": 0.8 } },
    "acetylcholine": { "level": 0.5, "at": [0.16, 0.26], "targets": { "tectum": 1 } }
  },
  "memory": {
    "slots": [ { "id": 3, "kind": "word", "depth": 4.2, "faded": 0.1, "kept": true } ],
    "events": [ { "slot": 3, "what": "revise" } ],
    "heads": [ { "cue": "the sound just heard", "from": "ncm", "weights": [ [3, 0.82], [7, 0.11] ] } ]
  },
  "map": {
    "things": [ { "place": [0.16, 0.26], "velocity": [0.0, 0.02], "forecast": [0.16, 0.28], "seen": true } ],
    "pose": { "heading": 12.5 }
  },
  "words": {
    "segment": { "on": true },
    "stored": { "slot": 3, "revised": true },
    "attempt": { "slot": 3, "match": 0.93 }
  }
}
```

- **settle** (repairs): per region, its residual at up to 16 frames spread over the moment's settle
  sweeps (the distance of its neurons from the settled state, any non-negative scale); per tract,
  the message it carries at each frame. The view replays the moment in its 100 ms: each region glows
  with what it has left to repair and settles out, and light runs along a tract as its message
  changes. A reference for a host that keeps the settle's trajectory (`settle_batch(...,
  trajectory=True)`; rows = sweeps, columns = neurons):

  ```python
  def settle_viz(rows, regions, frames=16):
      """rows: (sweeps + 1, neurons); regions: {atlas id: neuron indices}."""
      pick = np.linspace(0, len(rows) - 1, min(frames, len(rows))).round().astype(int)
      final = rows[-1]
      return {"frames": len(pick), "sweeps": len(rows) - 1, "kind": "residual",
              "regions": {k: np.abs(rows[pick][:, i] - final[i]).mean(axis=1).round(4).tolist()
                          for k, i in regions.items()}}
  ```
- **surprise**: `units` the most surprised units, each with its level (#337: the settle's residual
  from the learned forecast, per unit, scaled by its usual size, so 1 is usual); the view flashes a
  unit above 1. `focus.returned` places with inhibition of return, each `[x, z, strength]`.
- **modulators**: `level` in [-1, 1] (dopamine may dip below 0); `targets` atlas ids with weights
  (the atlas's projections when absent); `paid` the tracts the dopamine strengthened.
- **memory**: `slots` the records (`kind` word, place or thing; `depth`; `faded` 0 to 1; `kept`
  past #336's threshold: a solid rim); `events` this moment's `write`, `revise` ("told again"),
  `fade`, `kept`; `heads` one entry a head (#325), its cue's region and its weights over slots.
- **map**: things with `velocity` and `forecast` (a ghost and a dashed line to it); `pose.heading`
  the head's yaw.
- **words**: `segment.on` while a sound is being heard, `stored` at its offset, `attempt` a
  pronunciation with its match.
