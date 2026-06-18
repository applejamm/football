"""virtual_tracking_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from virtual_tracking_lib import (  # noqa: E402
    evaluate_candidate,
    handicap_wdl,
    parse_scores_arg,
    virtual_pnl,
)


def test_handicap_france_minus1():
    assert handicap_wdl(2, 0, -1) == "胜"  # 法国 2:0 让球胜
    assert handicap_wdl(2, 1, -1) == "平"  # 净胜 1
    assert handicap_wdl(1, 1, -1) == "负"


def test_evaluate_wdl_draw():
    c = {
        "id": "T1",
        "match_no": "周日010",
        "play_type": "wdl",
        "pick": "平",
        "odds": 3.38,
    }
    assert evaluate_candidate(c, {"周日010": (2, 2)}) is True
    assert evaluate_candidate(c, {"周日010": (2, 1)}) is False


def test_virtual_pnl():
    assert virtual_pnl(50, 3.38, True) == round(50 * 3.38 - 50, 2)
    assert virtual_pnl(50, 2.0, False) == -50


def test_parse_scores():
    s = parse_scores_arg("周日010:2:2,周二017:2-1")
    assert s["周日010"] == (2, 2)
    assert s["周二017"] == (2, 1)


if __name__ == "__main__":
    test_handicap_france_minus1()
    test_evaluate_wdl_draw()
    test_virtual_pnl()
    test_parse_scores()
    print("OK")
