# Attribution

Every asset the parrot page ships or loads, with its source, author and licence.

The rule for third-party assets in this folder: CC0 first, CC BY with attribution, and no asset
with an unclear licence. Two groups were generated for this page under the owner's own accounts and
are listed apart: the parrot's two bodies and the voices.

## Third-party assets in the folder

### The African Grey calls

| Files | Source | Author | Licence | Changes |
| --- | --- | --- | --- | --- |
| `site/pack/calls.json` | ["Psittacus erithacus making some noise"](https://commons.wikimedia.org/wiki/File:Psittacus_erithacus_making_some_noise.ogg), Wikimedia Commons (SHA-1 `536bd991cb9bbfd85febd7315571c848b22253e5`) | Amada44 | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | cut into single calls; each call kept as its own sound (16 kHz) and as the ear's log-mel frames (`site/tools/make_calls.py`) |

### The things, the textures and the light: Poly Haven

All from [Poly Haven](https://polyhaven.com), licensed [CC0 1.0](https://polyhaven.com/license).
`site/assets/CREDITS.json` lists, for each asset, the files fetched with their MD5 and the SHA-256
of each file the page loads (`site/tools/fetch_assets.py` writes it).

| Files | Asset | Authors | Licence |
| --- | --- | --- | --- |
| `site/assets/models/apple.glb` | [Food Apple 01](https://polyhaven.com/a/food_apple_01) | Oliver Harries | CC0 1.0 |
| `site/assets/models/ball.glb` | [Baseball 01](https://polyhaven.com/a/baseball_01) | Rico Cilliers | CC0 1.0 |
| `site/assets/models/cup.glb` | [Tea Set 01](https://polyhaven.com/a/tea_set_01) | James Ray Cock, Jurita Burger, Rico Cilliers | CC0 1.0 |
| `site/assets/models/banana.glb` | [Bananas](https://polyhaven.com/a/bananas) | Alexander Shulha | CC0 1.0 |
| `site/assets/models/duck.glb` | [Rubber Duck Toy](https://polyhaven.com/a/rubber_duck_toy) | Plat251 | CC0 1.0 |
| `site/assets/models/lemon.glb` | [Lemon](https://polyhaven.com/a/lemon) | Kuutti Siitonen | CC0 1.0 |
| `site/assets/models/pear.glb` | [Pears Asian 01](https://polyhaven.com/a/food_pears_asian_01) | Amal Kumar | CC0 1.0 |
| `site/assets/tex/table_*.jpg` | [Wood Table 001](https://polyhaven.com/a/wood_table_001) | Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `site/assets/tex/floor_*.jpg` | [Wood Floor](https://polyhaven.com/a/wood_floor) | Dimitrios Savva | CC0 1.0 |
| `site/assets/tex/wall_*.jpg` | [Beige Wall 001](https://polyhaven.com/a/beige_wall_001) | Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `site/assets/tex/bark_*.jpg` | [Bark Brown 02](https://polyhaven.com/a/bark_brown_02) | Rob Tuytel | CC0 1.0 |
| `site/assets/tex/block_*.jpg` | [Plywood](https://polyhaven.com/a/plywood) | Rob Tuytel | CC0 1.0 |
| `site/assets/tex/post_*.jpg` | [Oak Veneer 01](https://polyhaven.com/a/oak_veneer_01) | Jenelle van Heerden | CC0 1.0 |
| `site/assets/room.hdr` | [Lebombo](https://polyhaven.com/a/lebombo) | Greg Zaal | CC0 1.0 |

The key, the block's shape, the green ball, the perch, the table and the pistachio are drawn by
the page's own code (`site/scene.js`, `site/pistachio.js`); they have no model file.

### Vendored code

| Files | Source | Author | Licence |
| --- | --- | --- | --- |
| `site/vendor/three/three.module.min.js` and `site/vendor/three/jsm/` (`OrbitControls.js`, `GLTFLoader.js`, `RGBELoader.js`, `BufferGeometryUtils.js`) | [three.js](https://github.com/mrdoob/three.js) r160 | the three.js authors | MIT (`site/vendor/three/LICENSE`) |
| `site/pack/cadence_net-0.99.0-lane-meaning-568a0ad8-parrot-5fccf8cb.whl` | [Cadence](https://github.com/muellerberndt/cadence), a development build from its branches `lane-0100-meaning` and `lane-0100-parrot` | Bernhard Mueller | GPL-3.0 (the licence text is inside the wheel) |

## Generated for this page

### The parrot's two bodies

| Files | Source | Made by | Terms |
| --- | --- | --- | --- |
| `site/looks/realistic.glb`, `site/looks/realistic.rig.json` | made with [Meshy](https://www.meshy.ai) from a generated image of an African Grey (an image, then image to 3D), then fitted to the page's rig by `site/tools/prepare_look.py` | the repository owner, under the owner's Meshy account | output of that account under Meshy's terms; no Creative Commons licence is attached |
| `site/looks/anime.glb`, `site/looks/anime.rig.json` | an original design, made with Meshy the same way and fitted the same way | the repository owner, under the owner's Meshy account | output of that account under Meshy's terms; no Creative Commons licence is attached |

### The voices

Voices generated with ElevenLabs, under the owner's ElevenLabs account. No Creative Commons licence
is attached; ElevenLabs' terms apply to the output.

| Files | What | How it was made |
| --- | --- | --- |
| `site/voice/words.json` (the sound of each starting record) | a woman's voice says each answer word, a man's voice each question word, one take a word | ElevenLabs text to speech (`eleven_multilingual_v2`), the ElevenLabs voices "Jessica Anne Bogart - Chatty and Friendly" and "Mark - Natural Conversations"; each take then heard by the page's own hearing code (`site/tools/build_words.py`) |
| `site/voice/questions/*.wav`, `site/voice/questions.json` | the preset questions | the man's takes of each word, joined with short pauses (`site/tools/build_words.py`) |
| `site/voice/parrot/*.wav` | the parrot's rendering of each starting sound | ElevenLabs speech to speech (`eleven_multilingual_sts_v2`) of the kept sound into a parrot voice made with ElevenLabs Voice Design |

Only takes and renderings that Whisper reads as their word are in the folder.

## The page's own work

The page's code, the trained brain (`site/pack/trained/`), the hosts (`site/pack/py/`), the test
fixtures (`site/tests/fixtures/dsp_clips.json`, synthetic clips written by
`site/tests/make_dsp_fixtures.py`), the evidence files and the shared demo files
(`cadence-explain.js`, `cadence-explain.css`, `cadence-help.css`, `cadence-palette.js`, from this
repository's `shared/`) are this repository's own.

## Loaded when the page runs, not in the folder

| What | From | Author | Licence |
| --- | --- | --- | --- |
| [Pyodide](https://pyodide.org) (the version `site/pack/manifest.json` names) | jsDelivr | the Pyodide contributors | MPL-2.0 |
| [NumPy](https://numpy.org), as Pyodide's package | jsDelivr | the NumPy developers | BSD-3-Clause |
| IBM Plex Sans, IBM Plex Mono | Google Fonts | IBM Corp. | SIL Open Font License 1.1 |
| Sora | Google Fonts | The Sora Project Authors | SIL Open Font License 1.1 |
