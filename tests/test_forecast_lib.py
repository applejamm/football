"""forecast_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forecast_lib import forecast_summary, pick_forecast_score, pick_forecast_total_goals  # noqa: E402


def test_pick_forecast():
    score, p = pick_forecast_score({"1:0": 0.38, "2:0": 0.22})
    assert score == "1:0"
    assert p == 0.38
    tg, tp = pick_forecast_total_goals({"0": 0.1, "1": 0.26, "2": 0.24})
    assert tg == "1球"
    assert tp == 0.26


def test_forecast_summary_from_prediction_json():
    pred_path = ROOT / "prediction_260617_20260618-002841.json"
    if not pred_path.exists():
        return
    import json

    data = json.loads(pred_path.read_text("utf-8"))
    row = data["predictions"][0]
    fc = forecast_summary(row["prediction"])
    assert fc["wdl"] in ("胜", "平", "负")
    assert fc["score"] != "—"
    assert fc["top_scorelines"]
    assert fc["top_total_goals"]


if __name__ == "__main__":
    test_pick_forecast()
    test_forecast_summary_from_prediction_json()
    print("OK")
