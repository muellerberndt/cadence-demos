"""The MLP control: a small torch network trained by DAgger on the same labels (control only).

Two hidden layers of 256 (ReLU), one softmax head per slot, cross-entropy summed over the slots.
Every decision takes one Adam step on the batch of cells and one on a replay minibatch drawn from
the last ``buffer`` labelled moments, so the control sees the same states and labels as the brain
in the same order. It establishes what the labels and the observation afford a conventional
learner; it is not a Cadence result.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch
from torch import nn

torch.set_num_threads(max(1, int(os.environ.get("OMP_NUM_THREADS", "1"))))


class SlotMLP(nn.Module):
    def __init__(self, inputs: int, slots, hidden: int = 256) -> None:
        super().__init__()
        self.slots = tuple(int(s) for s in slots)
        self.inputs, self.hidden = int(inputs), int(hidden)
        self.net = nn.Sequential(nn.Linear(inputs, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(),
                                 nn.Linear(hidden, int(sum(self.slots))))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    def heads(self, logits: torch.Tensor) -> list[torch.Tensor]:
        return list(torch.split(logits, list(self.slots), dim=1))


def act(model: SlotMLP, x: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        logits = model(torch.as_tensor(np.asarray(x, dtype=np.float32)))
    return np.stack([h.argmax(dim=1).numpy() for h in model.heads(logits)], axis=1).astype(np.int64)


class Trainer:
    def __init__(self, inputs: int, slots, seed: int, lr: float = 1e-3, buffer: int = 50_000, replay: int = 256) -> None:
        torch.manual_seed(seed)
        self.model = SlotMLP(inputs, slots)
        self.opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.buffer, self.replay = buffer, replay
        self.x = np.zeros((buffer, inputs), dtype=np.float32)
        self.y = np.zeros((buffer, len(self.model.slots)), dtype=np.int64)
        self.filled, self.cursor = 0, 0
        self.rng = np.random.default_rng(seed)

    def _loss(self, x: np.ndarray, labels: np.ndarray) -> torch.Tensor:
        logits = self.model(torch.as_tensor(np.asarray(x, dtype=np.float32)))
        y = torch.as_tensor(np.asarray(labels, dtype=np.int64))
        return sum(nn.functional.cross_entropy(h, y[:, k]) for k, h in enumerate(self.model.heads(logits)))

    def lesson(self, x: np.ndarray, labels: np.ndarray) -> dict:
        n = len(x)
        loss = self._loss(x, labels)
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        idx = (self.cursor + np.arange(n)) % self.buffer
        self.x[idx], self.y[idx] = np.asarray(x, dtype=np.float32), np.asarray(labels, dtype=np.int64)
        self.cursor = int((self.cursor + n) % self.buffer)
        self.filled = min(self.buffer, self.filled + n)
        replay = None
        if self.filled >= self.replay:
            pick = self.rng.integers(0, self.filled, self.replay)
            replay = self._loss(self.x[pick], self.y[pick])
            self.opt.zero_grad()
            replay.backward()
            self.opt.step()
        return {"loss": float(loss), "replay_loss": None if replay is None else float(replay)}

    def act(self, x: np.ndarray) -> np.ndarray:
        return act(self.model, x)

    def scale_lr(self, factor: float) -> float:
        for group in self.opt.param_groups:
            group["lr"] *= factor
        return float(self.opt.param_groups[0]["lr"])

    @property
    def lr(self) -> float:
        return float(self.opt.param_groups[0]["lr"])

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        torch.save({"state": self.model.state_dict(), "inputs": self.model.inputs, "slots": self.model.slots,
                    "hidden": self.model.hidden}, path)
        return path


def load(path: str | Path) -> SlotMLP:
    data = torch.load(path, map_location="cpu", weights_only=False)
    model = SlotMLP(data["inputs"], data["slots"], data["hidden"])
    model.load_state_dict(data["state"])
    model.eval()
    return model
