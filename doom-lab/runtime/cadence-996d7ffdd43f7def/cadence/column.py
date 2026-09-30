"""Processing-population definitions shared by columns and recursive observers.

A population groups patches using one common repair law. Its data and live
state/error observation connections determine its role in the joint solve.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class Population:
    """An exact patch count and its data and internal-observation connections."""

    name: str
    patches: int
    inputs: tuple
    observes: tuple

    def __repr__(self):
        inputs = tuple(source.name for source in self.inputs)
        observes = tuple(source.name for source in self.observes)
        return (
            f"Population(name={self.name!r}, patches={self.patches!r}, "
            f"inputs={inputs!r}, observes={observes!r})"
        )

    @property
    def role(self):
        """Layout role; observation function still requires causal testing."""
        return "observer" if self.observes else "processing"
