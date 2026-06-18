"""predict_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from predict_lib import (  # noqa: E402
    compute_team_stats,
    devig_1x2,
    evaluate_scheme,
    predict_match,
    teams_match,
)


def test_devig_1x2():
    p = devig_1x2({"胜": 2.0, "平": 3.5, "负": 4.0})
    assert p is not None
    assert abs(sum(p.values()) - 1.0) < 1e-6


def test_teams_match_cn_en():
    assert teams_match("德国", "Germany")
    assert teams_match("日本", "Japan")
    assert teams_match("捷克", "Czechia")
    assert teams_match("南非", "South Africa")
    assert teams_match("波黑", "Bosnia-Herzegovina")
    assert teams_match("卡塔尔", "Qatar")


def test_compute_team_stats():
    events = [
        {"result": "W", "score": "2-0", "at_venue": "vs"},
        {"result": "W", "score": "1-0", "at_venue": "@"},
        {"result": "D", "score": "1-1", "at_venue": "vs"},
    ]
    s = compute_team_stats(events)
    assert s["n"] == 3
    assert s["win_rate"] == 2 / 3
    assert s["avg_gf"] is not None


def test_predict_match_minimal():
    pred = predict_match(
        "Germany",
        "Japan",
        features={
            "last_five_games": [
                {"team": "Germany", "events": [{"result": "W", "score": "3-0", "at_venue": "vs"}] * 5},
                {"team": "Japan", "events": [{"result": "W", "score": "2-1", "at_venue": "vs"}] * 3 + [{"result": "L", "score": "0-1", "at_venue": "@"}] * 2},
            ],
            "head_to_head": [],
            "missing": ["rosters_lineups_injuries"],
        },
        cn_odds={"胜": 1.5, "平": 4.0, "负": 6.0},
    )
    assert 3 <= len(pred["schemes"]) <= 5
    assert "strength" in pred["dimensions"]
    assert pred["outcome_probs"]["胜"] > pred["outcome_probs"]["负"]


def test_evaluate_scheme():
    scheme = {"wdl": "胜", "total_goals": "3", "score": "2:1"}
    assert evaluate_scheme(scheme, 2, 1) is True
    assert evaluate_scheme(scheme, 1, 1) is False


if __name__ == "__main__":
    test_devig_1x2()
    test_teams_match_cn_en()
    test_compute_team_stats()
    test_predict_match_minimal()
    test_evaluate_scheme()
    print("OK all tests passed")
