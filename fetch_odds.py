#!/usr/bin/env python3
"""
中国体育彩票 - 竞彩足球 赔率抓取脚本

数据来源：体彩官网移动端计算器（胜平负/让球/比分/总进球/半全场同源 API）
源页面：
  - 比分：https://m.sporttery.cn/mjc/jsq/zqbf/
  - 总进球数：https://m.sporttery.cn/mjc/jsq/zqzjq/
  - 混合过关：https://m.sporttery.cn/mjc/jsq/zqhhgg/ （与上两页共用同一 API）
后端 API：https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry

输出（每次抓取都是独立文件，文件名含抓取时间）：
  snapshots/odds/odds_<matchDayCode>_<YYYYMMDD>-<HHMMSS>.json
  snapshots/diffs/diff_<matchDayCode>_<YYYYMMDD>-<HHMMSS>.json
  snapshots/raw/api_match_calc_<YYYYMMDD>_<HHMMSS>.json  （--save-raw）

用法：
    python3 fetch_odds.py                  # 抓取所有可见天
    python3 fetch_odds.py --day 260614     # 只抓指定一天
    python3 fetch_odds.py --save-raw       # 同时保留 API 原始响应
    python3 fetch_odds.py --no-diff        # 不计算漂移
    python3 fetch_odds.py --diff-min-pct 2 # 只显示变化绝对值 ≥ 2% 的项
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CN_TZ = timezone(timedelta(hours=8))

API_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getMatchCalculatorV1.qry?channel=c"
)
SOURCE_PAGES = {
    "比分": "https://m.sporttery.cn/mjc/jsq/zqbf/",
    "总进球数": "https://m.sporttery.cn/mjc/jsq/zqzjq/",
    "混合过关": "https://m.sporttery.cn/mjc/jsq/zqhhgg/",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 "
        "Safari/604.1"
    ),
    "Referer": "https://m.sporttery.cn/",
    "Origin": "https://m.sporttery.cn",
}

from artifact_lib import (  # noqa: E402
    SNAPSHOT_DIFFS_DIR,
    SNAPSHOT_ODDS_DIR,
    SNAPSHOT_RAW_DIR,
    ensure_snapshot_dirs,
    rel_snapshot,
)

DEFAULT_OUTPUT_DIR = SNAPSHOT_ODDS_DIR

CRS_RE = re.compile(r"^s(\d{2})s(\d{2})$")
CRS_OTHER = {
    "s1sh": ("胜", "胜其它"),
    "s1sd": ("平", "平其它"),
    "s1sa": ("负", "负其它"),
}

HAFU_LABELS = {
    "hh": "胜胜",
    "hd": "胜平",
    "ha": "胜负",
    "dh": "平胜",
    "dd": "平平",
    "da": "平负",
    "ah": "负胜",
    "ad": "负平",
    "aa": "负负",
}



def fetch_api(url: str = API_URL, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_update_time(market: dict[str, Any]) -> str | None:
    date = market.get("updateDate") or ""
    time = market.get("updateTime") or ""
    combined = f"{date} {time}".strip()
    return combined or None


def parse_had(had: dict[str, Any]) -> dict[str, Any]:
    """胜平负（不让球）"""
    if not had or to_float(had.get("h")) is None:
        return {
            "type": "胜平负",
            "handicap": None,
            "handicap_label": "[未]",
            "status": "未开盘",
            "update_time": None,
            "odds": {"胜": None, "平": None, "负": None},
        }
    return {
        "type": "胜平负",
        "handicap": 0,
        "handicap_label": "[0]",
        "status": "已开盘",
        "update_time": fmt_update_time(had),
        "odds": {
            "胜": to_float(had.get("h")),
            "平": to_float(had.get("d")),
            "负": to_float(had.get("a")),
        },
    }


def parse_hhad(hhad: dict[str, Any]) -> dict[str, Any] | None:
    """让球胜平负"""
    if not hhad or to_float(hhad.get("h")) is None:
        return None

    goal_line_raw = str(hhad.get("goalLine", "")).strip()
    try:
        gl_int: int | None = int(goal_line_raw.replace("+", ""))
    except (TypeError, ValueError):
        gl_int = None

    if gl_int is None:
        label = f"[{goal_line_raw}]" if goal_line_raw else "[?]"
    elif gl_int > 0:
        label = f"[+{gl_int}]"
    else:
        label = f"[{gl_int}]"

    return {
        "type": "让球胜平负",
        "handicap": gl_int,
        "handicap_label": label,
        "status": "已开盘",
        "update_time": fmt_update_time(hhad),
        "odds": {
            "胜": to_float(hhad.get("h")),
            "平": to_float(hhad.get("d")),
            "负": to_float(hhad.get("a")),
        },
    }


def parse_crs(crs: dict[str, Any]) -> dict[str, Any] | None:
    """比分"""
    if not crs:
        return None

    buckets: dict[str, dict[str, float]] = {"胜": {}, "平": {}, "负": {}}
    has_data = False

    for key, val in crs.items():
        if key.endswith("f") or key in {"goalLine", "goalLineValue", "updateDate", "updateTime"}:
            continue
        odds = to_float(val)
        if odds is None:
            continue

        if key in CRS_OTHER:
            bucket, label = CRS_OTHER[key]
            buckets[bucket][label] = odds
            has_data = True
            continue

        m = CRS_RE.match(key)
        if not m:
            continue
        home, away = int(m.group(1)), int(m.group(2))
        score = f"{home}:{away}"
        if home > away:
            buckets["胜"][score] = odds
        elif home == away:
            buckets["平"][score] = odds
        else:
            buckets["负"][score] = odds
        has_data = True

    if not has_data:
        return None

    return {
        "type": "比分",
        "status": "已开盘",
        "update_time": fmt_update_time(crs),
        "odds": buckets,
    }


def parse_hafu(hafu: dict[str, Any]) -> dict[str, Any] | None:
    """半全场胜平负"""
    if not hafu:
        return None
    odds: dict[str, float] = {}
    for key, label in HAFU_LABELS.items():
        val = to_float(hafu.get(key))
        if val is not None and val > 1:
            odds[label] = val
    if not odds:
        return None
    return {
        "type": "半全场",
        "status": "已开盘",
        "update_time": fmt_update_time(hafu),
        "odds": odds,
    }


def empty_crs_market() -> dict[str, Any]:
    return {
        "type": "比分",
        "status": "未开盘",
        "update_time": None,
        "odds": {"胜": {}, "平": {}, "负": {}},
    }


def empty_ttg_market() -> dict[str, Any]:
    odds: dict[str, float | None] = {str(i): None for i in range(7)}
    odds["7+"] = None
    return {
        "type": "总进球数",
        "description": "双方进球数之和",
        "status": "未开盘",
        "update_time": None,
        "odds": odds,
    }


def pool_codes(pool_list: list[dict[str, Any]] | None) -> set[str]:
    return {str(p.get("poolCode", "")).upper() for p in (pool_list or []) if p.get("poolCode")}


def summarize_market_coverage(matches: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = {}
    for match in matches:
        for market in match.get("markets", []) or []:
            mtype = market.get("type", "?")
            status = market.get("status", "?")
            coverage.setdefault(mtype, {})
            coverage[mtype][status] = coverage[mtype].get(status, 0) + 1
    return coverage


def parse_ttg(ttg: dict[str, Any]) -> dict[str, Any] | None:
    """总进球数（双方进球之和）"""
    if not ttg:
        return None
    odds: dict[str, float] = {}
    for i in range(8):
        v = to_float(ttg.get(f"s{i}"))
        if v is None:
            continue
        odds["7+" if i == 7 else str(i)] = v
    if not odds:
        return None
    return {
        "type": "总进球数",
        "description": "双方进球数之和",
        "status": "已开盘",
        "update_time": fmt_update_time(ttg),
        "odds": odds,
    }


def convert_match(sm: dict[str, Any]) -> dict[str, Any]:
    markets: list[dict[str, Any]] = []
    pools = pool_codes(sm.get("poolList"))
    markets.append(parse_had(sm.get("had") or {}))
    hhad = parse_hhad(sm.get("hhad") or {})
    if hhad:
        markets.append(hhad)
    crs = parse_crs(sm.get("crs") or {})
    if crs:
        markets.append(crs)
    elif "CRS" in pools:
        markets.append(empty_crs_market())
    ttg = parse_ttg(sm.get("ttg") or {})
    if ttg:
        markets.append(ttg)
    elif "TTG" in pools:
        markets.append(empty_ttg_market())
    hafu = parse_hafu(sm.get("hafu") or {})
    if hafu:
        markets.append(hafu)

    kickoff_time = (sm.get("matchTime") or "")[:5]
    return {
        "match_no": sm.get("matchNumStr", ""),
        "match_id": sm.get("matchId"),
        "tournament": sm.get("leagueAbbName") or sm.get("leagueAllName") or "",
        "kickoff_local": f"{sm.get('matchDate','')} {kickoff_time}".strip(),
        "home_team": sm.get("homeTeamAbbName", ""),
        "away_team": sm.get("awayTeamAbbName", ""),
        "venue": sm.get("remark", ""),
        "status": sm.get("matchStatus", ""),
        "issue_no": sm.get("taxDateNo", ""),
        "markets": markets,
    }


def build_day_file(day: dict[str, Any], captured_at: str) -> dict[str, Any]:
    sub = day.get("subMatchList") or []
    issue_no = sub[0].get("taxDateNo", "") if sub else ""
    matches = [convert_match(sm) for sm in sub]
    return {
        "source": "中国体育彩票 - 竞彩足球 (API: getMatchCalculatorV1.qry)",
        "play_type": "混合过关",
        "issue_no": issue_no,
        "list_date": day.get("businessDate", ""),
        "list_weekday": day.get("weekday", ""),
        "match_date_code": day.get("matchNumDate", ""),
        "total_matches_on_page": day.get("matchCount", len(sub)),
        "captured_at": captured_at,
        "api_endpoint": API_URL,
        "source_pages": SOURCE_PAGES,
        "market_coverage": summarize_market_coverage(matches),
        "matches": matches,
        "notes": [
            "本文件由 fetch_odds.py 自动抓取生成，源自体彩官方 API。",
            "比分/总进球数与移动端 zqbf、zqzjq 计算器页同源，一次抓取即含六类玩法。",
            "[未] 表示赔率尚未开出，对应市场暂不可投注。",
            "让球数为正值表示主队被让球，负值表示主队让球，0 表示不让球。",
            "比分赔率按 胜/平/负 三类分组，'胜其它/平其它/负其它' 表示未列出的更冷比分集合。",
            "总进球数 = 双方进球数之和，档位 0~6 + '7+'（7 球及以上）。",
            "半全场 = 半场结果 + 全场结果（如 胜胜 = 半场主胜且全场主胜）。",
        ],
    }


def parse_kickoff_local(kickoff_local: str) -> datetime | None:
    """解析 kickoff_local（Asia/Shanghai）。"""
    text = (kickoff_local or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CN_TZ)
        except ValueError:
            continue
    return None


def is_match_bettable(
    match: dict[str, Any],
    *,
    now: datetime | None = None,
    within_hours: int | None = None,
) -> bool:
    """可投注：Selling 且未开赛；可选限制在未来 within_hours 小时内。"""
    if match.get("status") != "Selling":
        return False
    kickoff = parse_kickoff_local(match.get("kickoff_local", ""))
    if kickoff is None:
        return False
    ref = now or datetime.now(CN_TZ)
    if kickoff <= ref:
        return False
    if within_hours is not None and kickoff > ref + timedelta(hours=within_hours):
        return False
    return True


def filter_bettable_matches(
    matches: list[dict[str, Any]],
    *,
    within_hours: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    return [
        m
        for m in matches
        if is_match_bettable(m, now=now, within_hours=within_hours)
    ]


def build_window_file(
    day_files: list[dict[str, Any]],
    captured_at: str,
    within_hours: int,
) -> dict[str, Any]:
    """合并多比赛日、24h 窗口内可投注场次为单一快照。"""
    merged: list[dict[str, Any]] = []
    codes: list[str] = []
    for day_data in day_files:
        code = day_data.get("match_date_code", "")
        if code and code not in codes:
            codes.append(code)
        merged.extend(day_data.get("matches") or [])
    merged.sort(key=lambda m: m.get("kickoff_local", ""))
    primary = codes[0] if len(codes) == 1 else "window"
    return {
        "source": "中国体育彩票 - 竞彩足球 (API: getMatchCalculatorV1.qry)",
        "play_type": "混合过关",
        "issue_no": day_files[0].get("issue_no", "") if day_files else "",
        "list_date": day_files[0].get("list_date", "") if day_files else "",
        "list_weekday": day_files[0].get("list_weekday", "") if day_files else "",
        "match_date_code": primary,
        "match_days_included": codes,
        "window_hours": within_hours,
        "total_matches_on_page": len(merged),
        "captured_at": captured_at,
        "api_endpoint": API_URL,
        "source_pages": SOURCE_PAGES,
        "market_coverage": summarize_market_coverage(merged),
        "matches": merged,
        "notes": [
            f"本文件合并 {within_hours}h 窗口内全部可投注场次（status=Selling 且未开赛）。",
            "候选扫描须基于此文件，确保下单选项均来自体彩下注页当前可买池。",
            *(
                day_files[0].get("notes", [])
                if day_files
                else ["本文件由 fetch_odds.py 自动抓取生成，源自体彩官方 API。"]
            ),
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")
_FNAME_RE = re.compile(r"^odds_(\d{6})_(\d{8})-(\d{6})\.json$")


def _iso_to_compact(iso: str) -> str:
    """2026-06-14T19:44:48+08:00 -> 20260614-194448"""
    m = _ISO_RE.match(iso)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return f"{y}{mo}{d}-{h}{mi}{s}"
    return iso.replace(":", "").replace("-", "").replace("T", "-")[:15]


def _find_latest_existing(output_dir: Path, code: str) -> Path | None:
    """找到同一 matchDayCode 下时间戳最大的 odds_*.json，作为 diff 基准。"""
    candidates = []
    for f in output_dir.glob(f"odds_{code}_*.json"):
        m = _FNAME_RE.match(f.name)
        if m:
            candidates.append((m.group(2) + m.group(3), f))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


# --------------------------------------------------------------------------
# 赔率漂移（diff）
# --------------------------------------------------------------------------

def _flatten_market(market: dict[str, Any]) -> dict[str, float | None]:
    """把一个 market 拍平成 {path: odds} 字典，便于跨市场统一对比。"""
    flat: dict[str, float | None] = {}
    mtype = market.get("type", "?")
    odds = market.get("odds", {})

    if mtype in {"胜平负", "让球胜平负"}:
        for k in ("胜", "平", "负"):
            flat[f"{mtype}・{k}"] = odds.get(k) if isinstance(odds, dict) else None
    elif mtype == "比分":
        if isinstance(odds, dict):
            for cat in ("胜", "平", "负"):
                inner = odds.get(cat, {}) or {}
                for score, v in inner.items():
                    flat[f"比分・{cat}・{score}"] = v
    elif mtype == "总进球数":
        if isinstance(odds, dict):
            for k, v in odds.items():
                flat[f"总进球数・{k}球"] = v
    elif mtype == "半全场":
        if isinstance(odds, dict):
            for k, v in odds.items():
                flat[f"半全场・{k}"] = v
    return flat


def _flatten_match(match: dict[str, Any]) -> dict[str, float | None]:
    flat: dict[str, float | None] = {}
    for mk in match.get("markets", []) or []:
        flat.update(_flatten_market(mk))
    return flat


def compute_diff(
    old_data: dict[str, Any] | None,
    new_data: dict[str, Any],
    min_pct: float = 0.0,
) -> dict[str, Any]:
    """对比两份 odds_<code>.json，返回结构化 diff。"""
    summary = {
        "code": new_data.get("match_date_code"),
        "issue_no": new_data.get("issue_no"),
        "previous_captured_at": (old_data or {}).get("captured_at"),
        "current_captured_at": new_data.get("captured_at"),
        "totals": {"changed": 0, "hotter": 0, "colder": 0, "added": 0, "removed": 0},
        "by_match": [],
    }

    old_matches = {m["match_no"]: m for m in (old_data or {}).get("matches", [])}
    for new_match in new_data.get("matches", []):
        mno = new_match.get("match_no")
        new_flat = _flatten_match(new_match)
        old_match = old_matches.get(mno)
        old_flat = _flatten_match(old_match) if old_match else {}

        changes: list[dict[str, Any]] = []
        keys = sorted(set(new_flat) | set(old_flat))
        for key in keys:
            old_v = old_flat.get(key)
            new_v = new_flat.get(key)
            if old_v is None and new_v is None:
                continue
            if old_v is None:
                changes.append({
                    "path": key, "old": None, "new": new_v,
                    "delta": None, "delta_pct": None, "direction": "added",
                })
                summary["totals"]["added"] += 1
                continue
            if new_v is None:
                changes.append({
                    "path": key, "old": old_v, "new": None,
                    "delta": None, "delta_pct": None, "direction": "removed",
                })
                summary["totals"]["removed"] += 1
                continue
            if abs(new_v - old_v) < 1e-9:
                continue
            delta = new_v - old_v
            delta_pct = (delta / old_v) * 100 if old_v else None
            if delta_pct is not None and abs(delta_pct) < min_pct:
                continue
            direction = "hotter" if delta < 0 else "colder"
            changes.append({
                "path": key, "old": round(old_v, 3), "new": round(new_v, 3),
                "delta": round(delta, 3),
                "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
                "direction": direction,
            })
            summary["totals"]["changed"] += 1
            summary["totals"][direction] += 1

        if changes:
            summary["by_match"].append({
                "match_no": mno,
                "home_team": new_match.get("home_team", ""),
                "away_team": new_match.get("away_team", ""),
                "changes": changes,
            })

    return summary


def format_diff_console(diff: dict[str, Any], max_per_match: int = 8) -> str:
    """把 diff 渲染成对人友好的文本。"""
    lines: list[str] = []
    code = diff.get("code")
    prev = diff.get("previous_captured_at") or "(无)"
    curr = diff.get("current_captured_at")
    t = diff["totals"]

    if t["changed"] == 0 and t["added"] == 0 and t["removed"] == 0:
        lines.append(f"  [diff] {code}: 与上次抓取一致，无变化")
        return "\n".join(lines)

    lines.append(
        f"  [diff] {code}: "
        f"changed={t['changed']} (压热↓{t['hotter']} / 压冷↑{t['colder']}) "
        f"added={t['added']} removed={t['removed']}"
    )
    lines.append(f"         上次：{prev}")
    lines.append(f"         本次：{curr}")

    arrow = {"hotter": "↓压热", "colder": "↑压冷", "added": "+新增", "removed": "-下架"}

    for match in diff.get("by_match", []):
        lines.append(
            f"  ─ {match['match_no']}  {match['home_team']} vs {match['away_team']}"
        )
        sorted_changes = sorted(
            match["changes"],
            key=lambda c: abs(c.get("delta_pct") or 0),
            reverse=True,
        )
        for i, c in enumerate(sorted_changes):
            if i >= max_per_match:
                lines.append(f"      … 其余 {len(sorted_changes) - max_per_match} 项省略")
                break
            old = "—" if c["old"] is None else f"{c['old']:>6.2f}"
            new = "—" if c["new"] is None else f"{c['new']:>6.2f}"
            pct = (
                "         "
                if c["delta_pct"] is None
                else f"{c['delta_pct']:+6.2f}%"
            )
            lines.append(
                f"      {c['path']:<22}  {old} → {new}  {arrow[c['direction']]}  {pct}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取体彩竞彩足球赔率")
    parser.add_argument("--day", help="只抓指定 matchNumDate（如 260614）")
    parser.add_argument(
        "--within-hours",
        type=int,
        metavar="N",
        help="仅保留未来 N 小时内可投注场次（status=Selling 且未开赛）",
    )
    parser.add_argument(
        "--emit-window",
        action="store_true",
        help="与 --within-hours 联用，额外写出 odds_window_<N>h_<ts>.json 合并快照",
    )
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录（默认：脚本所在目录）",
    )
    parser.add_argument(
        "--save-raw", action="store_true",
        help="同时保留 API 原始响应到 raw/ 子目录",
    )
    parser.add_argument(
        "--no-diff", action="store_true",
        help="不计算赔率漂移（默认会自动找同一天最新的旧文件做对比）",
    )
    parser.add_argument(
        "--diff-min-pct", type=float, default=0.0,
        help="过滤变化绝对值小于该百分比的项（默认 0 = 显示全部）",
    )
    args = parser.parse_args()

    ensure_snapshot_dirs()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch_odds] GET {API_URL}")
    try:
        raw = fetch_api()
    except Exception as e:
        print(f"[fetch_odds] 请求失败：{e}", file=sys.stderr)
        return 1

    if not raw.get("success"):
        print(f"[fetch_odds] API 返回错误：{raw.get('errorMessage')}", file=sys.stderr)
        return 1

    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")

    if args.save_raw:
        raw_dir = SNAPSHOT_RAW_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"api_match_calc_{_iso_to_compact(captured_at)}.json"
        write_json(raw_path, raw)
        print(f"[fetch_odds] raw -> {rel_snapshot(raw_path)}")

    diff_dir = SNAPSHOT_DIFFS_DIR
    diff_dir.mkdir(parents=True, exist_ok=True)

    ts_compact = _iso_to_compact(captured_at)

    written: list[str] = []
    diffs_printed: list[str] = []
    window_day_payloads: list[dict[str, Any]] = []
    now_cn = datetime.now(CN_TZ)

    for day in raw.get("value", {}).get("matchInfoList", []) or []:
        code = day.get("matchNumDate", "")
        if args.day and code != args.day:
            continue
        if not day.get("subMatchList"):
            continue

        day_data = build_day_file(day, captured_at)
        if args.within_hours:
            filtered = filter_bettable_matches(
                day_data["matches"],
                within_hours=args.within_hours,
                now=now_cn,
            )
            day_data["matches"] = filtered
            day_data["total_matches_on_page"] = len(filtered)
            day_data["window_hours"] = args.within_hours
            day_data["notes"] = [
                f"已按 {args.within_hours}h 窗口过滤：仅保留 status=Selling 且未开赛场次。",
                *day_data.get("notes", []),
            ]
            if filtered:
                window_day_payloads.append(day_data)
        target = output_dir / f"odds_{code}_{ts_compact}.json"

        prev_data: dict[str, Any] | None = None
        prev_path = _find_latest_existing(output_dir, code)
        if prev_path is not None:
            try:
                with open(prev_path, "r", encoding="utf-8") as f:
                    prev_data = json.load(f)
            except Exception as e:
                print(
                    f"[fetch_odds] 读取旧文件失败 {prev_path}: {e}",
                    file=sys.stderr,
                )

        if args.within_hours and not day_data["matches"]:
            print(f"[fetch_odds] skip {code}: 0 matches in {args.within_hours}h window")
            continue

        write_json(target, day_data)
        prev_hint = f" (vs {prev_path.name})" if prev_path else ""
        cov = day_data.get("market_coverage", {})
        crs_cov = cov.get("比分", {})
        ttg_cov = cov.get("总进球数", {})
        print(
            f"[fetch_odds] {target.name}  "
            f"matches={len(day_data['matches'])}  issue={day_data['issue_no']}"
            f"  比分={crs_cov.get('已开盘', 0)}/{len(day_data['matches'])}"
            f"  总进球={ttg_cov.get('已开盘', 0)}/{len(day_data['matches'])}"
            f"{prev_hint}"
        )
        written.append(str(target))

        if args.no_diff or prev_data is None:
            continue
        diff = compute_diff(prev_data, day_data, min_pct=args.diff_min_pct)
        rendered = format_diff_console(diff)
        diffs_printed.append(rendered)

        diff_dir.mkdir(parents=True, exist_ok=True)
        diff_path = diff_dir / f"diff_{code}_{ts_compact}.json"
        with open(diff_path, "w", encoding="utf-8") as f:
            json.dump(diff, f, ensure_ascii=False, indent=2)

    if args.emit_window and args.within_hours and window_day_payloads:
        window_data = build_window_file(
            window_day_payloads, captured_at, args.within_hours
        )
        window_target = output_dir / f"odds_window_{args.within_hours}h_{ts_compact}.json"
        write_json(window_target, window_data)
        written.append(str(window_target))
        print(
            f"[fetch_odds] {window_target.name}  "
            f"matches={len(window_data['matches'])}  "
            f"days={','.join(window_data.get('match_days_included') or [])}"
        )

    if not written:
        print("[fetch_odds] 没有匹配到任何赛事（检查 --day 参数）。", file=sys.stderr)
        return 2

    if diffs_printed:
        print("\n[fetch_odds] === 赔率漂移 ===")
        for block in diffs_printed:
            print(block)
            print()

    print(f"[fetch_odds] 完成，共写出 {len(written)} 个文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
