#!/usr/bin/env python3
"""
基本面信号强弱评分（B 路：不出概率数字，只出状态分 + 与市场盘反向告警）

【方法论边界】
本脚本不输出"基本面胜负平概率"——5 场 + 4 H2H 的样本量做概率推断属于虚假精确，
反而会让用户用信噪比 1/100 的数据 PK 全球资金共识。
本脚本输出的是「可解释的信号分」，作为市场盘的"对照工具"，不是"决策工具"。

输入：
  最新或指定的 fundamentals_<league>_<时间>.json 快照
输出：
  scores_<league>_<date>_<时间>.json   结构化评分
  scores_<league>_<date>_<时间>.html   可视化对比页（自包含、可离线打开）

算法（可解释、不假装精确）：
  form_score          = (W*3 + D*1) / 15 * 100              # 0~100，每队近 5 场状态
  h2h_advantage_home  = (home_wins - home_losses) / total_h2h * 100   # -100~+100
  market_implied_prob = 从 DraftKings moneyline 反算 + 去水                # 三选一
  signal_gap          = home_form - away_form                        # -100~+100，正向 home

差异告警：
  当 (form_gap + h2h_advantage) / 2 > 20 且市场对应方 implied prob < 35% → "基本面与市场反向"
  反之亦然；其他情况标"一致 / 信号弱"

用法：
    python3 score_fundamentals.py                           # 自动用最新一份 fundamentals_*.json
    python3 score_fundamentals.py --snapshot <path.json>    # 指定快照
    python3 score_fundamentals.py --date 20260614           # 找该日期下最新一份
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

from artifact_lib import SNAPSHOT_FUNDAMENTALS_DIR, fundamentals_search_dirs

DEFAULT_DIR = SNAPSHOT_FUNDAMENTALS_DIR
SNAPSHOT_RE = re.compile(r"^fundamentals_(?P<league>[^_]+(?:\.[^_]+)*)_(?P<stamp>\d{8}-\d{6})\.json$")

DIVERGENCE_THRESHOLD = 20.0
MARKET_COLD_THRESHOLD = 0.35


def find_latest_snapshot(base: Path, date_yyyymmdd: str | None = None) -> Path | None:
    """date_yyyymmdd 匹配 meta.date（比赛日期），不是文件名的抓取时间戳。
    如果不传 date 就找全局最新一份快照。
    """
    files: list[Path] = []
    for directory in fundamentals_search_dirs():
        if directory.is_dir():
            files.extend(
                p for p in directory.glob("fundamentals_*.json") if SNAPSHOT_RE.match(p.name)
            )
    files = sorted(files, key=lambda p: p.name)
    if not files:
        return None
    if not date_yyyymmdd:
        return files[-1]
    for p in reversed(files):
        try:
            meta = json.loads(p.read_text("utf-8")).get("meta", {})
        except Exception:
            continue
        if meta.get("date") == date_yyyymmdd:
            return p
    return None


def compute_form_score(last_five_games: list[dict]) -> dict[str, Any]:
    if not last_five_games:
        return {"score": None, "wins": 0, "draws": 0, "losses": 0, "n": 0, "note": "no data"}
    w = sum(1 for e in last_five_games if e.get("result") == "W")
    d = sum(1 for e in last_five_games if e.get("result") == "D")
    l = sum(1 for e in last_five_games if e.get("result") == "L")
    n = w + d + l
    if n == 0:
        return {"score": None, "wins": 0, "draws": 0, "losses": 0, "n": 0, "note": "no data"}
    score = (w * 3 + d * 1) / (n * 3) * 100
    return {"score": round(score, 1), "wins": w, "draws": d, "losses": l, "n": n}


def compute_h2h_advantage(h2h_blocks: list[dict], home_team: str | None) -> dict[str, Any]:
    """ESPN 的 h2h_blocks 中 result 字段是「相对该 summary 主队（home）」的视角。
    我们直接按 home 视角计算优势。
    """
    if not h2h_blocks:
        return {"score": None, "wins": 0, "draws": 0, "losses": 0, "n": 0, "note": "no h2h"}
    all_events = []
    for b in h2h_blocks:
        all_events.extend(b.get("events") or [])
    if not all_events:
        return {"score": None, "wins": 0, "draws": 0, "losses": 0, "n": 0, "note": "h2h header only"}
    w = sum(1 for e in all_events if e.get("result") == "W")
    d = sum(1 for e in all_events if e.get("result") == "D")
    l = sum(1 for e in all_events if e.get("result") == "L")
    n = w + d + l
    if n == 0:
        return {"score": None, "wins": 0, "draws": 0, "losses": 0, "n": 0, "note": "no decisive h2h"}
    advantage = (w - l) / n * 100
    return {"score": round(advantage, 1), "wins": w, "draws": d, "losses": l, "n": n}


def moneyline_to_prob(ml: float | int | None) -> float | None:
    """美式赔率 → 隐含概率（含 vig）。
    ml > 0:  prob = 100 / (ml + 100)
    ml < 0:  prob = -ml / (-ml + 100)
    """
    if ml is None:
        return None
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml > 0:
        return 100.0 / (ml + 100.0)
    if ml < 0:
        return (-ml) / (-ml + 100.0)
    return None


def market_implied_probs(consensus_odds: dict | None) -> dict[str, Any] | None:
    if not consensus_odds:
        return None
    home = moneyline_to_prob(consensus_odds.get("home_money_line"))
    draw = moneyline_to_prob(consensus_odds.get("draw_money_line"))
    away = moneyline_to_prob(consensus_odds.get("away_money_line"))
    if None in (home, draw, away):
        return None
    total = home + draw + away
    if total <= 0:
        return None
    return {
        "provider": consensus_odds.get("provider"),
        "details": consensus_odds.get("details"),
        "home_raw": round(home, 4),
        "draw_raw": round(draw, 4),
        "away_raw": round(away, 4),
        "vig": round(total - 1.0, 4),
        "home": round(home / total, 4),
        "draw": round(draw / total, 4),
        "away": round(away / total, 4),
    }


def score_record(rec: dict) -> dict[str, Any]:
    ev = rec["event"]
    feat = rec["features"]
    home = ev.get("home")
    away = ev.get("away")

    last_five_by_team = {g["team"]: g.get("events", []) for g in (feat.get("last_five_games") or [])}
    home_form = compute_form_score(last_five_by_team.get(home, []))
    away_form = compute_form_score(last_five_by_team.get(away, []))

    h2h = compute_h2h_advantage(feat.get("head_to_head") or [], home)
    market = market_implied_probs(feat.get("consensus_odds"))

    form_gap = None
    if home_form["score"] is not None and away_form["score"] is not None:
        form_gap = round(home_form["score"] - away_form["score"], 1)

    composite = None
    if form_gap is not None and h2h["score"] is not None:
        composite = round((form_gap + h2h["score"]) / 2, 1)
    elif form_gap is not None:
        composite = form_gap

    divergence = detect_divergence(composite, market)

    return {
        "event": ev,
        "home_form": home_form,
        "away_form": away_form,
        "h2h_advantage_home": h2h,
        "form_gap_home_minus_away": form_gap,
        "composite_signal_home_view": composite,
        "market_implied_probs": market,
        "divergence": divergence,
        "missing_dimensions": feat.get("missing", []),
    }


def detect_divergence(composite: float | None, market: dict | None) -> dict[str, Any]:
    if composite is None or market is None:
        return {"flag": "insufficient_data", "label": "信号不足", "color": "gray", "explain": "缺基本面或市场盘数据"}

    if composite >= DIVERGENCE_THRESHOLD:
        if market["home"] < MARKET_COLD_THRESHOLD:
            return {
                "flag": "fundamentals_favor_home_market_cold",
                "label": "基本面更看好主队，市场偏冷",
                "color": "yellow",
                "explain": f"基本面综合 {composite:+.0f} 偏向主队，但市场对主队胜定 {market['home']:.1%}（< {MARKET_COLD_THRESHOLD:.0%}）",
            }
        return {
            "flag": "fundamentals_and_market_align_home",
            "label": "基本面与市场一致（看好主队）",
            "color": "green",
            "explain": f"基本面 {composite:+.0f} 偏向主队，市场也定主队胜 {market['home']:.1%}",
        }
    if composite <= -DIVERGENCE_THRESHOLD:
        if market["away"] < MARKET_COLD_THRESHOLD:
            return {
                "flag": "fundamentals_favor_away_market_cold",
                "label": "基本面更看好客队，市场偏冷",
                "color": "yellow",
                "explain": f"基本面综合 {composite:+.0f} 偏向客队，但市场对客队胜定 {market['away']:.1%}（< {MARKET_COLD_THRESHOLD:.0%}）",
            }
        return {
            "flag": "fundamentals_and_market_align_away",
            "label": "基本面与市场一致（看好客队）",
            "color": "green",
            "explain": f"基本面 {composite:+.0f} 偏向客队，市场也定客队胜 {market['away']:.1%}",
        }
    return {
        "flag": "weak_signal",
        "label": "基本面信号弱 / 双方接近",
        "color": "gray",
        "explain": f"基本面综合 {composite:+.0f}，未达差异阈值 ±{DIVERGENCE_THRESHOLD:.0f}",
    }


HTML_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>基本面信号 vs 市场盘 · ${league} · ${date}</title>
<style>
  *,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
    background: linear-gradient(180deg, #0b1220 0%, #1e293b 100%);
    color: #e2e8f0;
    padding: 32px 20px 80px;
    min-height: 100vh;
    line-height: 1.5;
  }
  .container { max-width: 1100px; margin: 0 auto; }
  header { margin-bottom: 28px; }
  h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
  .subtitle { color: #94a3b8; font-size: 13px; margin-top: 6px; }
  .disclaimer {
    background: rgba(251,191,36,0.08);
    border: 1px solid rgba(251,191,36,0.25);
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 12.5px;
    color: #fcd34d;
    margin-bottom: 22px;
    line-height: 1.6;
  }
  .disclaimer strong { color: #fde68a; }

  .match-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 22px;
    margin-bottom: 18px;
  }
  .match-title {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .match-meta {
    font-size: 11.5px;
    color: #64748b;
    margin-bottom: 18px;
  }

  .panels {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
    margin-bottom: 16px;
  }
  @media (max-width: 720px) { .panels { grid-template-columns: 1fr; } }

  .panel {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 14px 16px;
  }
  .panel-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94a3b8;
    margin-bottom: 12px;
  }

  .bar-row { display: grid; grid-template-columns: 90px 1fr 56px; gap: 10px; align-items: center; margin-bottom: 8px; font-size: 13px; }
  .bar-row .label { color: #cbd5e1; font-weight: 500; }
  .bar-track { height: 14px; background: rgba(255,255,255,0.05); border-radius: 7px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 7px; transition: width 0.3s; }
  .bar-fill.home { background: linear-gradient(90deg, #34d399, #10b981); }
  .bar-fill.away { background: linear-gradient(90deg, #60a5fa, #3b82f6); }
  .bar-fill.draw { background: linear-gradient(90deg, #cbd5e1, #94a3b8); }
  .bar-row .pct { font-variant-numeric: tabular-nums; color: #e2e8f0; text-align: right; font-size: 12.5px; }

  .h2h-meter {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px dashed rgba(255,255,255,0.08);
  }
  .h2h-label { font-size: 11.5px; color: #94a3b8; margin-bottom: 6px; display: flex; justify-content: space-between; }
  .h2h-track {
    position: relative;
    height: 12px;
    background: rgba(255,255,255,0.05);
    border-radius: 6px;
    overflow: hidden;
  }
  .h2h-center { position: absolute; top: 0; bottom: 0; left: 50%; width: 1px; background: rgba(255,255,255,0.2); }
  .h2h-fill-home { position: absolute; top: 0; bottom: 0; right: 50%; background: linear-gradient(90deg, transparent, #10b981); border-radius: 6px 0 0 6px; }
  .h2h-fill-away { position: absolute; top: 0; bottom: 0; left: 50%; background: linear-gradient(90deg, #3b82f6, transparent); border-radius: 0 6px 6px 0; }

  .alert-box {
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 13.5px;
    line-height: 1.55;
    margin-top: 4px;
  }
  .alert-box.green { background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.25); color: #86efac; }
  .alert-box.yellow { background: rgba(251,191,36,0.10); border: 1px solid rgba(251,191,36,0.30); color: #fde68a; }
  .alert-box.gray { background: rgba(148,163,184,0.08); border: 1px solid rgba(148,163,184,0.20); color: #cbd5e1; }
  .alert-label { font-weight: 600; margin-bottom: 4px; }
  .alert-explain { font-size: 12px; color: inherit; opacity: 0.85; }

  .miss-tag {
    display: inline-block;
    margin-top: 8px;
    font-size: 11px;
    color: #f87171;
    background: rgba(248,113,113,0.08);
    border: 1px solid rgba(248,113,113,0.20);
    border-radius: 4px;
    padding: 2px 8px;
  }

  footer {
    margin-top: 28px;
    padding-top: 18px;
    border-top: 1px solid rgba(255,255,255,0.08);
    color: #64748b;
    font-size: 11.5px;
    line-height: 1.7;
  }
  footer code { background: rgba(255,255,255,0.05); padding: 1px 5px; border-radius: 3px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>基本面信号 vs 市场盘 · ${league} · ${date}</h1>
    <div class="subtitle">生成时间 ${generated_at} · 共 ${match_count} 场 · 数据源 ESPN（基本面 + DraftKings 共识盘）</div>
  </header>

  <div class="disclaimer">
    <strong>方法论边界</strong>：本页面<strong>不输出"胜负平概率数字"</strong>。基本面信号分仅基于"近 5 场 + H2H + 主客场"，
    样本量极小，无法 PK 市场盘背后的全球资金共识。<br>
    本页面的设计意图是<strong>对照</strong>：当基本面信号与市场盘<strong>反向</strong>时，提示你重新审视市场判断；
    当一致时，让你对市场判断更有信心。<strong>不是替代市场盘的胜率推断工具。</strong>
  </div>

${cards_html}

  <footer>
    生成命令：<code>python3 score_fundamentals.py --date ${date}</code><br>
    算法：form_score = (W·3 + D·1)/15·100 ；h2h_advantage = (主胜 − 主负)/总数·100 ；composite = (form_gap + h2h)/2<br>
    告警阈值：composite ≥ ±20 且对应方市场 implied prob &lt; 35% → 反向告警；详见 <code>scores_*.json</code>
  </footer>
</div>
</body>
</html>
""")


def render_card(scored: dict) -> str:
    ev = scored["event"]
    home = ev.get("home", "?")
    away = ev.get("away", "?")
    market = scored.get("market_implied_probs")
    home_form = scored["home_form"]
    away_form = scored["away_form"]
    h2h = scored["h2h_advantage_home"]
    div = scored["divergence"]
    composite = scored.get("composite_signal_home_view")

    lines = []
    lines.append('  <div class="match-card">')
    lines.append(f'    <div class="match-title">{home} vs {away}</div>')
    lines.append(f'    <div class="match-meta">event_id {ev.get("event_id","?")} · {ev.get("date","?")} · {ev.get("venue","?")}</div>')
    lines.append('    <div class="panels">')

    lines.append('      <div class="panel">')
    lines.append('        <div class="panel-title">市场共识（DraftKings 去 vig）</div>')
    if market:
        for key, label, css in (("home", f"{home} 胜", "home"),
                                 ("draw", "平", "draw"),
                                 ("away", f"{away} 胜", "away")):
            pct = market[key] * 100
            lines.append('        <div class="bar-row">')
            lines.append(f'          <div class="label">{label}</div>')
            lines.append(f'          <div class="bar-track"><div class="bar-fill {css}" style="width:{min(pct, 100):.1f}%"></div></div>')
            lines.append(f'          <div class="pct">{pct:.1f}%</div>')
            lines.append('        </div>')
        lines.append(f'        <div class="match-meta" style="margin-top:8px">提供方 {market["provider"]} · 含 vig {market["vig"]*100:.1f}% · 让球 {market["details"]}</div>')
    else:
        lines.append('        <div class="match-meta">N/A — 无共识盘数据</div>')
    lines.append('      </div>')

    lines.append('      <div class="panel">')
    lines.append('        <div class="panel-title">基本面信号（不是概率）</div>')
    for team_label, form, css in ((home, home_form, "home"), (away, away_form, "away")):
        if form["score"] is not None:
            sc = form["score"]
            sub = f"近{form['n']}: {form['wins']}胜{form['draws']}平{form['losses']}负"
            lines.append('        <div class="bar-row">')
            lines.append(f'          <div class="label">{team_label}<br><span style="font-size:10.5px;color:#64748b;">{sub}</span></div>')
            lines.append(f'          <div class="bar-track"><div class="bar-fill {css}" style="width:{sc:.1f}%"></div></div>')
            lines.append(f'          <div class="pct">{sc:.0f}/100</div>')
            lines.append('        </div>')
        else:
            lines.append('        <div class="bar-row">')
            lines.append(f'          <div class="label">{team_label}</div>')
            lines.append('          <div class="bar-track"></div>')
            lines.append('          <div class="pct">N/A</div>')
            lines.append('        </div>')

    if h2h["score"] is not None:
        h2h_sc = h2h["score"]
        if h2h_sc >= 0:
            home_w = h2h_sc
            away_w = 0
        else:
            home_w = 0
            away_w = -h2h_sc
        lines.append('        <div class="h2h-meter">')
        lines.append(f'          <div class="h2h-label"><span>{home} ←</span><span>H2H 偏向</span><span>→ {away}</span></div>')
        lines.append('          <div class="h2h-track">')
        lines.append(f'            <div class="h2h-fill-home" style="width:{home_w/2:.1f}%"></div>')
        lines.append(f'            <div class="h2h-fill-away" style="width:{away_w/2:.1f}%"></div>')
        lines.append('            <div class="h2h-center"></div>')
        lines.append('          </div>')
        lines.append(f'          <div class="match-meta" style="margin-top:6px">基于 {h2h["n"]} 次历史交手（home 视角 {h2h["wins"]}胜{h2h["draws"]}平{h2h["losses"]}负，advantage {h2h_sc:+.0f}）</div>')
        lines.append('        </div>')
    else:
        lines.append(f'        <div class="match-meta" style="margin-top:10px">H2H：{h2h.get("note","N/A")}</div>')

    if composite is not None:
        lines.append(f'        <div class="match-meta" style="margin-top:10px">综合信号（home 视角）：<strong>{composite:+.0f}</strong></div>')
    lines.append('      </div>')

    lines.append('    </div>')

    lines.append(f'    <div class="alert-box {div["color"]}">')
    lines.append(f'      <div class="alert-label">{div["label"]}</div>')
    lines.append(f'      <div class="alert-explain">{div["explain"]}</div>')
    lines.append('    </div>')

    if scored.get("missing_dimensions"):
        lines.append(f'    <div class="miss-tag">缺失维度：{", ".join(scored["missing_dimensions"])}</div>')

    lines.append('  </div>')
    return "\n".join(lines)


def render_html(scored_records: list[dict], league: str, date: str) -> str:
    cards = "\n".join(render_card(r) for r in scored_records) if scored_records else \
        '<div class="match-card"><div class="match-meta">无可评分的比赛</div></div>'
    return HTML_TEMPLATE.substitute(
        league=league,
        date=date,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        match_count=len(scored_records),
        cards_html=cards,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--snapshot", help="指定 fundamentals_*.json 路径")
    p.add_argument("--date", help="按日期 YYYYMMDD 找最新一份快照")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="snapshots/fundamentals 目录")
    args = p.parse_args(argv)

    base = Path(args.dir)
    if args.snapshot:
        snap_path = Path(args.snapshot)
    else:
        snap_path = find_latest_snapshot(base, args.date)
    if not snap_path or not snap_path.exists():
        print(f"[!] 找不到快照（date={args.date}）。先跑 fetch_fundamentals.py", file=sys.stderr)
        return 1

    print(f"[*] 加载 {snap_path.name}", file=sys.stderr)
    data = json.loads(snap_path.read_text("utf-8"))
    meta = data.get("meta", {})
    records = data.get("records") or []
    if not records:
        print("[!] 快照内无 records", file=sys.stderr)
        return 1

    league = meta.get("league") or "?"
    date = meta.get("date") or "?"
    snapshot_at = meta.get("snapshot_at") or datetime.now().strftime("%Y%m%d-%H%M%S")

    scored = [score_record(r) for r in records]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = base / f"scores_{league}_{date}_{stamp}.json"
    html_path = base / f"scores_{league}_{date}_{stamp}.html"

    json_path.write_text(json.dumps({
        "meta": {
            "schema_version": "0.1",
            "source_snapshot": snap_path.name,
            "league": league,
            "date": date,
            "snapshot_at": snapshot_at,
            "scored_at": stamp,
            "match_count": len(scored),
            "method": "B-route signal scoring (no probability output)",
            "thresholds": {
                "divergence": DIVERGENCE_THRESHOLD,
                "market_cold": MARKET_COLD_THRESHOLD,
            },
        },
        "scored": scored,
    }, ensure_ascii=False, indent=2), "utf-8")

    html_path.write_text(render_html(scored, league, date), "utf-8")

    def _short(p: Path) -> str:
        try:
            return str(p.relative_to(Path.cwd()))
        except ValueError:
            return str(p)
    print(f"[OK] 写入 {_short(json_path)}", file=sys.stderr)
    print(f"[OK] 写入 {_short(html_path)}", file=sys.stderr)

    print()
    print(f"=== 评分摘要（{len(scored)} 场） ===", file=sys.stderr)
    for s in scored:
        ev = s["event"]
        composite = s.get("composite_signal_home_view")
        div = s["divergence"]
        composite_str = f"{composite:+.0f}" if composite is not None else "N/A"
        print(f"  {ev.get('home','?')} vs {ev.get('away','?'):20s}  composite={composite_str:>5s}  → {div['label']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
