"""enrich_fundamentals_forecast 自测。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enrich_fundamentals_forecast import enrich_fundamentals_data  # noqa: E402


def test_enrich_writes_forecast_fields():
    fund_path = ROOT / "fundamentals_fifa.world_20260618-002404.json"
    odds_path = ROOT / "odds_260617_20260617-202235.json"
    if not fund_path.exists() or not odds_path.exists():
        return
    fund = json.loads(fund_path.read_text("utf-8"))
    odds = json.loads(odds_path.read_text("utf-8"))
    enriched, _, count = enrich_fundamentals_data(fund, odds)
    assert enriched["meta"]["forecast_enriched"]
    assert count >= 4
    with_fc = [r for r in enriched["records"] if r.get("forecast")]
    assert len(with_fc) >= 4
    fc = with_fc[0]["forecast"]
    assert fc["wdl"] in ("胜", "平", "负")
    assert fc["score"]
    assert fc["total_goals"]


if __name__ == "__main__":
    test_enrich_writes_forecast_fields()
    print("OK")
