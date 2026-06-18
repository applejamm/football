#!/usr/bin/env python3
"""
玩法全量扫描 CLI（T-5-1）+ Top6 / 主推漏斗（T-5-2 / T-5-3）。

用法：
    python3 scan_candidates.py --odds odds_260616_20260616-212759.json
    python3 scan_candidates.py --odds odds_*.json --prediction prediction_*.json --out validation/drafts/scan_260616.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scan_candidates_lib import load_json, rank_top6, scan_all, write_json  # noqa: E402
from strategy_gates_lib import enrich_scan_payload  # noqa: E402


def resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    ap = argparse.ArgumentParser(description="竞彩玩法全量扫描 + Top6 漏斗")
    ap.add_argument("--odds", required=True, help="odds_*.json")
    ap.add_argument("--prediction", help="prediction_*.json（二次评估用）")
    ap.add_argument("--strategy", help="STRATEGY_DEFAULT.yaml 路径")
    ap.add_argument("--no-parlay", action="store_true", help="跳过 2 串 1 扫描")
    ap.add_argument("--out", help="输出 JSON 路径（默认 validation/drafts/scan_<code>_<ts>.json）")
    ap.add_argument("--budget", type=int, help="有效预算（写入 strategy_gates.budget，可选）")
    ap.add_argument("--top", type=int, default=6, help="Top N（默认 6）")
    args = ap.parse_args()

    odds_path = resolve(args.odds)
    odds = load_json(odds_path)
    strategy = resolve(args.strategy) if args.strategy else None
    prediction = load_json(resolve(args.prediction)) if args.prediction else None

    scan = scan_all(odds, strategy_path=strategy, include_parlays=not args.no_parlay)
    funnel = rank_top6(scan, prediction=prediction, top_n=args.top)

    code = odds.get("match_date_code") or "unknown"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = resolve(args.out) if args.out else ROOT / "validation" / "drafts" / f"scan_{code}_{stamp}.json"

    payload = {
        "meta": {
            **scan["meta"],
            "odds_source": odds_path.name,
            "prediction_source": args.prediction,
        },
        "scan_summary": scan["scan_summary"],
        "funnel": funnel,
        "candidates": scan["candidates"],
    }
    enrich_scan_payload(payload, odds, prediction, strategy_path=strategy)
    write_json(out_path, payload)

    summary = scan["scan_summary"]
    print(f"[OK] scan_{code} → {out_path}")
    print(f"  候选 {summary['total_candidates']} · 过闸 {summary['eligible_count']} · 被砍 {summary['rejected_below']}")
    print(f"  六类覆盖: {', '.join(summary['by_category'].keys())}")
    if funnel.get("hero"):
        h = funnel["hero"]
        print(f"  主推 S1: {h['pick_label']} @ {h['odds']} · EV {h['ev']:.1%} · 综合分 {h['composite_score']}")
    else:
        print("  主推: 无（全部 EV < reject_below）→ 合法空单")
    top3 = funnel.get("top3") or []
    for row in top3:
        print(
            f"  Top3 #{row['pick_rank']} {row['pick_label_user']}: "
            f"{row['pick_label']} @ {row['odds']} · 命中奖 {row['win_gross']} 元（参考 {row['ref_stake']} 元）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
