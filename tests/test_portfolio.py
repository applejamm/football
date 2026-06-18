"""portfolio_lib 自测（T-5-9 双方案择优）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from portfolio_lib import (  # noqa: E402
    MODE_DEFENSIVE,
    MODE_OFFENSIVE,
    build_defensive_portfolio,
    build_offensive_portfolio,
    select_portfolio_plan,
)
from scan_candidates_lib import scan_all, rank_top6  # noqa: E402


def test_offensive_and_defensive_differ():
    odds_path = ROOT / "odds_window_24h_20260618-210344.json"
    pred_path = ROOT / "prediction_260619_20260618-210344.json"
    if not odds_path.is_file():
        return
    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    scan = scan_all(odds)
    rank_top6(scan, prediction=pred)
    off = build_offensive_portfolio(scan, pred, budget=200)
    deff = build_defensive_portfolio(scan, pred, budget=200)
    assert off and deff
    assert off["mode"] == MODE_OFFENSIVE
    assert deff["mode"] == MODE_DEFENSIVE
    assert off["leg_count"] <= 2
    assert deff["leg_count"] >= 3


def test_select_portfolio_plan_auto():
    odds_path = ROOT / "odds_window_24h_20260618-210344.json"
    pred_path = ROOT / "prediction_260619_20260618-210344.json"
    if not odds_path.is_file():
        return
    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    scan = scan_all(odds)
    plan = select_portfolio_plan(scan, pred, budget=200)
    assert plan is not None
    assert plan["mode"] in (MODE_DEFENSIVE, MODE_OFFENSIVE)
    assert plan["primary"]["total_stake"] == 200
    assert plan["selection_reason"]
    assert plan["alternate"] is not None


if __name__ == "__main__":
    test_offensive_and_defensive_differ()
    test_select_portfolio_plan_auto()
    print("OK")
