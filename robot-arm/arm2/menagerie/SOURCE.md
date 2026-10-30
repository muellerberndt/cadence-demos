# franka_emika_panda from google-deepmind/mujoco_menagerie (fetched by `fetch.sh`)

- Source: https://github.com/google-deepmind/mujoco_menagerie, directory `franka_emika_panda/`
- Commit: f3b6013629c7b94f8ee93fd977b161fa8350f9bc (2026-10-23T16:08:31-07:00)
- License: Apache License 2.0 (the directory's own `LICENSE`; the repository root license is beside this note as `LICENSE_menagerie_root`). The Panda description is derived by the Menagerie authors from Franka Emika's public URDF (see its README).
- Files `fetch.sh` takes, bytes unchanged: `panda.xml`, `hand.xml`, `scene.xml`, `LICENSE`, `README.md`, `CHANGELOG.md`, `assets/*` (meshes). Not taken: `mjx_*.xml`, `panda.png`.
- Stage 2 never edits these files: `arm2/scene.py` loads `panda.xml` through `mujoco.MjSpec` and adds the table, block, bins, lamps and a `tcp` site at run time.
- One model change, at load time only (`arm2/scene.py`, `GRIP_STIFFNESS`): the finger tendon actuator `actuator8` runs at 1000 N/m (gain 0.1569, bias 0 / -1000 / -100) in place of the file's 100 N/m, so a 3 to 6 cm block is squeezed with 10 to 25 N; ctrl 255 still opens the fingers to 4 cm, 0 closes them. `fetch.sh` checks `panda.xml` (sha256 96ad67da...8ea273), `hand.xml` (d2a6539d...e786a) and the assets against the files the arm was trained with.
