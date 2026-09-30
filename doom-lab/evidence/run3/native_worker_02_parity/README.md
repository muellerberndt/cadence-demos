# CPU2 native parity

The new CPU2 worker matched all12Cadence source hashes, native executable/PK3/Python-extension hashes, Python3.11.16, Torch2.14.0+cpu, NumPy2.4.6, ViZDoom1.3.1 and Pillow12.3.0 against CPU1. The fixed existing development case Basic1220100000 under checkpointb6de81e8365aed8838f768d24d7630de55f90932714221a6cd9ed97452c044d6 (querybudget1024) then exactly reproduced all56native frame hashes, executed actions, tic/reward transitions and final outcome: native success,222tics,return-191.0. All56queries qualified. Timing and internal floating solver-state hashes were deliberately not claimed equal.

The check took24.88seconds. Full remote run: `/home/ec2-user/doom-v3-20260929/runs/native_worker_parity_01` on CPU2,79,082bytes. Local reference summary/decisions are small existing-episode fixtures; freeze and receipt document the new check. No reserved seed, training, or deployment was consumed.
