import json

from arena.league import League, baseline_bots
from arena.parts import stock_designs
from arena.replay import render_html
from arena.royale import Fighter, elo_update, place_score, run_royale

DESIGNS = {b.name: b for b in stock_designs()}


def test_place_scores_and_elo_are_zero_sum():
    assert place_score(1, 4) == 1.0 and place_score(4, 4) == -1.0 and place_score(2, 3) == 0.0
    ratings = {"a": 1000.0, "b": 1000.0, "c": 1200.0}
    delta = elo_update(ratings, {"a": 1, "b": 2, "c": 3})
    assert abs(sum(delta.values())) < 1e-9
    assert delta["a"] > 0 and delta["c"] < 0


def test_a_royale_of_random_bots_and_a_newborn_records_a_replay():
    fighters = [
        Fighter("R1", DESIGNS["Tumbler"], "random"),
        Fighter("R2", DESIGNS["Mantis"], "random"),
        Fighter("B1", DESIGNS["Cart"], "brain"),
    ]
    out = run_royale(fighters, seed=5, duration=80, zone_moments=40, workers=0, save=False)
    assert sorted(r["place"] for r in out["results"]) == [1, 2, 3]
    replay = out["replay"]
    assert replay["format"].startswith("cadence-robot-arena/replay/")
    assert len(replay["frames"]) == out["moments"] + 1
    assert all(len(f["robots"]) == 3 for f in replay["frames"])
    for f in fighters:
        assert f.owed is not None and f.owed[1] is True
    page = render_html(replay)
    assert "/*REPLAY*/null" not in page and '"frames"' in page


def test_league_round_trip(tmp_path):
    root = tmp_path / "league"
    league = League(root)
    designs = [DESIGNS["Tumbler"], DESIGNS["Cart"]] + baseline_bots(stock_designs(), ("Mantis",))
    league.create(designs)
    assert (root / "brains" / "Tumbler.npz").exists()
    assert not (root / "brains" / "Random-Mantis.npz").exists()
    reports = league.nursery(["Tumbler"], moments=60, workers=1)
    assert reports[0]["robot"] == "Tumbler"
    row = league.royale(seed=3, duration=60, zone_moments=30, workers=0)
    assert len(row["results"]) == 3 and (root / row["page"]).exists()
    again = League(root)
    entry = again.data["robots"]["Tumbler"]
    assert entry["fights"] == 1 and entry["owed"] is not None and entry["owed"][1] is True
    # the second fight delivers the first fight's end with its first observation
    row2 = again.royale(seed=4, duration=40, zone_moments=30, workers=0)
    assert row2["id"] == 2 and again.data["robots"]["Tumbler"]["fights"] == 2
    assert json.loads((root / "league.json").read_text())["fights"][1]["id"] == 2
