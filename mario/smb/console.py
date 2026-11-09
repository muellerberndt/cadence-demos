"""Super Mario Bros. on the nes-py emulator, started at one level.

Written for this demo on nes-py (MIT). The start sequence and the per-frame skips reproduce what
gym-super-mario-bros 7.4.0 does for a single level, because the brain was raised there (its code
is not included here: its licence is not an open one). `tests/` and the model card record that
this console and that package give the brain identical screens, RAM and answers.

One `Console` is one level from power-on:
- the title screen is skipped by tapping Start; while the level loads, the world, stage and area
  bytes are written so the chosen level loads instead of 1-1;
- the state at the first frame the level timer counts down is saved, and `reset()` returns there;
- after every frame: a dying Mario is killed at once, area-change timers are run out, and the
  frames where Mario can't be controlled (pipes, flagpole, lives screen) are stepped through;
- an attempt is over when Mario dies or reaches the flag (or the axe, in castles).
"""
from __future__ import annotations

from pathlib import Path

from nes_py import NESEnv

START, NOOP = 0x08, 0x00
# RAM (the community SMB RAM map, datacrystal.tcrf.net)
WORLD, STAGE, AREA = 0x075F, 0x075C, 0x0760
PRELEVEL_TIMER, CHANGE_AREA_TIMER = 0x07A0, 0x06DE
PLAYER_STATE, FLOAT_STATE, Y_VIEWPORT = 0x000E, 0x001D, 0x00B5
GAME_MODE, TIMER_DIGITS = 0x0770, 0x07F8
X_PAGE, X_PIXEL = 0x006D, 0x0086
ENEMY_TYPES = range(0x0016, 0x001B)
FLAGPOLE, BOWSER = 0x31, 0x2D
STATE_DYING, STATE_DEAD = 0x0B, 0x06
STATES_BUSY = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x07}


def area_of(world: int, stage: int) -> int:
    """The area byte that loads world-stage: in worlds 1, 2, 4 and 7 a pipe intro area comes
    before stages 2 to 4, so their area is one more than the stage."""
    if not (1 <= world <= 8 and 1 <= stage <= 4):
        raise ValueError(f"no level {world}-{stage}")
    return stage + 1 if world in (1, 2, 4, 7) and stage >= 2 else stage


class Console(NESEnv):
    def __init__(self, rom: str | Path, world: int = 1, stage: int = 1):
        super().__init__(str(rom))
        self.world, self.stage, self.area = world, stage, area_of(world, stage)
        self.reset()  # power on (there is no saved state yet)
        self._to_level()
        self._backup()  # every later reset() restores this

    # -- readings --------------------------------------------------------------------------
    @property
    def time(self) -> int:
        """The level timer as the screen shows it (three decimal digits in RAM)."""
        d = self.ram[TIMER_DIGITS:TIMER_DIGITS + 3]
        return int(d[0]) * 100 + int(d[1]) * 10 + int(d[2])

    @property
    def x(self) -> int:
        return int(self.ram[X_PAGE]) * 256 + int(self.ram[X_PIXEL])

    @property
    def dying(self) -> bool:
        return self.ram[PLAYER_STATE] == STATE_DYING or self.ram[Y_VIEWPORT] > 1

    @property
    def dead(self) -> bool:
        return self.ram[PLAYER_STATE] == STATE_DEAD

    @property
    def busy(self) -> bool:
        return int(self.ram[PLAYER_STATE]) in STATES_BUSY

    @property
    def world_over(self) -> bool:
        return self.ram[GAME_MODE] == 2

    @property
    def flag(self) -> bool:
        """At the flagpole (sliding down it) or past Bowser's axe."""
        if self.world_over:
            return True
        for a in ENEMY_TYPES:  # the first flagpole or Bowser on screen decides
            if self.ram[a] in (FLAGPOLE, BOWSER):
                return self.ram[FLOAT_STATE] == 3  # 3 = on the pole (not a vine)
        return False

    # -- start --------------------------------------------------------------------------------
    def _to_level(self):
        self._frame_advance(START)
        self._frame_advance(NOOP)
        while self.time == 0:  # tap Start until the level's timer appears
            self._frame_advance(START)
            self.ram[WORLD], self.ram[STAGE], self.ram[AREA] = self.world - 1, self.stage - 1, self.area - 1
            self._frame_advance(NOOP)
            self.ram[PRELEVEL_TIMER] = 0
        last = self.time
        while self.time >= last:  # on until the timer first counts down
            last = self.time
            self._frame_advance(START)
            self._frame_advance(NOOP)

    # -- nes-py hooks -------------------------------------------------------------------------
    def _get_reward(self):
        return 0.0

    def _get_done(self):
        return self.dying or self.dead or self.flag

    def _get_info(self):
        return {"flag_get": self.flag, "x_pos": self.x, "time": self.time}

    def _did_step(self, done):
        if done:
            return
        if self.dying:  # straight to dead: no death animation
            self.ram[PLAYER_STATE] = STATE_DEAD
            self._frame_advance(NOOP)
        t = int(self.ram[CHANGE_AREA_TIMER])
        if 1 < t < 255:
            self.ram[CHANGE_AREA_TIMER] = 1
        while self.busy or self.world_over:  # pipes, flagpole slide, lives screen
            self.ram[PRELEVEL_TIMER] = 0
            self._frame_advance(NOOP)

