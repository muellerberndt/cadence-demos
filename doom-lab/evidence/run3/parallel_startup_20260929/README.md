# First-engine directory race

The separate `baby_screen_01` evaluation exposed ViZDoom's native `_vizdoom` directory creation race when two engines first started in a previously unused working directory. The failure log and missing evaluation outcomes remain preserved by the evaluation owner; a failed worker is not a student gameplay failure or a completed evaluation.

`tasks.new_game()` now creates `Path.cwd() / '_vizdoom'` with Python's race-safe `mkdir(exist_ok=True)` before invoking `DoomGame()`. Both actual environment construction and configuration-only start-time inspection use this helper. The runtime wrapper does not change the process working directory, which would be unsafe in a browser server with multiple threads. No frozen training or earlier evaluation source was overwritten.

AWS regression `runs/parallel_startup_verify_01` created four new empty working directories and four new child processes per round. A process barrier released all four constructors together. All **16/16** engines initialized successfully, exposed Basic's configured and observed initial tic 14, and completed a four-tic native action. Total wall time was 0.976 seconds. The native code path was exercised on the actual Linux host, not mocked. The local `receipt.json` binds the frozen source and full result.

Final `tasks.py` SHA256: `2f807b7f8f1d7f5ab9bb886bb9efc8994bdfea2aa39b44e1a08fd3dfe852410d`. Regression freeze SHA256: `8b9fc8d227bba820e4a9ecf7d1495fe9c20f858be864ef111b3443cd16c50565`. Producer: `verify_parallel_startup.py`. The existing 21 focused environment/feedback tests also passed.

This verifies safe native initialization in the observed adverse condition; it does not establish gameplay competence. The earlier throughput benchmark used an already initialized directory and therefore could not reveal this first-start race.
