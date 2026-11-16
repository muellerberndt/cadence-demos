# The demo standard

Every demo makes one thing clear to a visitor who has never heard of Cadence: **what the demo
shows about Cadence, why that is a great feature, and what the visitor can do.** The demo page
stays minimal; the explanations live in three places:

1. **The demos site's header bar** (cadence.floatingpragma.ai) carries the demo's title, its claim
   and what to try. The demo's `site.json` holds that text.
2. **Question marks on the page.** Every control and every part of the brain explains itself in a
   short card when the pointer rests on it (`shared/cadence-explain.js`).
3. **A help page** (`help.html`, from `shared/help-template.html`) explains everything in detail.

## What Cadence is, in the site's words

Cadence brains are alternative, brain-inspired neural networks that learn during life. Wherever it
is true for the demo, say that the brain has **real memory, a real state, and runs in real time,
like the brain of a living being**. Each demo names one property of Cadence (a second only where the
page shows it as clearly). Examples:

- A brain that learns from a teacher and then exceeds the teacher during its own life.
- A brain that keeps a map of where everything is, even what its camera cannot see.
- A demo whose result a conventional network could also reach says so plainly and names what it
  does show, for example "Cadence brains play strong games: 363 wins in 400 against a perfect
  solver."

## Truth

- A claim is something the page shows, backed by an evidence file in the demo's folder. Numbers
  come from evidence files and name them. The claim gets a scripted scenario test on the real page
  in a headless browser (the promise test), run before every deploy.
- The help page states the limits: what the demo does not show.
- The rules of `AGENTS.md` hold: describe each mechanism as it is; trained brains, frozen
  protocols, evidence files, parity fixtures and runtime identities are never rewritten.
- Words: state-only (never "now", "still", "already", "remains", "no longer", "not yet",
  "currently"), no em dash, no "not X but Y" constructions, never "honest". No private names,
  people, projects or repositories.

## site.json

```json
{
  "slug": "atari-arcade",           "title": "Atari Arcade",       "page_dir": "web",
  "card":    "home card, one sentence (at most 140 characters)",
  "tagline": "a short subtitle (at most 80)",
  "kicker":  "THE CADENCE PROPERTY, A FEW WORDS (at most 48)",
  "feature": "what the demo shows and why it is great (at most 240)",
  "howTo":   "what the visitor can do (at most 240)",
  "help": "help.html",
  "evidence": ["the evidence files the claim and the numbers come from"],
  "promise_test": "the command that runs the promise test"
}
```

`page_dir` is the folder the site serves as `/demos/<slug>/` (its `index.html` becomes
`play.html` there).

## The page

- **Minimal.** No paragraphs of explanation on the page. A title or an introduction the page shows
  by itself carries `data-standalone`: inside the demos site (in a frame) it hides, because the
  site's header shows the title, the claim and what to try.
- **Explained.** The page loads `cadence-explain.css` and `cadence-explain.js` (copies of
  `shared/`, made by `python tools/sync_shared.py`). Every control and every brain region or part
  carries `data-explain` (or a spot over a canvas: `CadenceExplain.spot`), one to three plain
  sentences: what it is and what it does in the demo. Brain parts say what they do, in the role
  they play.
- **Help.** A small link in the page's own toolbar: `<a data-help href="help.html" target="_blank" rel="noopener">help</a>`.
- **Interactions marked.** Everything the visitor can do is either walked through (a tutorial or a
  first hint) or marked where it can be done (a question mark, a hint beside the pointer, a cursor).
- **One screen.** No sideways scroll at 1512x860 and 1280x720, by itself and in a frame.

## The help page

Sections in this order, with these ids: `see` (what you see), `why` (why it matters), `do` (what
you can do), `how` (how it works), `numbers` (the numbers, each with its evidence file), `limits`.
Keys, if any, after `limits`. A labelled figure of the screen helps the first section.

## Checks

- `python tools/check_explain.py <demo> --shots <dir>`: the shared gate (site.json, help page,
  explanations, embedded rule, no sideways scroll, no console errors).
- `python tools/sync_shared.py --check`: the shared files match.
- The demo's own tests and checks, and its promise test.
