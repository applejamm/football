#!/usr/bin/env python3
"""
2026 世界杯每日模拟流水线（T-3-3）：选最多 5 场竞彩赛事 → 预测 → 落盘 simulation/。

用法：
    python3 daily_simulate.py
    python3 daily_simulate.py --day 260614 --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from artifact_lib import (
    SNAPSHOT_FUNDAMENTALS_DIR,
    fundamentals_search_dirs,
    odds_search_dirs,
    resolve_snapshot,
)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from predict_engine import find_latest, run_predictions  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--day", help="比赛日 code；默认取最新 odds")
    p.add_argument("--limit", type=int, default=5, help="最多模拟场数")
    p.add_argument("--dir", default=str(SNAPSHOT_FUNDAMENTALS_DIR))
    args = p.parse_args(argv)

    if args.day:
        odds_path = find_latest(f"odds_{args.day}_*.json", odds_search_dirs())
    else:
        odds_path = find_latest("odds_*.json", odds_search_dirs())
    if not odds_path:
        print("[!] 无 odds 文件", file=sys.stderr)
        return 1

    odds_data = json.loads(odds_path.read_text("utf-8"))
    fund_path = find_latest("fundamentals_*.json", fundamentals_search_dirs())
    fundamentals_data = json.loads(fund_path.read_text("utf-8")) if fund_path else None

    matches = odds_data.get("matches", [])[: args.limit]
    odds_subset = {**odds_data, "matches": matches}
    results = run_predictions(odds_subset, fundamentals_data)

    sim_dir = ROOT / "simulation"
    sim_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    code = odds_data.get("match_date_code") or args.day or "daily"
    out = sim_dir / f"sim_{code}_{stamp}.json"
    payload = {
        "meta": {
            "schema_version": "1.0",
            "sim_date": stamp,
            "match_date_code": code,
            "limit": args.limit,
            "odds_source": odds_path.name,
            "pending_settlement": True,
        },
        "predictions": results,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    print(f"[OK] 每日模拟 {len(results)} 场 → {out.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
