#!/usr/bin/env python3
"""
基本面快照 + 预估赛果 enrich（基本面 Agent 标准收尾步骤）。

在 fetch_fundamentals 落盘 JSON/MD 后调用，用当期 odds + 五维引擎为每场写入：
  - JSON records[].forecast
  - MD 每场「8.7 预估赛果」节（胜平负 / 总进球 / 比分 / xG）

用法：
    python3 enrich_fundamentals_forecast.py --fundamentals fundamentals_*.json --odds odds_*.json
    python3 enrich_fundamentals_forecast.py --day 260617   # 自动找最新 fundamentals + odds
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fetch_fundamentals import render_markdown
from forecast_lib import forecast_summary, render_forecast_markdown_blocks
from artifact_lib import SNAPSHOT_FUNDAMENTALS_DIR, fundamentals_search_dirs, odds_search_dirs
from predict_engine import find_latest, run_predictions
from predict_lib import teams_match


def day_to_calendar(day: str) -> str:
    """260617 → 20260617（ESPN 日期格式）。"""
    if len(day) == 6 and day.isdigit():
        return f"20{day}"
    return day


def match_pred_to_record(rec: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any] | None:
    ev = rec.get("event") or {}
    home, away = ev.get("home"), ev.get("away")
    for r in results:
        if teams_match(r.get("home_en", ""), home or "") and teams_match(
            r.get("away_en", ""), away or ""
        ):
            return r
        if teams_match(r.get("home_cn", ""), home or "") and teams_match(
            r.get("away_cn", ""), away or ""
        ):
            return r
    return None


def forecast_to_record(fc: dict[str, Any], pred_row: dict[str, Any]) -> dict[str, Any]:
    return {
        **fc,
        "top_scorelines": list(fc["top_scorelines"]),
        "top_total_goals": list(fc["top_total_goals"]),
        "match_no": pred_row.get("match_no"),
        "home_cn": pred_row.get("home_cn"),
        "away_cn": pred_row.get("away_cn"),
        "home_en": pred_row.get("home_en"),
        "away_en": pred_row.get("away_en"),
    }


def enrich_fundamentals_data(
    fundamentals_data: dict[str, Any],
    odds_data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    results = run_predictions(odds_data, fundamentals_data)
    enriched = 0
    for rec in fundamentals_data.get("records") or []:
        pred_row = match_pred_to_record(rec, results)
        if not pred_row:
            rec.pop("forecast", None)
            continue
        fc = forecast_summary(pred_row["prediction"])
        rec["forecast"] = forecast_to_record(fc, pred_row)
        enriched += 1
    meta = fundamentals_data.setdefault("meta", {})
    meta["forecast_enriched"] = True
    meta["forecast_match_count"] = enriched
    meta["odds_source"] = odds_data.get("odds_source") or meta.get("odds_source")
    return fundamentals_data, results, enriched


def write_enriched_outputs(
    fundamentals_path: Path,
    fundamentals_data: dict[str, Any],
    md_path: Path | None = None,
    *,
    emit_md: bool = False,
) -> Path | None:
    fundamentals_path.write_text(
        json.dumps(fundamentals_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not emit_md:
        return None
    if md_path is None:
        md_path = fundamentals_path.with_suffix(".md")
    meta = fundamentals_data.get("meta") or {}
    md = render_markdown(
        fundamentals_data.get("records") or [],
        meta.get("league", "fifa.world"),
        meta.get("date", ""),
    )
    md_path.write_text(md, encoding="utf-8")
    return md_path


def apply_enrich(fundamentals_path: Path, odds_path: Path) -> tuple[int, Path]:
    fundamentals_data = json.loads(fundamentals_path.read_text(encoding="utf-8"))
    odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
    fundamentals_data, _, enriched = enrich_fundamentals_data(fundamentals_data, odds_data)
    meta = fundamentals_data.setdefault("meta", {})
    meta["odds_source"] = odds_path.name
    md_path = write_enriched_outputs(fundamentals_path, fundamentals_data)
    return enriched, md_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--fundamentals", help="fundamentals_*.json 路径")
    p.add_argument("--odds", help="odds_*.json 路径")
    p.add_argument("--day", help="比赛日 code，自动找最新 fundamentals + odds")
    p.add_argument("--dir", default=str(SNAPSHOT_FUNDAMENTALS_DIR))
    args = p.parse_args(argv)

    if args.fundamentals:
        fund_path = Path(args.fundamentals)
    elif args.day:
        cal = day_to_calendar(args.day)
        fund_path = (
            find_latest(f"fundamentals_*_{cal}*.json", fundamentals_search_dirs())
            or find_latest(f"fundamentals_*_{args.day}*.json", fundamentals_search_dirs())
        )
    else:
        fund_path = find_latest("fundamentals_*.json", fundamentals_search_dirs())

    if not fund_path or not fund_path.is_file():
        print("[!] 找不到 fundamentals JSON", file=sys.stderr)
        return 1

    if args.odds:
        odds_path = Path(args.odds)
    elif args.day:
        odds_path = (
            find_latest(f"odds_{args.day}_*.json", odds_search_dirs())
            or find_latest("odds_window_24h_*.json", odds_search_dirs())
        )
    else:
        odds_path = find_latest("odds_window_24h_*.json", odds_search_dirs()) or find_latest(
            "odds_*.json", odds_search_dirs()
        )

    if not odds_path or not odds_path.is_file():
        print("[!] 找不到 odds JSON，无法生成预估赛果", file=sys.stderr)
        return 1

    enriched, md_path = apply_enrich(fund_path, odds_path)
    print(f"[OK] enrich {fund_path.name} · {enriched} 场含预估赛果", file=sys.stderr)
    print(f"[OK] 更新 {md_path.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
