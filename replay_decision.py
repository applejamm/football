#!/usr/bin/env python3
"""
赛后复盘自动化（T-4-9）：比分 → 注单结算 → tracking + decision MD/HTML + 虚拟跟踪。

用法：
    python3 replay_decision.py --code 260616 --scores "周二017:2:0"
    python3 replay_decision.py --decision decision_260616_match017_FUNNEL_REGEN.md \\
      --scores "周二017:2:0" --scan validation/drafts/scan_260616_demo.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from replay_lib import (  # noqa: E402
    find_latest_decision,
    find_latest_scan,
    parse_bets_from_md,
    parse_decision_meta,
    parse_scores_arg,
    patch_decision_html,
    run_virtual_if_scan,
    settle_bets,
    update_decision_md_replay,
    update_tracking_rows,
)
from virtual_tracking_lib import load_json  # noqa: E402

TRACKING = ROOT / "tracking.md"
REPLAY_DIR = ROOT / "replay" / "runs"


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    ap = argparse.ArgumentParser(description="赛后复盘自动化 T-4-9")
    ap.add_argument("--code", help="比赛日 code，如 260616")
    ap.add_argument("--decision", help="决策 MD 路径（默认取最新 decision_<code>_*.md）")
    ap.add_argument("--scores", required=True, help="场次:比分，逗号分隔")
    ap.add_argument("--scan", help="scan JSON（默认 validation/drafts/scan_<code>*.json 最新）")
    ap.add_argument("--virtual-stake", type=int, default=50)
    ap.add_argument("--no-virtual", action="store_true", help="跳过虚拟跟踪")
    ap.add_argument("--tracking", default="tracking.md")
    ap.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = ap.parse_args()

    scores = parse_scores_arg(args.scores)
    decision_path = resolve(args.decision) if args.decision else None
    if not decision_path:
        if not args.code:
            print("[!] 需要 --code 或 --decision", file=sys.stderr)
            return 1
        decision_path = find_latest_decision(ROOT, args.code)
    if not decision_path or not decision_path.exists():
        print(f"[!] 找不到决策文件", file=sys.stderr)
        return 1

    md_text = decision_path.read_text(encoding="utf-8")
    meta = parse_decision_meta(md_text)
    code = args.code or meta["match_date_code"]
    bets = parse_bets_from_md(md_text)
    if not bets:
        print("[!] 决策 MD 中未解析到注单（检查行动卡表格）", file=sys.stderr)
        return 1

    settled = settle_bets(bets, scores)
    if not settled:
        print("[!] 无注单被结算（比分场次与注单不匹配？）", file=sys.stderr)
        return 1

    print(f"[i] 决策 {decision_path.name} · 期号 {meta['issue_no']}")
    total_pnl = 0.0
    for s in settled:
        mark = "✓" if s.hit else "✗"
        print(f"  {s.bet.bet_id} {s.bet.match_no} {s.bet.pick} → {s.score} {mark} {s.pnl:+.2f}")
        total_pnl += s.pnl
    print(f"  合计净收益 {total_pnl:+.2f} 元")

    html_path = decision_path.with_suffix(".html")
    tracking_path = resolve(args.tracking)

    new_md = update_decision_md_replay(md_text, settled)
    tracking_text = tracking_path.read_text(encoding="utf-8") if tracking_path.exists() else ""
    new_tracking = update_tracking_rows(tracking_text, meta["issue_no"], settled)

    new_html = ""
    if html_path.exists():
        new_html = patch_decision_html(html_path.read_text(encoding="utf-8"), settled, hero_id="S1")

    scan_path = resolve(args.scan) if args.scan else find_latest_scan(ROOT, code)

    if args.dry_run:
        print("[dry-run] 未写入文件")
        return 0

    decision_path.write_text(new_md, encoding="utf-8")
    print(f"[OK] 更新 {decision_path.name}")

    if new_html:
        html_path.write_text(new_html, encoding="utf-8")
        print(f"[OK] 更新 {html_path.name}")

    if new_tracking != tracking_text:
        tracking_path.write_text(new_tracking, encoding="utf-8")
        print(f"[OK] 更新 {tracking_path.name}")
    else:
        print(f"[i] tracking 无匹配行（期号 {meta['issue_no']} / 注 ID）— 可手补")

    if not args.no_virtual:
        section = run_virtual_if_scan(
            scan_path, scores, args.virtual_stake, tracking_path, load_json
        )
        if section:
            print(f"[OK] 虚拟跟踪已更新（scan={scan_path.name}）")
        elif scan_path:
            print(f"[i] 虚拟跟踪跳过（scan 不存在）")
        else:
            print("[i] 无 scan 文件，跳过虚拟跟踪")

    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    import datetime

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = REPLAY_DIR / f"{meta['issue_no'] or code}_{stamp}.json"
    archive.write_text(
        json.dumps(
            {
                "decision": decision_path.name,
                "scores": {k: f"{v[0]}:{v[1]}" for k, v in scores.items()},
                "settled": [
                    {
                        "bet_id": s.bet.bet_id,
                        "match_no": s.bet.match_no,
                        "score": s.score,
                        "hit": s.hit,
                        "pnl": s.pnl,
                    }
                    for s in settled
                ],
                "total_pnl": round(total_pnl, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[OK] 归档 {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
