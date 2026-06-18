"""scan_candidates_lib 自测（T-5-1 ~ T-5-3）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scan_candidates_lib import (  # noqa: E402
    CATEGORY_LABELS,
    compute_ev,
    rank_top3_picks,
    rank_top6,
    scan_all,
)


def test_compute_ev():
    assert compute_ev(0.5, 2.0) == 0.0
    assert compute_ev(0.387, 2.29) == round(0.387 * 2.29 - 1, 4)


def test_scan_covers_six_categories():
    odds_path = ROOT / "odds_260616_20260616-212759.json"
    assert odds_path.exists()
    import json

    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    result = scan_all(odds, include_parlays=True)
    cats = set(result["scan_summary"]["by_category"].keys())
    assert CATEGORY_LABELS["wdl"] in cats or CATEGORY_LABELS["hcap"] in cats
    assert CATEGORY_LABELS["total"] in cats
    assert CATEGORY_LABELS["score"] in cats
    assert CATEGORY_LABELS["parlay"] in cats
    assert CATEGORY_LABELS["hafu"] in cats or "hafu" in CATEGORY_LABELS
    assert result["scan_summary"]["total_candidates"] > 100
    assert result["scan_summary"]["rejected_below"] > 0


def test_rank_top6_has_hero():
    odds_path = ROOT / "odds_260616_20260616-212759.json"
    pred_path = ROOT / "prediction_260616_20260616-214115.json"
    import json

    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    scan = scan_all(odds)
    funnel = rank_top6(scan, prediction=pred, top_n=6)
    assert len(funnel["top6"]) <= 6
    assert funnel["hero"] is not None
    assert funnel["hero"]["status"] == "主推"
    assert funnel["hero"]["scheme_id"] == "S1"
    assert "composite_score" in funnel["hero"]
    assert "dims" in funnel["hero"]


def test_rank_top3_by_win_gross():
    odds_path = ROOT / "odds_260616_20260616-212759.json"
    pred_path = ROOT / "prediction_260616_20260616-214115.json"
    import json

    odds = json.loads(odds_path.read_text(encoding="utf-8"))
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    scan = scan_all(odds)
    funnel = rank_top6(scan, prediction=pred, top_n=6)
    top3 = funnel["top3"]
    assert len(top3) <= 3
    assert len(top3) >= 1
    assert top3[0]["pick_label_user"] == "方案 A（赢利最高）"
    gross = [row["win_gross"] for row in top3]
    assert gross == sorted(gross, reverse=True)


def test_scan_hafu_when_present():
    window = sorted(ROOT.glob("odds_window_24h_*.json"))
    if not window:
        return
    import json

    odds = json.loads(window[-1].read_text(encoding="utf-8"))
    result = scan_all(odds, include_parlays=False)
    assert CATEGORY_LABELS["hafu"] in result["scan_summary"]["by_category"]


if __name__ == "__main__":
    test_compute_ev()
    test_scan_covers_six_categories()
    test_rank_top6_has_hero()
    test_rank_top3_by_win_gross()
    test_scan_hafu_when_present()
    print("OK")
