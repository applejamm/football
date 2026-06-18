#!/usr/bin/env python3
"""异常场景测试（T-3-5 ~ T-3-7）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from predict_lib import predict_match  # noqa: E402


def test_injury_scenario():
    pred = predict_match(
        "Brazil", "Serbia",
        features={
            "last_five_games": [],
            "missing": [],
            "injuries": [{"team": "home", "severity": "major"}],
            "news_headlines": [{"headline": "Star player injury doubt before kickoff"}],
        },
        cn_odds={"胜": 1.3, "平": 5.0, "负": 10.0},
    )
    assert pred["dimensions"]["personnel"]["available"] is True
    assert any("伤病" in (s.get("logic") or "") or pred["scenario_flags"] for s in pred["schemes"])


def test_must_win_scenario():
    pred = predict_match(
        "Mexico", "Argentina",
        features={
            "last_five_games": [],
            "news_headlines": [{"headline": "Mexico face must win elimination clash"}],
        },
        cn_odds={"胜": 4.0, "平": 3.5, "负": 1.8},
    )
    assert pred["dimensions"]["tournament"]["score"] != 50 or "must win" in pred["dimensions"]["tournament"]["detail"].lower() or "关键词" in pred["dimensions"]["tournament"]["detail"]


def test_high_draw_h2h():
    pred = predict_match(
        "Uruguay", "South Korea",
        features={
            "last_five_games": [],
            "h2h_last_three": [
                {"date": "2020-01-01", "result": "D", "score": "0-0"},
                {"date": "2018-01-01", "result": "D", "score": "1-1"},
                {"date": "2016-01-01", "result": "D", "score": "2-2"},
            ],
        },
        cn_odds={"胜": 2.0, "平": 3.2, "负": 3.8},
        ref_date="2022-11-24",
    )
    assert any("平局" in f for f in pred.get("scenario_flags", []))


def main() -> int:
    test_injury_scenario()
    test_must_win_scenario()
    test_high_draw_h2h()
    print("[OK] 异常场景测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
