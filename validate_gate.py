#!/usr/bin/env python3
"""
数据验证门禁（T-3-10 / T-3-11）：发布正式报告前校验；PASS 后可 promote。

用法：
    python3 validate_gate.py \\
      --odds odds_260616_20260616-212759.json \\
      --prediction prediction_260616_20260616-214115.json \\
      --draft-md validation/drafts/decision_draft.md \\
      --promote

    python3 validate_gate.py ... --promote --promote-prediction --force

退出码：0 = PASS（promote 成功或未请求 promote）；1 = FAIL 或 promote 失败。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from validation_lib import (  # noqa: E402
    DEFAULT_STRATEGY,
    PromoteBlockedError,
    promote_artifacts,
    run_gate,
)


def resolve_input(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main() -> int:
    p = argparse.ArgumentParser(description="数据验证门禁（E 档）")
    p.add_argument("--odds", required=True, help="当期 odds_*.json")
    p.add_argument("--prediction", required=True, help="prediction_*.json")
    p.add_argument("--fundamentals", help="fundamentals_*.json（可选，写入 manifest）")
    p.add_argument("--strategy", help=f"策略 yaml（默认 {DEFAULT_STRATEGY.name}）")
    p.add_argument("--draft-json", help="decision 草案 JSON（建议放 validation/drafts/）")
    p.add_argument("--draft-md", help="decision 草案 Markdown（仅 --emit-md 时生成；兼容旧流程）")
    p.add_argument("--draft-html", help="decision 草案 HTML")
    p.add_argument("--run-id", help="指定 run_id（默认时间戳）")
    p.add_argument(
        "--promote",
        action="store_true",
        help="PASS 后将草案 promote 到项目根目录（须 --draft-md 和/或 --draft-html）",
    )
    p.add_argument(
        "--promote-prediction",
        action="store_true",
        help="PASS 后将 validation_run_id 写入 prediction JSON（原地更新）",
    )
    p.add_argument("--out-md", help="promote 后的 decision md 路径（默认根目录 + 草案文件名）")
    p.add_argument("--out-report", help="promote 后的合并报告 HTML（默认 report_<day>_<ts>.html）")
    p.add_argument("--out-html", help="兼容旧参数：等同 --out-report")
    p.add_argument("--force", action="store_true", help="允许覆盖已存在的正式产物")
    p.add_argument("--dry-run", action="store_true", help="只校验 / 模拟 promote，不写文件")
    args = p.parse_args()

    odds = resolve_input(args.odds)
    prediction = resolve_input(args.prediction)
    fundamentals = resolve_input(args.fundamentals) if args.fundamentals else None
    strategy = resolve_input(args.strategy) if args.strategy else None
    draft_json = resolve_input(args.draft_json) if args.draft_json else None
    draft_md = resolve_input(args.draft_md) if args.draft_md else None
    draft_html = resolve_input(args.draft_html) if args.draft_html else None
    out_md = resolve_input(args.out_md) if args.out_md else None
    out_report = resolve_input(args.out_report) if args.out_report else None
    out_html = resolve_input(args.out_html) if args.out_html else None

    report, run_dir = run_gate(
        odds=odds,
        prediction=prediction,
        fundamentals=fundamentals,
        strategy=strategy,
        draft_json=draft_json,
        draft_md=draft_md,
        draft_html=draft_html,
        run_id=args.run_id,
    )

    print(f"[{'PASS' if report.overall == 'PASS' else 'FAIL'}] run_id={report.run_id}")
    print(f"  checks : {run_dir / 'checks.json'}")
    for c in report.checks:
        if c.status == "FAIL":
            print(f"  ❌ {c.check_id}: {c.message}")

    if report.overall != "PASS":
        return 1

    if args.promote or args.promote_prediction:
        try:
            result = promote_artifacts(
                report,
                run_dir,
                draft_json=draft_json,
                draft_md=draft_md,
                draft_html=draft_html,
                prediction=prediction,
                out_md=out_md,
                out_report=out_report or out_html,
                out_html=out_html,
                force=args.force,
                dry_run=args.dry_run,
                promote_prediction_file=args.promote_prediction,
            )
        except PromoteBlockedError as e:
            print(f"[!] promote blocked: {e}", file=sys.stderr)
            return 1
        tag = "DRY-RUN" if result.dry_run else "PROMOTED"
        print(f"  [{tag}] promote.json → {run_dir / 'promote.json'}")
        for role, path in result.artifacts.items():
            print(f"    {role}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
