#!/usr/bin/env python3
"""
PM 编排工作流 CLI（T-0-3）：三阶段顺序执行 + 阶段门禁。

用法：
    python3 run_workflow.py --day 260617
    python3 run_workflow.py --day 260617 --phase 1
    python3 run_workflow.py --day 260617 --budget 200 --promote
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from workflow_lib import (  # noqa: E402
    latest_fundamentals,
    latest_odds,
    latest_prediction,
    load_state,
    phase1_collect,
    phase2_analyze,
    phase3_decide,
    run_full_workflow,
    write_state,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="PM 编排：数据 → 分析 → 投注")
    ap.add_argument("--day", required=True, help="比赛日 code，如 260617")
    ap.add_argument("--phase", type=int, choices=[1, 2, 3], help="只跑指定阶段")
    ap.add_argument("--budget", type=int, default=200, help="投注预算（元）")
    ap.add_argument("--promote", action="store_true", help="阶段3 PASS 后 promote 正式报告")
    ap.add_argument(
        "--allow-full-budget",
        action="store_true",
        help="IMP-006：catastrophic 触发时仍使用满预算（须 yaml allow_full_budget_override=true）",
    )
    args = ap.parse_args()
    day = args.day

    try:
        if args.phase is None:
            state = run_full_workflow(
                day,
                budget=args.budget,
                promote=args.promote,
                allow_full_budget=args.allow_full_budget,
            )
            print(f"[OK] 工作流完成 day={day}")
            for k, v in state["paths"].items():
                if v:
                    print(f"  {k}: {v}")
            return 0

        if args.phase == 1:
            paths = phase1_collect(day)
            write_state(
                day,
                {
                    "day": day,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": 1,
                    "status": "phase1_complete",
                    "paths": {k: str(v) for k, v in paths.items() if v},
                },
            )
            print(f"[OK] 阶段1完成 odds={paths['odds']}")
            return 0

        if args.phase == 2:
            odds = latest_odds(day)
            if not odds:
                print("[!] 请先跑阶段1", file=sys.stderr)
                return 1
            pred = phase2_analyze(day, odds)
            write_state(
                day,
                {
                    "day": day,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": 2,
                    "status": "phase2_complete",
                    "paths": {"odds": str(odds), "prediction": str(pred)},
                },
            )
            print(f"[OK] 阶段2完成 prediction={pred}")
            return 0

        odds = latest_odds(day)
        pred = latest_prediction(day)
        if not odds or not pred:
            print("[!] 请先完成阶段1和阶段2", file=sys.stderr)
            return 1
        paths3 = phase3_decide(
            day,
            odds,
            pred,
            args.budget,
            promote=args.promote,
            allow_full_budget=args.allow_full_budget,
        )
        prev = load_state(day) or {}
        prev.update(
            {
                "day": day,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "phase": 3,
                "status": "phase3_complete",
                "paths": {
                    **(prev.get("paths") or {}),
                    "odds": str(odds),
                    "fundamentals": str(latest_fundamentals(day) or ""),
                    "prediction": str(pred),
                    "scan": str(paths3["scan"]),
                    "draft_json": str(paths3["draft_json"]),
                    "draft_html": str(paths3.get("draft_html") or ""),
                    "report_html": str(paths3.get("report_html") or ""),
                },
                "promoted": args.promote,
            }
        )
        write_state(day, prev)
        print(f"[OK] 阶段3完成 draft={paths3['draft_json']}")
        return 0
    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError) as exc:
        print(f"[!] 工作流失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
