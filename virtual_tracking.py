#!/usr/bin/env python3
"""
虚拟跟踪 CLI（T-5-5）：赛后结算主推 / Top6 / 被砍样本虚拟收益。

用法：
    python3 scan_candidates.py --odds odds_260614_*.json --prediction prediction_260614_*.json \\
      --out validation/drafts/scan_260614.json

    python3 virtual_tracking.py \\
      --scan validation/drafts/scan_260614.json \\
      --scores "周日010:2:2,周日012:5:1" \\
      --update-tracking
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from virtual_tracking_lib import (  # noqa: E402
    RUNS_DIR,
    build_virtual_rows,
    load_json,
    merge_into_tracking,
    parse_scores_arg,
    render_virtual_section,
    summarize_rows,
    write_run_json,
)


def resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    ap = argparse.ArgumentParser(description="虚拟跟踪：主推/Top6/被砍赛后结算")
    ap.add_argument("--scan", required=True, help="scan_*.json（含 funnel + candidates）")
    ap.add_argument("--scores", required=True, help="场次:比分，逗号分隔，如 周日010:2:2,周日012:5:1")
    ap.add_argument("--virtual-stake", type=int, default=50, help="每条虚拟注统一金额（默认 50）")
    ap.add_argument("--cut-sample", type=int, default=10, help="被砍样本条数（默认 10）")
    ap.add_argument("--tracking", default="tracking.md", help="tracking.md 路径")
    ap.add_argument("--update-tracking", action="store_true", help="写入 tracking.md 虚拟跟踪段")
    ap.add_argument("--out", help="JSON 归档路径（默认 virtual/runs/<issue>_<ts>.json）")
    args = ap.parse_args()

    scan_path = resolve(args.scan)
    scan = load_json(scan_path)
    scores = parse_scores_arg(args.scores)
    rows = build_virtual_rows(
        scan,
        scores,
        virtual_stake=args.virtual_stake,
        cut_sample=args.cut_sample,
    )
    summary = summarize_rows(rows)
    section = render_virtual_section(rows, summary, scan_path.name)

    issue = scan["meta"].get("issue_no") or scan["meta"].get("match_date_code", "unknown")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = resolve(args.out) if args.out else RUNS_DIR / f"{issue}_{ts}.json"
    try:
        scan_rel = str(scan_path.relative_to(ROOT))
    except ValueError:
        scan_rel = scan_path.name
    payload = {
        "meta": {
            "settled_at": datetime.now().isoformat(timespec="seconds"),
            "scan_source": scan_rel,
            "scores": {k: f"{v[0]}:{v[1]}" for k, v in scores.items()},
            "virtual_stake": args.virtual_stake,
            "cut_sample": args.cut_sample,
        },
        "summary": summary,
        "rows": [r.to_dict() for r in rows],
    }
    write_run_json(out_path, payload)

    print(section)
    print(f"\n[OK] archived → {out_path}")

    hero = summary["by_class"].get("主推", {})
    cut = summary["by_class"].get("被砍样本", {})
    print(
        f"  主推虚拟收益 {hero.get('virtual_pnl', 0):+.2f} · "
        f"被砍样本虚拟收益 {cut.get('virtual_pnl', 0):+.2f} · "
        f"被砍命中 {len(summary.get('cut_hits', []))} 条"
    )

    if args.update_tracking:
        merge_into_tracking(resolve(args.tracking), section)
        print(f"  [OK] tracking.md 已更新虚拟跟踪段")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
