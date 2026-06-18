#!/usr/bin/env python3
"""
基本面 DB 查询工具

读 snapshots/fundamentals/fundamentals_db.json + snapshots/fundamentals/teams/<name>.json，
按球队 / 按比赛 / 按列表查询抓过的基本面信息。

只读，不写盘；所有输出用于"进一步分析"。

用法：
    python3 query_fundamentals.py --list                        # 列出所有球队 + 比赛
    python3 query_fundamentals.py --team Japan                  # 该队所有抓取记录
    python3 query_fundamentals.py --team Japan --last 3         # 最近 3 次
    python3 query_fundamentals.py --match 760425                # 该比赛所有快照
    python3 query_fundamentals.py --team Japan --json           # JSON 输出（喂给下游脚本）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from artifact_lib import SNAPSHOT_FUNDAMENTALS_DIR
from fetch_fundamentals import safe_team_filename

DEFAULT_DIR = SNAPSHOT_FUNDAMENTALS_DIR


def _teams_dir(base: Path) -> Path:
    primary = base / "teams"
    legacy = base / "fundamentals" / "teams"
    if primary.is_dir() or not legacy.is_dir():
        return primary
    return legacy


def load_db(base: Path) -> dict:
    db_path = base / "fundamentals_db.json"
    if not db_path.exists():
        print(f"[!] 找不到 {db_path}。请先跑 fetch_fundamentals.py 或 backfill_fundamentals.py", file=sys.stderr)
        sys.exit(1)
    return json.loads(db_path.read_text("utf-8"))


def load_team(base: Path, team_name: str) -> dict | None:
    f = _teams_dir(base) / f"{safe_team_filename(team_name)}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text("utf-8"))


def cmd_list(db: dict) -> None:
    print(f"=== 概览（schema {db['meta']['schema_version']}, last_upsert={db['meta']['last_upsert']}） ===")
    print(f"  快照数: {db['meta']['snapshot_count']}")
    print(f"  比赛数: {db['meta']['match_count']}")
    print(f"  球队数: {db['meta']['team_count']}")
    print()
    print("=== 球队（按 last_seen 倒序） ===")
    teams = sorted(db["teams"].items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)
    for name, info in teams:
        print(f"  {name:25s}  抓取 {info['snapshot_count']:>2} 次 | 涉及 {len(info['match_ids'])} 场 | 最近 {info['last_seen']}")
    print()
    print("=== 比赛 ===")
    for mid, m in db["matches"].items():
        print(f"  {mid}  {m['date']}  {m['home']} vs {m['away']:25s}  快照 {len(m['snapshot_ids'])} 次")


def fmt_l5(events: list[dict]) -> str:
    if not events:
        return "（无）"
    return " ".join(f"{(e.get('result') or '?')[:1]}({e.get('score') or '?'})" for e in events)


def fmt_h2h(h2h: list[dict]) -> str:
    if not h2h:
        return "（无）"
    parts = []
    for h in h2h:
        events = h.get("events") or []
        for e in events:
            parts.append(f"{e.get('date','?')[:10]} {e.get('result','?')}({e.get('score','?')})")
    return ", ".join(parts) if parts else "（仅标题，无对局明细）"


def cmd_team(team_name: str, last: int | None, as_json: bool, base: Path, db: dict) -> int:
    real_name = next((k for k in db["teams"] if k.lower() == team_name.lower()), None)
    if not real_name:
        candidates = [k for k in db["teams"] if team_name.lower() in k.lower()]
        if not candidates:
            print(f"[!] DB 里没有 {team_name}。--list 看现有球队", file=sys.stderr)
            return 1
        real_name = candidates[0]
        print(f"[*] 模糊匹配命中：{real_name}", file=sys.stderr)

    team_data = load_team(base, real_name)
    if not team_data:
        print(f"[!] DB 索引说有 {real_name}，但球队文件丢了。建议跑 backfill_fundamentals.py --rebuild", file=sys.stderr)
        return 1

    history = team_data.get("history", [])
    if last:
        history = history[-last:]

    if as_json:
        print(json.dumps({**team_data, "history": history}, ensure_ascii=False, indent=2))
        return 0

    print(f"=== {real_name} · {len(history)} 条记录（按抓取时间升序） ===")
    print()
    for i, h in enumerate(history, 1):
        print(f"[{i}] {h['snapshot_at']}  vs {h.get('opponent','?')} ({h.get('match_name','?')})")
        print(f"    role={h.get('as_role','?')}  match_id={h.get('match_id','?')}  kickoff={h.get('kickoff_utc','?')}")
        print(f"    近 5 场: {fmt_l5(h.get('last_five_games') or [])}")
        print(f"    H2H:    {fmt_h2h(h.get('h2h') or [])}")
        co = h.get("consensus_odds")
        if co:
            print(f"    共识盘: {co.get('provider','?')} {co.get('details','?')} (O/U {co.get('over_under','?')})")
        miss = h.get("missing_dimensions") or []
        if miss:
            print(f"    缺失:   {', '.join(miss)}")
        print()
    return 0


def cmd_match(match_id: str, as_json: bool, db: dict) -> int:
    if match_id not in db["matches"]:
        print(f"[!] DB 里没有 match_id={match_id}", file=sys.stderr)
        return 1
    m = db["matches"][match_id]
    snap_ids = m.get("snapshot_ids", [])
    snaps = [db["snapshots"][sid] for sid in snap_ids if sid in db["snapshots"]]

    if as_json:
        print(json.dumps({"match": m, "snapshots": snaps}, ensure_ascii=False, indent=2))
        return 0

    print(f"=== {m['name']} (match_id={match_id}) ===")
    print(f"  日期: {m['date']}  开赛: {m['kickoff_utc']}  球场: {m['venue']}")
    print(f"  联赛: {m['league']}  主队: {m['home']}  客队: {m['away']}")
    print(f"  抓取次数: {len(snaps)}")
    print()
    for s in snaps:
        print(f"  - {s['snapshot_at']}  来源: {s.get('source_json','?')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="football/ 所在目录")
    p.add_argument("--list", action="store_true", help="列出所有球队 + 比赛")
    p.add_argument("--team", help="按球队名查（英文，模糊匹配）")
    p.add_argument("--last", type=int, default=None, help="只取该队最近 N 次抓取")
    p.add_argument("--match", help="按比赛 ID（ESPN event_id）查")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args(argv)

    base = Path(args.dir)
    db = load_db(base)

    if args.list:
        cmd_list(db)
        return 0
    if args.team:
        return cmd_team(args.team, args.last, args.json, base, db)
    if args.match:
        return cmd_match(args.match, args.json, db)

    cmd_list(db)
    print()
    print("（提示：用 --team <name> 或 --match <event_id> 看具体记录）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
