"""Breeding: the 0.95 brain genes compose, mutation stays valid, and an anchor never changes."""

import hashlib
import random
from dataclasses import replace
from pathlib import Path

import pytest

from arena import breed
from arena.brain import compose
from arena.parts import stock_designs


@pytest.mark.parametrize("layout", list(breed.LAYOUTS), ids=str)
def test_every_layout_composes(layout):
    body = replace(stock_designs()[0], genes={"modules": list(layout)})
    assert compose(body).describe()["layout"]["modules"] == list(layout)


@pytest.mark.parametrize("teaching", breed.TEACHING)
@pytest.mark.parametrize("recall", [False, True])
def test_recall_and_teaching_genes_compose(recall, teaching):
    body = replace(stock_designs()[1], genes={"recall": recall, "teaching": teaching})
    assert ("recall" in compose(body).describe().get("memories", {})) == recall


def test_mutations_stay_valid_and_reach_the_new_genes():
    rng = random.Random(3)
    parent, seen = stock_designs()[2], set()
    for k in range(60):
        child, log = breed.mutate(parent, f"c{k}", seed=k, rng=rng)
        seen.update(entry.split()[0] for entry in log)
        assert child.slots and child.genes.get("eta", 0.03) >= 0.002
        parent = child
    assert {"layout", "recall", "teaching"} & seen


def test_a_pool_fight_leaves_the_anchor_file_unchanged(tmp_path):
    root = Path(__file__).resolve().parents[1] / "league-live"
    pool = breed.reference_pool(root, ["Cart", "Random-Tumbler"])
    before = hashlib.sha256(Path(pool[0]["brain_path"]).read_bytes()).hexdigest()
    body = stock_designs()[0]
    path = tmp_path / "cand.npz"
    compose(body).save(path)
    cand = [{"name": body.name, "blueprint": body.to_dict(), "brain_path": str(path), "owed": None}]
    out = breed._pool_fight((cand, pool, 1, 60, 50, 3.5, None))
    assert set(out["stats"]) == {body.name, "ref:Cart", "ref:Random-Tumbler"}
    assert hashlib.sha256(Path(pool[0]["brain_path"]).read_bytes()).hexdigest() == before
