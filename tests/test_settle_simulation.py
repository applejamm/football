"""settle_simulation 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import settle_simulation as ss  # noqa: E402


def test_settle_match():
    pred = {
        "match_no": "周日010",
        "home_cn": "荷兰",
        "away_cn": "日本",
        "prediction": {
            "schemes": [
                {"id": "P1", "wdl": "胜", "total_goals": "2", "score": "—", "rank": 1},
                {"id": "P2", "wdl": "平", "total_goals": "4", "score": "2:2", "rank": 2},
                {"id": "P3", "wdl": "负", "total_goals": "1", "score": "0:1", "rank": 3},
            ]
        },
    }
    st = ss.settle_match(pred, 2, 2, top_n=3)
    assert st["actual_score"] == "2:2"
    assert st["top1_hit"] is False
    assert st["topn_any_hit"] is True
    assert st["schemes_evaluated"][1]["hit"] is True


def test_normalize_score():
    assert ss.normalize_score("2-2") == (2, 2)
    assert ss.normalize_score("2:2") == (2, 2)


if __name__ == "__main__":
    test_normalize_score()
    test_settle_match()
    print("OK settle_simulation tests")
