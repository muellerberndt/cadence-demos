"""Motion models for the rover's two public motor/odometry ports.

Every learner sees only two commanded motor values and learns two measured
motion values. Wheel gains, phase names, targets and simulator parameters are
deliberately absent. Action selection and replay belong to the application.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import cadence
import numpy as np
from cadence.experimental.equilibrium import Brain, Cortex, SettlementError

CADENCE_VERSION = "0.70.0"
if cadence.__version__ != CADENCE_VERSION:
    raise ImportError(
        f"Rover Lab is bound to cadence-net=={CADENCE_VERSION}; found {cadence.__version__}. "
        "Install the pinned release with: python3 -m pip install -r requirements.txt"
    )


SCHEMA = "pragma.rover.model/1"
KINDS = ("coupled", "observer", "adaptive", "mlp")
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _pair(values, name, *, bound=None):
    if isinstance(values, (str, bytes)) or len(values) != 2:
        raise ValueError(f"{name} must contain two finite numbers")
    if any(isinstance(value, (bool, np.bool_)) for value in values):
        raise ValueError(f"{name} must contain numbers, not booleans")
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain two finite numbers")
    if bound is not None and any(abs(value) > bound for value in result):
        raise ValueError(f"{name} must lie in [-{bound}, {bound}]")
    return result


def _action(value):
    return _pair(value, "motor commands", bound=0.8)


def _counter(value):
    if type(value) is not int or value < 0:
        raise ValueError("model counters must be nonnegative integers")
    return value


def _base_snapshot(model):
    return {
        "schema": SCHEMA,
        "implementation_sha256": IMPLEMENTATION_SHA256,
        "kind": model.kind,
        "accepted": model.accepted,
        "presentations": model.presentations,
    }


class CadenceModel:
    """Four processing patches in three populations, settled as one equilibrium.

    ``coupled`` is the default brain: populations read the motors and one
    another's live states. ``observer`` is the optional addition: the same
    populations also read exact prediction errors. Candidate forecasts are
    unclamped solves in both layouts.
    """

    def __init__(self, kind, seed):
        self.kind = kind
        cortex = Cortex(seed=seed, parameter_prior=0.1)
        motors = cortex.input("motors", shape=2)
        body = cortex.column("body", patches=1, inputs=motors)
        if kind == "coupled":
            middle = cortex.column("integration", patches=1, inputs=(motors, body))
            output = cortex.column("motion", patches=2, inputs=(motors, body, middle))
        else:
            middle = cortex.observer("integration", patches=1, inputs=motors, observes=body)
            output = cortex.observer("motion", patches=2, inputs=motors, observes=(body, middle))
        cortex.output("motion_readout", shape=2, reads=output)
        self.brain = cortex.build()
        self.accepted = self.presentations = 0
        self._errors = [0.0] * self.brain.graph.n_patches
        self._names = self._patch_names()

    def _patch_names(self):
        return [
            f"{population['name']} {index + 1}"
            for population in self.brain.inspect()["populations"]
            for index in range(population["patches"])
        ]

    @staticmethod
    def _qualified(result):
        if not result["qualified"]:
            raise SettlementError(
                f"Rover motion solve refused: {result['reason']}; "
                f"stationarity={result['stationarity']:.6g}"
            )
        return list(result["outputs"]["motion_readout"])

    def query(self, actions):
        return [
            self._qualified(self.brain.settle({"motors": _action(action)}))
            for action in actions
        ]

    def activate(self, action):
        result = self.brain.step({"motors": _action(action)})
        prediction = self._qualified(result)
        self._errors = list(result["errors"])
        return prediction

    def learn(self, action, motion):
        inputs = {"motors": _action(action)}
        targets = {"motion_readout": _pair(motion, "measured motion", bound=1.0)}
        self.presentations += 1
        result = self.brain.observe(inputs, targets, source="witness")
        if result["accepted"]:
            self.accepted += 1
            self._errors = list(result["errors"])
        return result["accepted"]

    def activity(self):
        return [
            {"name": name, "state": state, "error": error}
            for name, state, error in zip(
                self._names, self.brain.state, self._errors, strict=True
            )
        ]

    def parameters(self):
        return len(self.brain.weights) + len(self.brain.biases)

    def snapshot(self):
        return {
            **_base_snapshot(self),
            "brain": self.brain.snapshot(),
            "errors": list(self._errors),
        }


class AdaptiveModel:
    """Two-output affine recursive least squares with forgetting factor 0.97.

The estimator knows only that command-to-motion dynamics may be affine. It
does not receive the simulator's wheel equation or perturbation information.
"""

    def __init__(self, seed=0):
        del seed
        self.kind = "adaptive"
        self.forgetting = 0.97
        self.coefficients = [[0.0] * 3 for _ in range(2)]
        self.covariance = [
            [100.0 if row == column else 0.0 for column in range(3)]
            for row in range(3)
        ]
        self.accepted = self.presentations = 0
        self._last = [0.0, 0.0]
        self._errors = [0.0, 0.0]

    def query(self, actions):
        results = []
        for action in actions:
            features = [*_action(action), 1.0]
            results.append([
                sum(weight * value for weight, value in zip(row, features))
                for row in self.coefficients
            ])
        return results

    def activate(self, action):
        self._last = self.query([action])[0]
        self._errors = [0.0, 0.0]
        return list(self._last)

    def learn(self, action, motion):
        command = _action(action)
        target = _pair(motion, "measured motion", bound=1.0)
        features = [*command, 1.0]
        forecast = self.query([command])[0]
        projected = [
            sum(value * coordinate for value, coordinate in zip(row, features))
            for row in self.covariance
        ]
        denominator = self.forgetting + sum(
            value * coordinate for value, coordinate in zip(projected, features)
        )
        gain = [value / denominator for value in projected]
        residual = [actual - predicted for actual, predicted in zip(target, forecast)]
        coefficients = [
            [weight + error * update for weight, update in zip(row, gain)]
            for row, error in zip(self.coefficients, residual)
        ]
        covariance = [
            [
                (self.covariance[row][column] - gain[row] * projected[column])
                / self.forgetting
                for column in range(3)
            ]
            for row in range(3)
        ]
        # Roundoff can otherwise destroy symmetry over long online lives.
        covariance = [
            [(covariance[row][column] + covariance[column][row]) / 2 for column in range(3)]
            for row in range(3)
        ]
        if not all(
            math.isfinite(value)
            for matrix in (coefficients, covariance)
            for row in matrix
            for value in row
        ):
            raise FloatingPointError("adaptive estimator update became nonfinite")
        self.coefficients, self.covariance = coefficients, covariance
        self.presentations += 1
        self.accepted += 1
        self._last = self.query([command])[0]
        self._errors = [actual - predicted for actual, predicted in zip(target, self._last)]
        return True

    def activity(self):
        return [
            {"name": name, "state": state, "error": error}
            for name, state, error in zip(
                ("forward estimate", "turn estimate"), self._last, self._errors
            )
        ]

    def parameters(self):
        return 6

    def snapshot(self):
        return {
            **_base_snapshot(self),
            "forgetting": self.forgetting,
            "coefficients": [row[:] for row in self.coefficients],
            "covariance": [row[:] for row in self.covariance],
            "last": self._last[:],
            "errors": self._errors[:],
        }


class MLPModel:
    """NumPy float64 2→24→24→2 tanh MLP, trained by full-state Adam."""

    def __init__(self, seed):
        self.kind = "mlp"
        rng = np.random.default_rng(seed)
        self.arrays = []
        for width_in, width_out in ((2, 24), (24, 24), (24, 2)):
            limit = 1.0 / math.sqrt(width_in)
            self.arrays.extend([
                rng.uniform(-limit, limit, (width_in, width_out)),
                rng.uniform(-limit, limit, width_out),
            ])
        self.first_moments = [np.zeros_like(array) for array in self.arrays]
        self.second_moments = [np.zeros_like(array) for array in self.arrays]
        self.learning_rate = 0.01
        self.steps = self.accepted = self.presentations = 0
        self._last = [0.0, 0.0]
        self._errors = [0.0, 0.0]

    def _forward(self, values):
        hidden1 = np.tanh(values @ self.arrays[0] + self.arrays[1])
        hidden2 = np.tanh(hidden1 @ self.arrays[2] + self.arrays[3])
        output = np.tanh(hidden2 @ self.arrays[4] + self.arrays[5])
        return hidden1, hidden2, output

    def query(self, actions):
        values = [_action(action) for action in actions]
        if not values:
            return []
        output = self._forward(np.asarray(values, dtype=np.float64))[-1]
        if not np.isfinite(output).all():
            raise FloatingPointError("MLP forecast became nonfinite")
        return output.tolist()

    def activate(self, action):
        self._last = self.query([action])[0]
        self._errors = [0.0, 0.0]
        return self._last[:]

    def learn(self, action, motion):
        values = np.asarray(_action(action), dtype=np.float64)
        target = np.asarray(_pair(motion, "measured motion", bound=1.0), dtype=np.float64)
        hidden1, hidden2, output = self._forward(values)
        # Mean squared error over both motion coordinates: 2 / outputs = 1.
        derivative3 = (output - target) * (1.0 - output * output)
        derivative2 = (derivative3 @ self.arrays[4].T) * (1.0 - hidden2 * hidden2)
        derivative1 = (derivative2 @ self.arrays[2].T) * (1.0 - hidden1 * hidden1)
        gradients = [
            np.outer(values, derivative1), derivative1,
            np.outer(hidden1, derivative2), derivative2,
            np.outer(hidden2, derivative3), derivative3,
        ]
        next_step = self.steps + 1
        moments1 = [0.9 * old + 0.1 * gradient for old, gradient in zip(self.first_moments, gradients)]
        moments2 = [0.999 * old + 0.001 * gradient * gradient for old, gradient in zip(self.second_moments, gradients)]
        arrays = [
            parameter - self.learning_rate * (first / (1.0 - 0.9 ** next_step))
            / (np.sqrt(second / (1.0 - 0.999 ** next_step)) + 1e-8)
            for parameter, first, second in zip(self.arrays, moments1, moments2)
        ]
        if not all(np.isfinite(array).all() for array in arrays + moments1 + moments2):
            raise FloatingPointError("MLP optimizer update became nonfinite")
        self.arrays, self.first_moments, self.second_moments = arrays, moments1, moments2
        self.steps = next_step
        self.accepted += 1
        self.presentations += 1
        self._last = self.query([values])[0]
        self._errors = (target - np.asarray(self._last)).tolist()
        return True

    def activity(self):
        return [
            {"name": name, "state": state, "error": error}
            for name, state, error in zip(
                ("forward readout", "turn readout"), self._last, self._errors
            )
        ]

    def parameters(self):
        return sum(array.size for array in self.arrays)

    def snapshot(self):
        return {
            **_base_snapshot(self),
            "arrays": [array.tolist() for array in self.arrays],
            "first_moments": [array.tolist() for array in self.first_moments],
            "second_moments": [array.tolist() for array in self.second_moments],
            "learning_rate": self.learning_rate,
            "steps": self.steps,
            "last": self._last[:],
            "errors": self._errors[:],
        }


def make_model(kind, seed):
    if kind not in KINDS:
        raise ValueError(f"unknown rover model {kind!r}; choose from {KINDS}")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if kind == "adaptive":
        return AdaptiveModel(seed)
    if kind == "mlp":
        return MLPModel(seed)
    return CadenceModel(kind, seed)


def _matrix(data, shape, name):
    matrix = np.asarray(data, dtype=np.float64)
    if matrix.shape != shape or not np.isfinite(matrix).all():
        raise ValueError(f"checkpoint {name} must have finite shape {shape}")
    return matrix


def model_from_snapshot(data):
    """Restore parameters, admission counts, optimizer and retained display state."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported rover model checkpoint")
    if data.get("implementation_sha256") != IMPLEMENTATION_SHA256:
        raise ValueError("rover model checkpoint belongs to different source code")
    model = make_model(data.get("kind"), 0)
    model.accepted = _counter(data["accepted"])
    model.presentations = _counter(data["presentations"])
    if model.accepted > model.presentations:
        raise ValueError("checkpoint accepted count exceeds presentations")
    if isinstance(model, CadenceModel):
        original = model.brain.inspect()
        model.brain = Brain.from_snapshot(data["brain"])
        restored = model.brain.inspect()
        if any(original[field] != restored[field] for field in ("inputs", "populations", "outputs")):
            raise ValueError("checkpoint brain layout does not match rover model kind")
        model._errors = _matrix(data["errors"], (model.brain.graph.n_patches,), "errors").tolist()
        model._names = model._patch_names()
    else:
        model._last = _pair(data["last"], "checkpoint readout")
        model._errors = _pair(data["errors"], "checkpoint errors")
        if isinstance(model, AdaptiveModel):
            if data["forgetting"] != model.forgetting:
                raise ValueError("checkpoint changed adaptive forgetting factor")
            model.coefficients = _matrix(data["coefficients"], (2, 3), "coefficients").tolist()
            model.covariance = _matrix(data["covariance"], (3, 3), "covariance").tolist()
        else:
            if data["learning_rate"] != model.learning_rate:
                raise ValueError("checkpoint changed MLP learning rate")
            shapes = [array.shape for array in model.arrays]
            for field in ("arrays", "first_moments", "second_moments"):
                if len(data[field]) != len(shapes):
                    raise ValueError(f"checkpoint has wrong number of {field}")
                setattr(model, field, [
                    _matrix(value, shape, field)
                    for value, shape in zip(data[field], shapes, strict=True)
                ])
            if any((array < 0).any() for array in model.second_moments):
                raise ValueError("checkpoint Adam second moments must be nonnegative")
            model.steps = _counter(data["steps"])
            if model.steps != model.accepted:
                raise ValueError("checkpoint Adam steps disagree with admissions")
    return model
