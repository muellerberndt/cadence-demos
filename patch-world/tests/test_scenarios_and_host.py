import json

from patchworld import scenarios
from patchworld.brain import compose
from patchworld.genes import FOUNDER
from patchworld.host import BrainHost, WorldHost


def group(tmp_path, n=2):
    out = []
    for i in range(n):
        g = dict(FOUNDER, width=16)
        compose(g, seed=i).save(tmp_path / f"f{i}.npz")
        out.append({"name": f"f{i}", "file": f"f{i}.npz", "genes": g})
    (tmp_path / "founders.json").write_text(json.dumps({"founders": out}))
    return out


def test_flip_and_controls_scenarios_record_every_creature(tmp_path):
    roster = group(tmp_path)
    from patchworld.brain import load

    founders = [{**f, "brain": load(tmp_path / f["file"])} for f in roster]
    rows = scenarios.flip(100, founders, summer=60, winter=60)
    assert sorted(r["kind"] for r in rows) == ["frozen", "frozen", "live", "live"]
    rows = scenarios.controls(100, founders, moments=50)
    assert len(rows) == 6 and all(r["age"] <= 50 for r in rows)


def test_world_and_brain_hosts_round_trip(tmp_path):
    group(tmp_path)
    world = WorldHost(str(tmp_path), seed=1, cap=3, frozen=1, random=1)
    hosts = [BrainHost(str(tmp_path), seed=1), BrainHost(str(tmp_path), seed=2)]
    opening = world.handle({"command": "opening"})
    where = {}
    for i, b in enumerate(opening["births"]):
        hosts[i % 2].handle({"command": "born", "payload": {"births": [b]}})
        where[b["id"]] = i % 2
    requests = opening["requests"]
    for _ in range(5):
        replies = {}
        for k, h in enumerate(hosts):
            mine = [r for r in requests if where.get(r["id"]) == k]
            replies.update(h.handle({"command": "answer", "payload": {"requests": mine}})["replies"])
        res = world.handle({"command": "advance", "payload": {"replies": replies}})
        requests = res["requests"]
    # a brain carried between workers as checkpoint bytes
    cid = next(i for i, k in where.items() if k == 0 and opening["births"][0]["id"] == i)
    data = hosts[0].handle({"command": "export", "payload": {"id": cid}})["brain"]
    child = {"id": 999, "kind": "live", "genes": dict(FOUNDER, width=16), "parent": cid}
    hosts[1].handle({"command": "born", "payload": {"births": [child], "brains": {"999": data}}})
    assert 999 in hosts[1].minds.minds
    world.handle({"command": "control", "payload": {"action": "flip"}})
    assert not world.eco.world.summer
