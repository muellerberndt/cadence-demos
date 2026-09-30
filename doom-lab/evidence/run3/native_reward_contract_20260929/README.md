# Native reward contract audit

Basic's installed WAD contains its ACS source in the `SCRIPTS` lump. The retained
`basic.acs` and `basic.cfg` bytes are bound to the original files by
`asset_hashes.json`. The new contract rejects any different cfg or WAD hash.

Basic adds 106 once when its sole one-hit monster dies, then exits. Its ammo
loop can subtract five at most once per tic (`delay(1)`); the cfg subtracts one
per living tic. Therefore an additional H native tics has conservative return
bound `[-6H, 106]`. The separately versioned contract in
`../../native_feedback_long.py` uses divisor `max(6H,106)`: 216,864,1800 for
36,144,300 tics. It stops at native terminal and uses no terminal bootstrap.
The original 36-tic v1 contract/divisor300 remains unchanged.

The divisor changes units, not the ordering of Basic's integer native returns.
The learner must still explicitly transform the complete native vector to its
bounded action-preference targets. Longer horizons may expose delayed kills;
that does not establish that learning will improve. A fixed founder continuation
can still produce poor counterfactual values.

Navigation's `my_way_home.acs` sets reward to one and exits when the armor is
collected. Its cfg charges 0.0001 per tic. Its existing36-tic divisor1 therefore
does not reject a successful branch as being above one. Sparse feedback far
from the goal remains a separate problem.

The official [ViZDoom scenario documentation](https://vizdoom.farama.org/environments/default/)
agrees with Basic's +106 kill,−5 shot,−1 tic convention. The bound above is tied
to the installed assets, rather than relying on documentation remaining current.
The [tagged1.3.1 native reward implementation](https://github.com/Farama-Foundation/ViZDoom/blob/1.3.1/src/lib/ViZDoomGame.cpp#L187)
adds the scripted reward difference and living reward; other reward components
default to zero.

Reproduce the extraction with the installed package:

```python
from pathlib import Path
import struct, vizdoom
root = Path(vizdoom.__file__).parent / 'scenarios'
for name in ('basic', 'my_way_home'):
    blob = (root / f'{name}.wad').read_bytes()
    _, count, directory = struct.unpack_from('<4sii', blob)
    for index in range(count):
        start, size, lump = struct.unpack_from('<ii8s', blob, directory + index*16)
        if lump.rstrip(b'\0') == b'SCRIPTS':
            Path(f'{name}.acs').write_bytes(blob[start:start+size])
```

The relevant tests cover asset drift, explicitly declared horizons, altered
contracts, selected-transition mismatch, old/new36 ranking equivalence, and a
long negative return below−300. The separate native verification receipt, when
present, checks one historical actual context on AWS; it is not a fresh skill
evaluation or a training result.
