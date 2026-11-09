# Cadence Showcase League · the page

Six robots, each with one continuing Cadence brain wired to every motor, fight and learn live
in the browser. Python and the released Cadence library run in a web worker (Pyodide); the
same `arena` code that raised the brains runs the ring here. Every brain is saved in the browser (IndexedDB) after
every fight and restored on the next visit: the robot you watched learn yesterday is the
robot that fights today. Click a robot to inspect its brain, moment by moment.

Stack: Vite, React 18, TypeScript, Tailwind. No backend, no accounts, nothing leaves the
browser. The pack in `public/pack/` holds the Cadence wheel (from PyPI, hashed), the arena's
Python sources, the browser host and the six brains with a manifest; Pyodide itself comes
from jsDelivr at load time (about 15 MB the first time, cached afterwards).

## Run it

```sh
npm install
../.venv/bin/python pack.py      # rebuild public/pack from ../league-live (optional; the pack is committed)
npm run dev                      # http://localhost:8080
npm run build && npm run preview # the production build at http://localhost:4173
node check_page.mjs              # the page's promise, end to end in headless Chrome
```

`pack.py` downloads the pinned Cadence wheel, copies the arena's sources and the brains of
the six highest-rated robots of the league, runs their driving test and writes the
manifest. `npm run build` uses the existing pack and does not rebuild it. Each packed brain
carries its final owed outcome into its first browser fight; restoring a saved browser life
uses that life's own saved outcome. A saved league belongs to one pack (the library version
and every brain's hash), so a new pack starts a fresh league in a returning visitor's browser.

`check_page.mjs` is the deploy gate: the league wakes, a fight runs, a robot's brain can be
inspected, the fight ends at full speed, the brains land in IndexedDB, and a reload restores
them. Run it against the preview before publishing.

## Deploy on Lovable

Lovable projects are Vite + React + TypeScript + Tailwind, which is what this folder is.

1. In Lovable, create a project and connect it to GitHub (Settings → GitHub), or open the
   project's repository that Lovable created for you.
2. Replace the repository's contents with this folder: `package.json`, `index.html`,
   `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `src/`,
   `public/` (with `public/pack/` complete: the wheel, `py/`, `brains/`, `manifest.json`),
   `pack.py`, `check_page.mjs`, this README. Commit and push; Lovable syncs and builds
   (`npm run build`, output `dist/`).
3. Publish from Lovable. The page needs no environment variables, no server and no database.
   The worker loads Pyodide from `cdn.jsdelivr.net`, so that domain must be reachable.

Any static host (Netlify, Vercel, GitHub Pages) serves the `dist/` build
as well; the `pack/` files must be served with their paths intact.

## What the page shows

- **The ring**: an isometric royale of six, the ring closing from 10 m to 3.5 m over a hundred
  seconds, the burn outside it, wheels, legs with planted feet, arms with their weapons,
  hits, flames, trails and each robot's mood halo (blue calm, orange aroused).
- **Standings**: hit points, damage dealt, the brain's mode and, live, the share of moments it
  spent learning and the learning sweeps it did in this fight.
- **The brain inspector**: the selected robot's senses (four direction cells for the nearest
  robot and four for the ring's edge, body, proprioception), the settled state of its
  association cortex, the motor cortex slot by slot with the chosen command, the arousal
  level against its threshold with the last 200 moments of level and reward, and the
  command it just issued.
- **The league in this browser**: Elo over your fights, wins, mean place, damage and burn per
  fight early against late, what each robot arrived with (its moments lived and its driving test) and, for a
  roster bred by `python -m arena evolve`, its lineage, mutations and the lineage shares per generation.
- **Reset**: restores the six brains to the checkpoints they arrived with.

Speeds: 1×, 2× and "as fast as they settle". A brain's moment costs a few to a few tens of
milliseconds in Pyodide depending on the body and the machine; the shown rate and the
brains' cost per moment are in the header.
