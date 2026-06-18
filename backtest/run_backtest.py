#!/usr/bin/env python3
"""
历史回测框架（T-3-1 · 开发用，非本届 WC 验收）。

用 fixtures/matches.jsonl 跑通管道。不要用已知赛果的 2026 世界杯场次喂这个脚本。

用法：
    python3 backtest/run_backtest.py
    python3 backtest/run_backtest.py --fixtures backtest/fixtures/matches.jsonl --top 3
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from predict_lib import evaluate_scheme, predict_match  # noqa: E402

DEFAULT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "matches.jsonl"


def load_fixtures(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def run_backtest(fixtures: list[dict], top_n: int = 3) -> dict:
    results: list[dict] = []
    combo_hits = 0
    topn_at_least_one = 0

    for fx in fixtures:
        home = fx["home"]
        away = fx["away"]
        ah, aa = fx["actual_home_goals"], fx["actual_away_goals"]
        pred = predict_match(
            home=home,
            away=away,
            features=fx.get("features", {}),
            cn_odds=fx.get("market_odds"),
            ref_date=fx.get("date"),
        )
        schemes = pred["schemes"][:top_n]
        hit_any = any(evaluate_scheme(s, ah, aa) for s in schemes)
        hit_best = evaluate_scheme(schemes[0], ah, aa) if schemes else False
        if hit_any:
            topn_at_least_one += 1
        if hit_best:
            combo_hits += 1
        results.append({
            "match_id": fx.get("match_id"),
            "tournament": fx.get("tournament"),
            "home": home,
            "away": away,
            "actual": f"{ah}:{aa}",
            "hit_top1": hit_best,
            "hit_topn": hit_any,
            "top_scheme": schemes[0] if schemes else None,
        })

    n = len(results)
    return {
        "meta": {
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "fixture_count": n,
            "top_n": top_n,
            "acceptance_target_combo": 0.60,
            "acceptance_target_topn": 0.50,
        },
        "metrics": {
            "top1_combo_accuracy": round(combo_hits / n, 4) if n else 0,
            "topn_at_least_one_rate": round(topn_at_least_one / n, 4) if n else 0,
            "top1_hits": combo_hits,
            "topn_hits": topn_at_least_one,
            "total": n,
        },
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    p.add_argument("--top", type=int, default=3, help="评估前 N 套方案")
    p.add_argument("--output-dir", default=None, help="回测报告目录（默认 reports/backtest/）")
    args = p.parse_args(argv)

    fx_path = Path(args.fixtures)
    if not fx_path.exists():
        print(f"[!] fixtures 不存在: {fx_path}", file=sys.stderr)
        return 1

    fixtures = load_fixtures(fx_path)
    report = run_backtest(fixtures, args.top)
    from artifact_lib import BACKTEST_REPORTS_DIR  # noqa: WPS433

    out_dir = Path(args.output_dir) if args.output_dir else BACKTEST_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"backtest_{stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    m = report["metrics"]
    print(f"[OK] 回测报告 {out_path.name}", file=sys.stderr)
    print(f"样本 {m['total']} 场", file=sys.stderr)
    print(f"Top1 组合准确率: {m['top1_combo_accuracy']:.1%}（验收 ≥60%）", file=sys.stderr)
    print(f"Top{args.top} 至少命中 1 套: {m['topn_at_least_one_rate']:.1%}（验收 ≥50%）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
