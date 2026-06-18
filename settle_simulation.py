#!/usr/bin/env python3
"""
模拟赛后结算（T-3-3b）：读 simulation/sim_*.json + 实际比分 → 算方案命中 → 更新档案。

用法：
    python3 settle_simulation.py 周日010 2:2
    python3 settle_simulation.py --day 260614 --match 周日010 --score 2:2
    python3 settle_simulation.py --sim simulation/sim_260614_20260616.json --match 周日010 --score 2-2
    python3 settle_simulation.py --list-pending
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from predict_lib import evaluate_scheme, outcome_from_score  # noqa: E402

SIM_DIR = ROOT / "simulation"
TRACKING_PATH = SIM_DIR / "prediction_tracking.md"
TOP_N = 3


def normalize_match_no(s: str) -> str:
    return re.sub(r"\s+", "", s.strip())


def normalize_score(s: str) -> tuple[int, int]:
    s = s.strip().replace("：", ":")
    for sep in (":", "-"):
        if sep in s:
            parts = s.split(sep, 1)
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except ValueError:
                break
    raise ValueError(f"比分格式无效: {s}（期望如 2:2 或 2-2）")


def find_sim_files(day: str | None = None) -> list[Path]:
    pattern = f"sim_{day}_*.json" if day else "sim_*.json"
    return sorted(SIM_DIR.glob(pattern))


def pick_sim_file(day: str | None, sim_path: Path | None) -> Path | None:
    if sim_path:
        return sim_path if sim_path.exists() else None
    files = find_sim_files(day)
    if not files:
        return None
    # 优先未完全结算的文件
    for p in reversed(files):
        try:
            data = json.loads(p.read_text("utf-8"))
        except Exception:
            continue
        preds = data.get("predictions") or []
        if any(not pr.get("settlement") for pr in preds):
            return p
    return files[-1]


def find_prediction(data: dict, match_no: str) -> dict | None:
    key = normalize_match_no(match_no)
    for pr in data.get("predictions") or []:
        if normalize_match_no(pr.get("match_no", "")) == key:
            return pr
    return None


def scheme_hits(scheme: dict, home_goals: int, away_goals: int) -> dict[str, bool]:
    wdl = outcome_from_score(home_goals, away_goals)
    tg = str(home_goals + away_goals) if home_goals + away_goals < 7 else "7+"
    sc = f"{home_goals}:{away_goals}"
    return {
        "full_combo": evaluate_scheme(scheme, home_goals, away_goals),
        "wdl": scheme.get("wdl") == wdl,
        "total_goals": scheme.get("total_goals") == tg,
        "exact_score": scheme.get("score") in (sc, "—") and scheme.get("score") == sc,
    }


def settle_match(pred: dict, home_goals: int, away_goals: int, top_n: int = TOP_N) -> dict[str, Any]:
    schemes = pred.get("prediction", {}).get("schemes") or []
    evaluated: list[dict] = []
    for s in schemes:
        hits = scheme_hits(s, home_goals, away_goals)
        evaluated.append({**s, "hits": hits, "hit": hits["full_combo"]})
    top = evaluated[:top_n]
    return {
        "actual_score": f"{home_goals}:{away_goals}",
        "actual_wdl": outcome_from_score(home_goals, away_goals),
        "actual_total_goals": str(home_goals + away_goals) if home_goals + away_goals < 7 else "7+",
        "settled_at": datetime.now().isoformat(timespec="seconds"),
        "top_n": top_n,
        "top1_hit": bool(top and top[0]["hit"]),
        "topn_any_hit": any(s["hit"] for s in top),
        "schemes_evaluated": evaluated,
    }


def load_tracking() -> str:
    if TRACKING_PATH.exists():
        return TRACKING_PATH.read_text("utf-8")
    return """# 预测方案命中档案 · Forward 模拟

> 由 `settle_simulation.py` 维护。记录 **赛前锁定** 的组合方案 vs 实际赛果。
> 样本 < 20 场前 **只看趋势，不调权重**。

---

## 场次明细

| 比赛日 | 场次 | 对阵 | 实际比分 | 模拟文件 | Top1 | Top3任一 | P1 方案 | P1 命中 |
|---|---|---|---|---|---|---|---|---|

---

## 累计

| 指标 | 值 |
|---|---|
| 已结算场次 | 0 |
| Top1 组合命中率 | — |
| Top3 至少命中 1 套 | — |

---
"""


def append_tracking_row(
    content: str,
    row: dict[str, Any],
) -> str:
    line = (
        f"| {row['match_date_code']} | {row['match_no']} | {row['teams']} | **{row['actual_score']}** "
        f"| `{row['sim_file']}` | {'✓' if row['top1_hit'] else '✗'} | {'✓' if row['topn_any_hit'] else '✗'} "
        f"| {row['p1_pick']} | {'✓' if row['top1_hit'] else '✗'} |"
    )
    marker = "## 场次明细"
    if marker not in content:
        return content + "\n" + line + "\n"
    parts = content.split(marker, 1)
    rest = parts[1]
    # 插入到表头下一行（跳过空行和表头分隔行）
    lines = rest.splitlines()
    insert_at = 0
    for i, ln in enumerate(lines):
        if ln.startswith("|---"):
            insert_at = i + 1
            break
    lines.insert(insert_at, line)
    return parts[0] + marker + "\n".join(lines)


def update_cumulative(content: str, all_rows: list[dict]) -> str:
    n = len(all_rows)
    if n == 0:
        return content
    top1 = sum(1 for r in all_rows if r["top1_hit"])
    topn = sum(1 for r in all_rows if r["topn_any_hit"])
    top1_rate = f"{top1 / n:.1%}"
    topn_rate = f"{topn / n:.1%}"
    block = f"""## 累计

| 指标 | 值 |
|---|---|
| 已结算场次 | {n} |
| Top1 组合命中率 | **{top1_rate}**（{top1}/{n}） |
| Top3 至少命中 1 套 | **{topn_rate}**（{topn}/{n}） |

---"""
    if "## 累计" in content:
        pre, _ = content.split("## 累计", 1)
        return pre.rstrip() + "\n\n" + block + "\n"
    return content.rstrip() + "\n\n" + block + "\n"


def collect_settled_rows(sim_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(sim_dir.glob("sim_*.json")):
        try:
            data = json.loads(p.read_text("utf-8"))
        except Exception:
            continue
        code = data.get("meta", {}).get("match_date_code", "?")
        for pr in data.get("predictions") or []:
            st = pr.get("settlement")
            if not st:
                continue
            top = (st.get("schemes_evaluated") or [])[: st.get("top_n", TOP_N)]
            p1 = top[0] if top else {}
            rows.append({
                "match_date_code": code,
                "match_no": pr.get("match_no"),
                "teams": f"{pr.get('home_cn')} vs {pr.get('away_cn')}",
                "actual_score": st.get("actual_score"),
                "sim_file": p.name,
                "top1_hit": st.get("top1_hit"),
                "topn_any_hit": st.get("topn_any_hit"),
                "p1_pick": f"{p1.get('wdl','?')}/{p1.get('total_goals','?')}/{p1.get('score','?')}",
            })
    return rows


def rebuild_tracking_from_sims() -> None:
    rows = collect_settled_rows(SIM_DIR)
    content = load_tracking()
    # 保留头部到场次明细表头
    if "## 场次明细" in content:
        head = content.split("|---|", 1)[0] + "|---|---|---|---|---|---|---|---|\n"
    else:
        head = load_tracking()
    for r in rows:
        head = append_tracking_row(head, r)
    head = update_cumulative(head, rows)
    TRACKING_PATH.write_text(head, "utf-8")


def list_pending() -> int:
    found = False
    for p in reversed(find_sim_files()):
        data = json.loads(p.read_text("utf-8"))
        pending = [
            pr for pr in data.get("predictions") or []
            if not pr.get("settlement")
        ]
        if not pending:
            continue
        found = True
        print(f"\n{p.name}（{data.get('meta', {}).get('match_date_code', '?')}）")
        for pr in pending:
            print(f"  {pr.get('match_no')} {pr.get('home_cn')} vs {pr.get('away_cn')}")
    if not found:
        print("[*] 无待结算场次", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("match_pos", nargs="?", help="场次，如 周日010")
    p.add_argument("score_pos", nargs="?", help="比分，如 2:2")
    p.add_argument("--day", help="比赛日 code")
    p.add_argument("--match", help="场次编号")
    p.add_argument("--score", help="实际比分")
    p.add_argument("--sim", help="指定 sim JSON 路径")
    p.add_argument("--top", type=int, default=TOP_N, help="Top N 方案统计")
    p.add_argument("--list-pending", action="store_true", help="列出待结算场次")
    p.add_argument("--rebuild-tracking", action="store_true", help="从 simulation/*.json 重建 tracking")
    args = p.parse_args(argv)

    if args.rebuild_tracking:
        rebuild_tracking_from_sims()
        print(f"[OK] 重建 {TRACKING_PATH}", file=sys.stderr)
        return 0
    if args.list_pending:
        return list_pending()

    match_no = args.match or args.match_pos
    score_s = args.score or args.score_pos
    if not match_no or not score_s:
        p.print_help()
        return 1

    sim_path = Path(args.sim) if args.sim else None
    sim_file = pick_sim_file(args.day, sim_path)
    if not sim_file:
        print("[!] 找不到 simulation/sim_*.json，先跑 daily_simulate.py", file=sys.stderr)
        return 1

    hg, ag = normalize_score(score_s)
    data = json.loads(sim_file.read_text("utf-8"))
    pred = find_prediction(data, match_no)
    if not pred:
        print(f"[!] {sim_file.name} 中无场次 {match_no}", file=sys.stderr)
        return 1
    if pred.get("settlement"):
        print(f"[!] {match_no} 已结算（{pred['settlement'].get('actual_score')}），加 --rebuild-tracking 可重建档案", file=sys.stderr)
        return 1

    settlement = settle_match(pred, hg, ag, args.top)
    pred["settlement"] = settlement

    all_settled = all(pr.get("settlement") for pr in data.get("predictions") or [])
    data.setdefault("meta", {})["pending_settlement"] = not all_settled
    data["meta"]["last_settlement_at"] = settlement["settled_at"]

    sim_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    top = settlement["schemes_evaluated"][: args.top]
    print(f"[OK] 结算 {match_no} {pred.get('home_cn')} vs {pred.get('away_cn')} → {hg}:{ag}", file=sys.stderr)
    print(f"     文件 {sim_file.name}", file=sys.stderr)
    print(f"     Top1 {'命中 ✓' if settlement['top1_hit'] else '未中 ✗'} | Top{args.top} 任一 {'✓' if settlement['topn_any_hit'] else '✗'}", file=sys.stderr)
    for s in top:
        mark = "✓" if s["hit"] else "✗"
        print(f"     {s['id']} {s['wdl']}/{s['total_goals']}/{s['score']} {mark}", file=sys.stderr)

    row = {
        "match_date_code": data.get("meta", {}).get("match_date_code", "?"),
        "match_no": pred.get("match_no"),
        "teams": f"{pred.get('home_cn')} vs {pred.get('away_cn')}",
        "actual_score": settlement["actual_score"],
        "sim_file": sim_file.name,
        "top1_hit": settlement["top1_hit"],
        "topn_any_hit": settlement["topn_any_hit"],
        "p1_pick": f"{top[0]['wdl']}/{top[0]['total_goals']}/{top[0]['score']}" if top else "?",
    }
    content = load_tracking()
    content = append_tracking_row(content, row)
    content = update_cumulative(content, collect_settled_rows(SIM_DIR))
    SIM_DIR.mkdir(exist_ok=True)
    TRACKING_PATH.write_text(content, "utf-8")
    print(f"[OK] 更新 {TRACKING_PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
