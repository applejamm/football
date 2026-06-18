#!/usr/bin/env python3
"""
中国体彩竞彩足球 - 基本面信息抓取脚本（v0.1，仅 ESPN 公开端点）

数据来源：ESPN 公开 API（无需 API key）
  - 当日赛程：site.api.espn.com/apis/site/v2/sports/soccer/<league>/scoreboard?dates=YYYYMMDD
  - 单场详情：site.api.espn.com/apis/site/v2/sports/soccer/<league>/summary?event=<event_id>

只搬运、不解释。本脚本不做胜负平概率推断，只把"近 5 场状态 / 共识赔率 / H2H / 赛前舆论"拉下来落盘，
让人或下游 V2 报告生成步骤自己判断。

输出（每次运行都是独立时间快照）：
  snapshots/fundamentals/fundamentals_<league_slug>_<YYYYMMDD>-<HHMMSS>.json
  snapshots/fundamentals/fundamentals_<league_slug>_<YYYYMMDD>-<HHMMSS>.md
  snapshots/fundamentals/fundamentals_db.json
  snapshots/fundamentals/teams/<team>.json

用法：
    python3 fetch_fundamentals.py                              # 抓今天的 fifa.world（国家队赛事）
    python3 fetch_fundamentals.py --date 20260614              # 抓指定日期
    python3 fetch_fundamentals.py --league eng.1 --date ...    # 抓五大联赛（俱乐部）
    python3 fetch_fundamentals.py --teams Germany Japan        # 仅保留含这些球队的比赛

ESPN league slug 速查（按需扩展）：
    fifa.world          国家队赛事（友谊赛 / 世预赛 / 世界杯）
    eng.1               英超
    esp.1               西甲
    ger.1               德甲
    ita.1               意甲
    fra.1               法甲

数据覆盖度警告（实测 2026-06-14）：
    - 国家队场景下 ESPN 不返回伤停 / 首发 / 天气；只可靠拉到"近 5 场状态"
    - 俱乐部赛事覆盖度更高（首发 / 球队统计可用），但本脚本 v0.1 未做差异化处理
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

DB_SCHEMA_VERSION = "0.1"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

from artifact_lib import (
    SNAPSHOT_FUNDAMENTALS_DIR,
    fundamentals_search_dirs,
    latest_in_dirs,
    odds_search_dirs,
    rel_snapshot,
)

DEFAULT_OUTPUT_DIR = SNAPSHOT_FUNDAMENTALS_DIR


def http_json(url: str, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_daily_schedule(league_slug: str, date_yyyymmdd: str) -> dict[str, Any]:
    url = f"{ESPN_BASE}/{league_slug}/scoreboard?dates={date_yyyymmdd}"
    return http_json(url)


def fetch_event_summary(league_slug: str, event_id: str) -> dict[str, Any]:
    url = f"{ESPN_BASE}/{league_slug}/summary?event={event_id}"
    return http_json(url)


def extract_event_basics(event: dict[str, Any]) -> dict[str, Any]:
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    return {
        "event_id": event.get("id"),
        "name": event.get("name"),
        "short_name": event.get("shortName"),
        "date": event.get("date"),
        "status": event.get("status", {}).get("type", {}).get("name"),
        "venue": comp.get("venue", {}).get("fullName"),
        "home": home.get("team", {}).get("displayName"),
        "away": away.get("team", {}).get("displayName"),
    }


def extract_summary_features(summary: dict[str, Any]) -> dict[str, Any]:
    """从 summary 抽出 V2 第 8 节相关字段。缺失字段写 None，不编造。"""
    out: dict[str, Any] = {
        "last_five_games": [],
        "head_to_head": [],
        "consensus_odds": None,
        "rosters_size": [],
        "news_headlines": [],
        "missing": [],
    }

    for t in summary.get("lastFiveGames", []) or []:
        team = t.get("team", {}).get("displayName", "?")
        events = []
        for e in t.get("events", []) or []:
            events.append({
                "date": (e.get("gameDate") or "")[:10],
                "opponent": e.get("opponent", {}).get("displayName"),
                "result": e.get("gameResult"),
                "score": e.get("score"),
                "at_venue": e.get("atVs"),
            })
        out["last_five_games"].append({"team": team, "events": events})
    if not out["last_five_games"]:
        out["missing"].append("last_five_games")

    for h in summary.get("headToHeadGames", []) or []:
        title = h.get("title")
        note = h.get("note") or ""
        events = []
        for e in h.get("events", []) or []:
            events.append({
                "date": (e.get("gameDate") or "")[:10],
                "score": e.get("score"),
                "result": e.get("gameResult"),
            })
        out["head_to_head"].append({"title": title, "note": note, "events": events})
    if not out["head_to_head"] or all(not h["events"] for h in out["head_to_head"]):
        out["missing"].append("head_to_head")

    odds = summary.get("odds") or []
    if odds:
        first = odds[0]
        out["consensus_odds"] = {
            "provider": first.get("provider", {}).get("name"),
            "details": first.get("details"),
            "spread": first.get("spread"),
            "over_under": first.get("overUnder"),
            "home_money_line": first.get("homeTeamOdds", {}).get("moneyLine"),
            "draw_money_line": first.get("drawOdds", {}).get("moneyLine"),
            "away_money_line": first.get("awayTeamOdds", {}).get("moneyLine"),
        }
    else:
        out["missing"].append("consensus_odds")

    for r in summary.get("rosters", []) or []:
        team = r.get("team", {}).get("displayName")
        size = len(r.get("roster", []) or [])
        out["rosters_size"].append({"team": team, "size": size})
    if all(rs["size"] == 0 for rs in out["rosters_size"]):
        out["missing"].append("rosters_lineups_injuries")

    for n in (summary.get("news") or {}).get("articles", []) or []:
        out["news_headlines"].append({
            "headline": n.get("headline"),
            "type": n.get("type"),
            "published": n.get("published"),
            "link": (n.get("links") or {}).get("web", {}).get("href"),
        })

    return out


def _parse_score_goals(score: str | None) -> tuple[int | None, int | None]:
    if not score or "-" not in score:
        return None, None
    a, b = score.replace(" ", "").split("-", 1)
    try:
        return int(a), int(b)
    except ValueError:
        return None, None


def _goals_from_events(events: list[dict]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for e in events:
        hg, ag = _parse_score_goals(e.get("score"))
        if hg is None:
            continue
        if e.get("at_venue") == "@":
            out.append((ag, hg))
        else:
            out.append((hg, ag))
    return out


def compute_team_stats_block(events: list[dict]) -> dict[str, Any]:
    n = len(events)
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_gf": None, "avg_ga": None, "form_score": None}
    wins = sum(1 for e in events if e.get("result") == "W")
    goals = _goals_from_events(events)
    avg_gf = sum(g[0] for g in goals) / len(goals) if goals else None
    avg_ga = sum(g[1] for g in goals) / len(goals) if goals else None
    w = sum(1 for e in events if e.get("result") == "W")
    d = sum(1 for e in events if e.get("result") == "D")
    form = (w * 3 + d) / (n * 3) * 100 if n else None
    return {
        "n": n,
        "win_rate": round(wins / n, 3),
        "avg_gf": round(avg_gf, 2) if avg_gf is not None else None,
        "avg_ga": round(avg_ga, 2) if avg_ga is not None else None,
        "form_score": round(form, 1) if form is not None else None,
    }


def _merge_events(primary: list[dict], extra: list[dict], limit: int = 10) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for e in primary + extra:
        key = f"{e.get('date')}|{e.get('opponent')}|{e.get('score')}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda x: x.get("date") or "", reverse=True)
    return merged[:limit]


def _teams_dir(output_dir: Path) -> Path:
    primary = output_dir / "teams"
    legacy = output_dir / "fundamentals" / "teams"
    if primary.is_dir() or not legacy.is_dir():
        return primary
    return legacy


def enrich_features_from_db(feat: dict[str, Any], home: str, away: str, output_dir: Path) -> dict[str, Any]:
    """补近 10 场与 team_stats（T-1-6 / T-1-7）。"""
    teams_dir = _teams_dir(output_dir)
    l5_map = {g["team"]: g.get("events", []) for g in feat.get("last_five_games", [])}

    def load_history(team: str) -> list[dict]:
        tf = teams_dir / f"{safe_team_filename(team)}.json"
        if not tf.exists():
            return []
        try:
            hist = json.loads(tf.read_text("utf-8")).get("history", [])
        except Exception:
            return []
        extra: list[dict] = []
        for h in reversed(hist):
            extra.extend(h.get("last_five_games") or [])
        return extra

    last_ten: list[dict] = []
    team_stats: dict[str, dict] = {}
    for team in (home, away):
        if not team:
            continue
        l5 = l5_map.get(team, [])
        l10 = _merge_events(l5, load_history(team), 10)
        last_ten.append({"team": team, "events": l10})
        team_stats[team] = compute_team_stats_block(l10)
        if len(l10) >= 10:
            team_stats[team]["win_rate_10"] = team_stats[team]["win_rate"]

    feat = dict(feat)
    feat["last_ten_games"] = last_ten
    feat["team_stats"] = team_stats
    return feat


def extract_h2h_last_three(h2h_blocks: list[dict]) -> list[dict]:
    """专采近 3 次正式交锋（T-1-4 补强）。"""
    events: list[dict] = []
    for b in h2h_blocks or []:
        events.extend(b.get("events") or [])
    events.sort(key=lambda x: x.get("date") or "", reverse=True)
    return events[:3]


def safe_team_filename(name: str) -> str:
    """把球队名转成跨平台稳定的文件名：Curaçao → Curacao，去除非字母数字。"""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ASCII", "ignore").decode("ASCII")
    cleaned = "".join(c if c.isalnum() else "_" for c in ascii_str).strip("_")
    return cleaned or "Unknown"


def _empty_db() -> dict[str, Any]:
    return {
        "meta": {
            "schema_version": DB_SCHEMA_VERSION,
            "last_upsert": None,
            "snapshot_count": 0,
            "match_count": 0,
            "team_count": 0,
        },
        "snapshots": {},
        "matches": {},
        "teams": {},
    }


def upsert_snapshot(
    output_dir: Path,
    league: str,
    date_yyyymmdd: str,
    snapshot_at: str,
    records: list[dict[str, Any]],
    source_json: str | None = None,
) -> tuple[Path, Path]:
    """把一次抓取的 records 累积进 fundamentals_db.json + fundamentals/teams/<name>.json。
    主键 (snapshot_at, match_id)，重复 upsert 幂等。
    """
    db_path = output_dir / "fundamentals_db.json"
    teams_dir = output_dir / "teams"
    teams_dir.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        try:
            db = json.loads(db_path.read_text("utf-8"))
        except Exception:
            db = _empty_db()
    else:
        db = _empty_db()

    snapshot_id = f"{league}_{snapshot_at}"
    match_ids = [r["event"]["event_id"] for r in records if r.get("event", {}).get("event_id")]

    db["snapshots"][snapshot_id] = {
        "league": league,
        "date": date_yyyymmdd,
        "snapshot_at": snapshot_at,
        "source_json": source_json,
        "match_ids": match_ids,
    }

    for r in records:
        ev = r["event"]
        feat = r["features"]
        mid = ev.get("event_id")
        if not mid:
            continue

        if mid not in db["matches"]:
            db["matches"][mid] = {
                "name": ev.get("name"),
                "league": league,
                "date": date_yyyymmdd,
                "home": ev.get("home"),
                "away": ev.get("away"),
                "venue": ev.get("venue"),
                "kickoff_utc": ev.get("date"),
                "snapshot_ids": [],
            }
        if snapshot_id not in db["matches"][mid]["snapshot_ids"]:
            db["matches"][mid]["snapshot_ids"].append(snapshot_id)

        for role, t_name in (("home", ev.get("home")), ("away", ev.get("away"))):
            if not t_name:
                continue
            if t_name not in db["teams"]:
                db["teams"][t_name] = {
                    "first_seen": snapshot_at,
                    "last_seen": snapshot_at,
                    "snapshot_count": 0,
                    "match_ids": [],
                }
            tinfo = db["teams"][t_name]
            tinfo["last_seen"] = max(tinfo.get("last_seen") or "", snapshot_at)
            tinfo["first_seen"] = min(tinfo.get("first_seen") or snapshot_at, snapshot_at)
            if mid not in tinfo["match_ids"]:
                tinfo["match_ids"].append(mid)

            team_file = teams_dir / f"{safe_team_filename(t_name)}.json"
            if team_file.exists():
                try:
                    team_data = json.loads(team_file.read_text("utf-8"))
                except Exception:
                    team_data = {"team": t_name, "schema_version": DB_SCHEMA_VERSION, "history": []}
            else:
                team_data = {"team": t_name, "schema_version": DB_SCHEMA_VERSION, "history": []}

            l5 = next((g for g in feat.get("last_five_games", []) if g.get("team") == t_name), None)
            opponent = ev.get("away") if role == "home" else ev.get("home")

            entry = {
                "snapshot_at": snapshot_at,
                "league": league,
                "match_id": mid,
                "match_name": ev.get("name"),
                "kickoff_utc": ev.get("date"),
                "as_role": role,
                "opponent": opponent,
                "last_five_games": (l5 or {}).get("events", []),
                "h2h": feat.get("head_to_head", []),
                "consensus_odds": feat.get("consensus_odds"),
                "missing_dimensions": feat.get("missing", []),
            }

            existing = {(h.get("snapshot_at"), h.get("match_id")) for h in team_data["history"]}
            if (snapshot_at, mid) not in existing:
                team_data["history"].append(entry)
                team_data["history"].sort(key=lambda h: (h.get("snapshot_at") or "", h.get("match_id") or ""))

            tinfo["snapshot_count"] = len([
                h for h in team_data["history"]
            ])

            team_file.write_text(json.dumps(team_data, ensure_ascii=False, indent=2), "utf-8")

    db["meta"]["snapshot_count"] = len(db["snapshots"])
    db["meta"]["match_count"] = len(db["matches"])
    db["meta"]["team_count"] = len(db["teams"])
    db["meta"]["last_upsert"] = snapshot_at

    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), "utf-8")
    return db_path, teams_dir


def render_markdown(records: list[dict[str, Any]], league_slug: str, date_yyyymmdd: str) -> str:
    snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append(f"# 基本面信息快照 · {league_slug} · {date_yyyymmdd}")
    lines.append("")
    lines.append(f"> 数据源：ESPN 公开 API（仅搬运、不解释）  ")
    lines.append(f"> 抓取时间：{snapshot_time}  ")
    lines.append(f"> 共 {len(records)} 场  ")
    lines.append(f"> 用途：贴入 V2 报告第 8 节「基本面交叉验证」，由人或 odds-analyst 自行解读")
    lines.append("")
    lines.append("**字段口径**：本脚本只覆盖 V2 第 8 节 5 项中的「近 5 场状态」一项稳定可拉，"
                 "另含「共识赔率」「赛前新闻」「H2H」三项辅助。"
                 "「伤停」「首发」「天气」在国家队场景下 ESPN 不提供，已显式标注为 N/A。")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not records:
        lines.append("> 当天该联赛无比赛。")
        return "\n".join(lines)

    for i, rec in enumerate(records, 1):
        ev = rec["event"]
        feat = rec["features"]
        lines.append(f"## {i}. {ev['name']}")
        lines.append("")
        lines.append(f"- event_id: `{ev['event_id']}`")
        lines.append(f"- 开赛时间（UTC）：{ev['date']}")
        lines.append(f"- 球场：{ev['venue']}")
        lines.append(f"- 状态：{ev['status']}")
        lines.append("")
        lines.append("### 8.1 近 5 场状态")
        lines.append("")
        if feat["last_five_games"]:
            for t in feat["last_five_games"]:
                lines.append(f"**{t['team']}**")
                lines.append("")
                lines.append("| 日期 | 主客 | 对手 | 结果 | 比分 |")
                lines.append("|---|---|---|---|---|")
                for e in t["events"]:
                    av = "vs" if e["at_venue"] == "vs" else ("@" if e["at_venue"] == "@" else (e["at_venue"] or "?"))
                    lines.append(f"| {e['date']} | {av} | {e['opponent'] or '?'} | {e['result'] or '?'} | {e['score'] or '?'} |")
                lines.append("")
        else:
            lines.append("> N/A — ESPN 未返回")
            lines.append("")

        lines.append("### 8.2 伤停 / 首发")
        lines.append("")
        rs = feat["rosters_size"]
        if rs and any(x["size"] > 0 for x in rs):
            for x in rs:
                lines.append(f"- {x['team']}: roster {x['size']} 人 ← 需进一步抽细节")
        else:
            lines.append("> **N/A — 国家队场景下 ESPN 不返回 roster / 伤停。**")
            lines.append("> 如需此项，请人工查阅各国官方公告或加 WebSearch 兜底。")
        lines.append("")

        lines.append("### 8.3 H2H 历史交手")
        lines.append("")
        h2h = feat["head_to_head"]
        any_h2h = any(h["events"] for h in h2h)
        if any_h2h:
            for h in h2h:
                if h["events"]:
                    lines.append(f"**{h['title'] or 'H2H'}** {h['note']}")
                    for e in h["events"]:
                        lines.append(f"- {e['date']}: {e['result']} {e['score']}")
        else:
            lines.append("> N/A — ESPN 未返回有效 H2H（国家队稀有交手为常见情况）")
        lines.append("")

        lines.append("### 8.4 共识赔率（DraftKings / 海外大盘）")
        lines.append("")
        co = feat["consensus_odds"]
        if co:
            lines.append(f"- 提供方：{co['provider']}")
            lines.append(f"- 让球详情：`{co['details']}`（spread={co['spread']}, O/U={co['over_under']}）")
            lines.append(f"- moneyline：home={co['home_money_line']} / draw={co['draw_money_line']} / away={co['away_money_line']}")
            lines.append("")
            lines.append("> 用途：与体彩盘对照——如果海外把主队赔率定得明显更短而体彩偏长，可能是错价机会；反之亦然。")
        else:
            lines.append("> N/A")
        lines.append("")

        lines.append("### 8.5 天气 / 动机")
        lines.append("")
        lines.append("> N/A — ESPN summary 不含天气；动机需人脑判断（友谊赛 / 世预赛 / 大赛阶段差异巨大）")
        lines.append("")

        lines.append("### 8.6 赛前新闻（前 5 条）")
        lines.append("")
        nh = feat["news_headlines"][:5]
        if nh:
            for n in nh:
                lines.append(f"- [{n['headline']}]({n['link'] or '#'}) ({n['type']})")
        else:
            lines.append("> N/A")
        lines.append("")

        forecast = rec.get("forecast")
        if forecast:
            from forecast_lib import render_forecast_markdown_blocks  # noqa: WPS433

            lines.extend(
                render_forecast_markdown_blocks(forecast, forecast.get("match_no") or "")
            )

        if feat["missing"]:
            lines.append(f"### 8.x 缺失维度")
            lines.append("")
            lines.append(f"> 本场 ESPN 缺：`{', '.join(feat['missing'])}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("## 数据诚实性声明")
    lines.append("")
    lines.append("- 本脚本只搬运 ESPN 字段，未编造任何伤停 / 首发 / 状态")
    lines.append("- 缺失维度全部明示 N/A，绝不用其它字段假装填充")
    lines.append("- 「近 5 场」的对手强度差异未做调整（友谊赛 vs 大赛对手不可比），由人脑或 odds-analyst V2 第 3 节处理")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--date", default=datetime.now().strftime("%Y%m%d"),
                   help="比赛日期 YYYYMMDD（默认今天）")
    p.add_argument("--league", default="fifa.world",
                   help="ESPN league slug（默认 fifa.world，即国家队赛事）")
    p.add_argument("--teams", nargs="*", default=None,
                   help="只保留含这些球队的比赛（英文，按 ESPN 显示名匹配；可多个）")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                   help="输出目录")
    p.add_argument("--print-md", action="store_true", help="同时把 markdown 打到 stdout")
    from artifact_lib import add_emit_md_arg  # noqa: WPS433

    add_emit_md_arg(p)
    p.add_argument("--no-db", action="store_true",
                   help="不要 upsert 到 fundamentals_db.json + fundamentals/teams/（默认会写）")
    p.add_argument("--odds", default=None, help="体彩 odds JSON（enrich 预估赛果用；默认按日期找最新）")
    p.add_argument("--no-forecast", action="store_true",
                   help="跳过预估赛果 enrich（默认每次抓取后自动 enrich）")
    args = p.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] 抓取 {args.league} 在 {args.date} 的赛程……", file=sys.stderr)
    schedule = fetch_daily_schedule(args.league, args.date)
    events = schedule.get("events", []) or []
    print(f"[*] 当天共 {len(events)} 场", file=sys.stderr)

    if args.teams:
        wanted = [t.lower() for t in args.teams]
        events = [e for e in events if any(w in (e.get("name") or "").lower() for w in wanted)]
        print(f"[*] 按 --teams 过滤后剩 {len(events)} 场", file=sys.stderr)

    records: list[dict[str, Any]] = []
    for e in events:
        ev = extract_event_basics(e)
        eid = ev["event_id"]
        if not eid:
            continue
        print(f"[*] 拉 event_id={eid} {ev['name']}", file=sys.stderr)
        try:
            summary = fetch_event_summary(args.league, eid)
        except Exception as ex:
            print(f"[!] event {eid} summary 失败：{ex}", file=sys.stderr)
            continue
        feat = extract_summary_features(summary)
        feat["h2h_last_three"] = extract_h2h_last_three(feat.get("head_to_head", []))
        feat = enrich_features_from_db(feat, ev.get("home"), ev.get("away"), output_dir)
        records.append({"event": ev, "features": feat, "_raw_summary_keys": list(summary.keys())})

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"fundamentals_{args.league}_{stamp}.json"
    md_path = output_dir / f"fundamentals_{args.league}_{stamp}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "league": args.league,
                "date": args.date,
                "snapshot_at": stamp,
                "source": "ESPN public API",
                "match_count": len(records),
            },
            "records": records,
        }, f, ensure_ascii=False, indent=2)

    md = render_markdown(records, args.league, args.date) if args.emit_md or args.print_md else ""

    def _short(p: Path) -> str:
        try:
            return str(p.relative_to(Path.cwd()))
        except ValueError:
            return str(p)
    print(f"[OK] 写入 {_short(json_path)}", file=sys.stderr)
    if args.emit_md:
        md_path.write_text(md, encoding="utf-8")
        print(f"[OK] 写入 {_short(md_path)}", file=sys.stderr)

    if not args.no_forecast:
        odds_path: Path | None = Path(args.odds) if args.odds else None
        if odds_path is None or not odds_path.is_file():
            day6 = args.date[-6:] if len(args.date) >= 6 else args.date
            odds_path = latest_in_dirs(f"odds_{day6}_*.json", odds_search_dirs())
        if odds_path is None or not odds_path.is_file():
            odds_path = latest_in_dirs("odds_window_24h_*.json", odds_search_dirs())
        if odds_path and odds_path.is_file():
            from enrich_fundamentals_forecast import apply_enrich  # noqa: WPS433

            enriched, _ = apply_enrich(json_path, odds_path)
            print(f"[OK] 预估赛果 enrich · {enriched} 场 → 已写入 JSON 8.7 节", file=sys.stderr)
        else:
            print("[*] 无 odds 快照，跳过预估赛果 enrich", file=sys.stderr)

    if not args.no_db and records:
        db_path, teams_dir = upsert_snapshot(
            output_dir=output_dir,
            league=args.league,
            date_yyyymmdd=args.date,
            snapshot_at=stamp,
            records=records,
            source_json=json_path.name,
        )
        print(f"[OK] upsert {_short(db_path)}（snapshots={len([1 for _ in records])} matches）", file=sys.stderr)
        print(f"[OK] upsert {_short(teams_dir)} 下球队历史文件", file=sys.stderr)

    if args.print_md:
        if not md:
            md = render_markdown(records, args.league, args.date)
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
