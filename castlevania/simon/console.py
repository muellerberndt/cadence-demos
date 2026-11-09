"""The console: stable-retro's FCEUmm core on your own Castlevania (U) PRG1 cartridge.

The ROM is not part of this folder. Put your dump at
``integration/Castlevania-Nes-v0/rom.nes`` (``python -m simon.rom <file or folder>`` finds and
copies it); its SHA-1 without the 16-byte iNES header must be ``ROM_SHA1``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .pad import BUTTONS, NOOP, pad_action, readings

ROM_SHA1 = "3dcb69a8c861c041aeb56c04e39adf6d332eda3a"  # Castlevania (U) (PRG1), headerless
GAME = "Castlevania-Nes-v0"
INTEGRATION = Path(__file__).resolve().parents[1] / "integration"
FRAMES_PER_DECISION = 12


def rom_sha1(path: Path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha1(data[16:] if data[:4] == b"NES\x1a" else data).hexdigest()


def screen(frame) -> np.ndarray:
    """The core crops 8 px on every edge (224 x 240); edge padding restores RAM coordinates."""
    frame = np.asarray(frame)
    if frame.shape == (224, 240, 3):
        return np.pad(frame, ((8, 8), (8, 8), (0, 0)), mode="edge")
    return frame


class Console:
    def __init__(self, integration: Path = INTEGRATION) -> None:
        import stable_retro as retro
        directory = Path(integration).resolve() / GAME
        rom = directory / "rom.nes"
        if not rom.exists():
            raise FileNotFoundError(f"no ROM at {rom}: run `python -m simon.rom <your dump>` first")
        if rom_sha1(rom) != ROM_SHA1:
            raise ValueError(f"{rom} is not Castlevania (U) PRG1 (headerless SHA-1 {ROM_SHA1})")
        retro.data.Integrations.add_custom_path(str(directory.parent))
        self.env = retro.make(GAME, state=retro.State.NONE, inttype=retro.data.Integrations.ALL,
                              use_restricted_actions=retro.Actions.ALL, render_mode=None)
        if tuple(self.env.buttons) != BUTTONS:
            raise ValueError("unexpected NES pad layout")
        self.env.initial_state = self.env.em.get_state()  # every reset is a power-on
        self.env.reset()

    def power_on(self, idle: int = 0):
        """Power on, press Start, wait for Simon, then ``idle`` decisions of nothing."""
        self.env.reset()
        pad = np.zeros(len(BUTTONS), np.uint8)
        start = pad.copy()
        start[BUTTONS.index("START")] = 1
        for count, buttons in ((60, pad), (1, start), (720, pad)):
            for _ in range(count):
                frame, *_ = self.env.step(buttons)
        ram = self.env.get_ram().copy()
        frame = screen(frame)
        for _ in range(idle):
            frame, ram, _ = self.decide(NOOP)
        return frame, ram

    def frames(self, action: int):
        """Hold one pad action for a decision, yielding every frame (for smooth video)."""
        pad = pad_action(action)
        for _ in range(FRAMES_PER_DECISION):
            frame, _, terminated, truncated, _ = self.env.step(pad)
            yield screen(frame), bool(terminated or truncated)
            if terminated or truncated:
                return

    def decide(self, action: int):
        done = False
        for frame, done in self.frames(action):
            pass
        return frame, self.env.get_ram().copy(), done

    def ram(self) -> np.ndarray:
        return self.env.get_ram().copy()

    def readings(self) -> dict:
        return readings(self.env.get_ram())

    def close(self) -> None:
        self.env.close()
