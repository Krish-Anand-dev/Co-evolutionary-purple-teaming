import csv
import math

import pytest

from src.rules.loader import load_rules
from src.rules.rating import (
    DIMENSIONS, build_rating_items, pairwise_agreement, quadratic_weighted_kappa, read_ratings, write_rating_files,
)
from tests.test_static_rules import STATIC


def rules_as_dicts(tag):
    out = []
    for r in load_rules(STATIC):
        d = r.to_dict()
        d["rule_id"] = f"{tag}_{d['rule_id']}"
        d["agent_id"] = "blue_3"
        d["round"] = 7
        out.append(d)
    return out


CONDS = {"static": rules_as_dicts("s"), "llm": rules_as_dicts("l"), "fsm": rules_as_dicts("f")}


def test_sheet_is_blinded():
    sheet, key = build_rating_items(CONDS, 4, seed=1)
    assert len(sheet) == len(key) == 12
    header = set(sheet[0])
    assert not header & {"rule_id", "agent_id", "round", "condition_name"}
    text = " ".join(str(v) for row in sheet for v in row.values())
    assert "static_0" not in text and "blue_3" not in text and "s_static" not in text
    assert {k["condition"] for k in key} == {"static", "llm", "fsm"}


def test_balanced_and_shuffled_across_conditions():
    sheet, key = build_rating_items(CONDS, 5, seed=2)
    counts = {c: sum(k["condition"] == c for k in key) for c in CONDS}
    assert counts == {"static": 5, "llm": 5, "fsm": 5}
    order = [k["condition"] for k in key]
    assert order != sorted(order)              # not grouped by condition


def test_deterministic_and_seed_sensitive():
    a = build_rating_items(CONDS, 4, seed=3)
    assert a == build_rating_items(CONDS, 4, seed=3)
    assert a != build_rating_items(CONDS, 4, seed=4)


def test_fewer_rules_than_requested_takes_all():
    sheet, _ = build_rating_items({"x": rules_as_dicts("x")[:2]}, 10, seed=0)
    assert len(sheet) == 2


def test_files_written_with_same_items_for_every_rater(tmp_path):
    sheet, key = build_rating_items(CONDS, 3, seed=5)
    write_rating_files(sheet, key, tmp_path, ["bhavit", "krish", "prateek"])
    ids = []
    for rater in ("bhavit", "krish", "prateek"):
        with (tmp_path / f"ratings_{rater}.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        ids.append([r["item_id"] for r in rows])
        assert all(r[d] == "" for r in rows for d in DIMENSIONS)
    assert ids[0] == ids[1] == ids[2]
    assert (tmp_path / "KEY_do_not_open_until_all_rated.csv").exists()


def test_kappa_perfect_chance_and_disagreement():
    assert quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert quadratic_weighted_kappa([1, 5, 1, 5], [5, 1, 5, 1]) < 0       # systematic opposition
    near = quadratic_weighted_kappa([1, 2, 3, 4, 5], [2, 3, 4, 5, 5])
    far = quadratic_weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert near > far


def test_kappa_hand_computed_example():
    # Two raters, 2 items, categories (1,2,3). a=[1,3], b=[1,3]: perfect -> 1.0
    assert quadratic_weighted_kappa([1, 3], [1, 3], (1, 2, 3)) == pytest.approx(1.0)
    # a=[1,2], b=[2,1], 3 categories: weights w01=0.25. obs: (1,2)=1,(2,1)=1. row=[1,1,0],col=[1,1,0].
    # num = .25*1 + .25*1 = .5 ; den = sum w_ij*row_i*col_j/n = (w01*1*1 + w10*1*1)/2 = .25 -> kappa = 1-.5/.25 = -1
    assert quadratic_weighted_kappa([1, 2], [2, 1], (1, 2, 3)) == pytest.approx(-1.0)


def test_kappa_constant_ratings_is_nan_and_bad_input_rejected():
    assert math.isnan(quadratic_weighted_kappa([3, 3, 3], [3, 3, 3]))
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([1, 2], [1])


def test_read_ratings_validates(tmp_path):
    sheet, key = build_rating_items(CONDS, 1, seed=6)
    write_rating_files(sheet, key, tmp_path, ["a"])
    with pytest.raises(ValueError, match="no score"):
        read_ratings(tmp_path / "ratings_a.csv")
    path = tmp_path / "ratings_a.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        r.update({d: "3" for d in DIMENSIONS})
    rows[0]["clarity"] = "9"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(ValueError, match="outside 1..5"):
        read_ratings(path)


def test_pairwise_agreement_three_raters():
    items = [f"item_{i}" for i in range(6)]
    base = [1, 2, 3, 4, 5, 3]
    def rater(scores):
        return {it: {d: s for d in DIMENSIONS} for it, s in zip(items, scores)}
    res = pairwise_agreement({"a": rater(base), "b": rater(base), "c": rater([5, 4, 3, 2, 1, 3])})
    assert res["clarity"]["a|b"] == pytest.approx(1.0)
    assert res["clarity"]["a|c"] < 0 and res["clarity"]["mean"] < 1.0
