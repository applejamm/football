#!/usr/bin/env python3
"""
基本面 DB 回填工具

扫描 snapshots/fundamentals/fundamentals_<league>_<时间>.json 全部历史快照文件，
依次调用 fetch_fundamentals.upsert_snapshot()，重建：
  - snapshots/fundamentals/fundamentals_db.json
  - snapshots/fundamentals/teams/<name>.json

幂等：(snapshot_at, match_id) 已在 DB 中则跳过。
用 `--rebuild` 先删除 DB 再回填。

用法：
    python3 backfill_fundamentals.py            # 增量回填（保留已有 DB）
    python3 backfill_fundamentals.py --rebuild  # 删 DB 重建
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from artifact_lib import SNAPSHOT_FUNDAMENTALS_DIR, fundamentals_search_dirs
from fetch_fundamentals import upsert_snapshot

DEFAULT_DIR = SNAPSHOT_FUNDAMENTALS_DIR
SNAPSHOT_RE = re.compile(r"^fundamentals_(?P<league>[^_]+(?:\.[^_]+)*)_(?P<stamp>\d{8}-\d{6})\.json$")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="snapshots/fundamentals 目录")
    p.add_argument("--rebuild", action="store_true", help="删除已有 DB 后重建")
    args = p.parse_args(argv)

    base = Path(args.dir)
    db_path = base / "fundamentals_db.json"
    teams_dir = base / "teams"

    if args.rebuild:
        if db_path.exists():
            db_path.unlink()
            print(f"[*] 删除 {db_path.name}", file=sys.stderr)
        if teams_dir.exists():
            shutil.rmtree(teams_dir)
            print(f"[*] 删除 {teams_dir}", file=sys.stderr)
        legacy_teams = base / "fundamentals" / "teams"
        if legacy_teams.exists():
            shutil.rmtree(legacy_teams)
            print(f"[*] 删除遗留 {legacy_teams}", file=sys.stderr)

    snapshots: list[Path] = []
    for directory in fundamentals_search_dirs():
        if directory.is_dir():
            snapshots.extend(directory.glob("fundamentals_*.json"))
    snapshots = sorted(
        {s.resolve() for s in snapshots if s.name != "fundamentals_db.json"}
    )
    snapshots = [s for s in snapshots if s.name != "fundamentals_db.json"]

    if not snapshots:
        print("[!] 没找到任何 fundamentals_*.json 快照文件", file=sys.stderr)
        return 1

    print(f"[*] 找到 {len(snapshots)} 份快照文件", file=sys.stderr)

    upserted = 0
    for snap_path in snapshots:
        m = SNAPSHOT_RE.match(snap_path.name)
        if not m:
            print(f"[!] 跳过命名异常的文件：{snap_path.name}", file=sys.stderr)
            continue

        league = m.group("league")
        stamp = m.group("stamp")

        try:
            data = json.loads(snap_path.read_text("utf-8"))
        except Exception as ex:
            print(f"[!] 读取 {snap_path.name} 失败：{ex}", file=sys.stderr)
            continue

        meta = data.get("meta", {})
        records = data.get("records") or []
        if not records:
            print(f"[*] {snap_path.name} 无 records，跳过", file=sys.stderr)
            continue

        date = meta.get("date") or stamp[:8]
        snapshot_at = meta.get("snapshot_at") or stamp

        upsert_snapshot(
            output_dir=base,
            league=league,
            date_yyyymmdd=date,
            snapshot_at=snapshot_at,
            records=records,
            source_json=snap_path.name,
        )
        upserted += 1
        print(f"[OK] 回填 {snap_path.name}（{len(records)} 场）", file=sys.stderr)

    print(f"[*] 完成：{upserted}/{len(snapshots)} 份快照已 upsert", file=sys.stderr)
    print(f"[*] DB: {db_path}", file=sys.stderr)
    print(f"[*] teams 目录: {teams_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
