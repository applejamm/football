#!/usr/bin/env python3
"""
从 scan_candidates 漏斗 JSON 生成决策草案（canonical JSON → HTML/可选 MD）。

用法：
    python3 generate_decision_draft.py \\
      --scan validation/drafts/scan_260616_demo.json \\
      --prediction prediction_260616_20260616-214115.json \\
      --budget 100 \\
      --prefix decision_260616_match017_FUNNEL

默认写出 decision_*.json，再由 write_html_from_json 派生 .html；--emit-md 时额外派生 .md。
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from workflow_status_lib import (
    render_workflow_pipeline_html,
    render_workflow_pipeline_md,
    steps_from_state_or_infer,
)
from forecast_lib import (
    collect_forecast_summary_rows,
    render_card_forecast_snippet,
    render_forecast_inner_html,
    render_forecast_markdown,
    render_forecast_summary_table_html,
    render_hero_forecast_html,
)
from strategy_gates_lib import stake_with_caps
from portfolio_lib import MODE_LABELS, build_portfolio, select_portfolio_plan

ROOT = Path(__file__).resolve().parent
TEMPLATE = (
    ROOT.parent / ".cursor/skills/football-betting-strategist/DECISION_HTML_TEMPLATE.html"
)
PLAY_DOT = {
    "wdl": "var(--play-wdl)",
    "hcap": "var(--play-hcap)",
    "total": "var(--play-tg)",
    "score": "var(--play-tg)",
    "parlay": "var(--accent)",
}


def resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pred_index(prediction: dict[str, Any]) -> dict[str, dict]:
    return {r["match_no"]: r for r in prediction.get("predictions") or []}


def hero_stake(budget: int, min_unit: int = 2) -> int:
    """主推单注：缩量预算的一半，取 min_unit 整数倍。"""
    raw = max(min_unit, budget // 2)
    return raw - (raw % min_unit)


def alt_stake(budget: int, min_unit: int = 2) -> int:
    """Top3 备选注：预算四分之一，取 min_unit 整数倍。"""
    raw = max(min_unit, budget // 4)
    return raw - (raw % min_unit)


def matchup_line(pred_row: dict | None, match_no: str) -> str:
    if pred_row:
        return f"{match_no} · {pred_row.get('home_cn', '?')} vs {pred_row.get('away_cn', '?')}"
    return match_no


def pct(n: float, digits: int = 1) -> str:
    return f"{n * 100:.{digits}f}"


def ev_pct(ev: float) -> str:
    return f"{ev * 100:.1f}%"


def bar_ratio(a: float, b: float) -> tuple[float, float]:
    t = a + b
    if t <= 0:
        return 50.0, 50.0
    return round(a / t * 100, 1), round(b / t * 100, 1)


def candidate_by_id(candidates: list[dict], cid: str | None) -> dict | None:
    if not cid:
        return None
    for row in candidates:
        if row.get("id") == cid:
            return row
    return None


def render_strategy_gates_md(gates: dict[str, Any] | None, budget: int) -> str:
    if not gates:
        return ""
    lines: list[str] = ["", "## ⚠️ 复盘策略闸（IMP-006/007/008）", ""]
    bud = gates.get("budget") or {}
    if bud.get("catastrophic_active"):
        lines.append(f"| catastrophic 缩量 | **{bud.get('effective', budget)} 元**（请求 {bud.get('requested')} 元） |")
        lines.append(f"| 原因 | {bud.get('reason', '—')} |")
        lines.append("")
    for trap in gates.get("low_odds_traps") or []:
        lines.append(
            f"- **IMP-007** {trap['match_no']} {trap['home_team']} vs {trap['away_team']}："
            f"{trap['favorite_side']}赔 {trap['win_odds']} / 平赔 {trap['draw_odds']} → "
            f"稳档封顶 **{trap['max_stable_stake']} 元**，须评估防平"
        )
    for alert in gates.get("draw_risk_alerts") or []:
        lines.append(
            f"- **IMP-008** {alert['match_no']} {alert['home_cn']} vs {alert['away_cn']}："
            f"引擎平 **{alert['draw_prob']*100:.1f}%**（Top1 {alert['engine_top1']}）→ {alert['recommendation']}"
        )
    if len(lines) <= 3:
        return ""
    return "\n".join(lines) + "\n"


def render_strategy_gates_html(gates: dict[str, Any] | None, budget: int) -> str:
    if not gates:
        return ""
    parts: list[str] = []
    bud = gates.get("budget") or {}
    if bud.get("catastrophic_active"):
        override = " · <b>用户已显式覆盖满预算</b>" if bud.get("override_used") else ""
        parts.append(
            f"""<div class="warn">
  <b>⚠️ IMP-006 · catastrophic 预算缩量 → {bud.get('effective', budget)} 元</b>
  {bud.get('reason', '')}{override}
  <small>满预算覆盖须 CLI <code>--allow-full-budget</code>（yaml 默认禁止随意满预算）</small>
</div>"""
        )
    traps = gates.get("low_odds_traps") or []
    alerts = gates.get("draw_risk_alerts") or []
    if traps or alerts:
        rows = ""
        for trap in traps:
            rows += (
                f"<tr><td>{trap['match_no']}</td><td>{trap['home_team']} vs {trap['away_team']}</td>"
                f"<td class=\"num\">{trap['win_odds']}</td><td class=\"num\">{trap['draw_odds']}</td>"
                f"<td class=\"num\">≤{trap['max_stable_stake']} 元</td>"
                f"<td>稳档封顶 · 评估防平</td></tr>"
            )
        for alert in alerts:
            rows += (
                f"<tr><td>{alert['match_no']}</td><td>{alert['home_cn']} vs {alert['away_cn']}</td>"
                f"<td class=\"num\">—</td><td class=\"num\">{alert['draw_prob']*100:.1f}%</td>"
                f"<td>—</td><td>{alert['recommendation']}</td></tr>"
            )
        parts.append(
            f"""<div class="warn" style="border-left-color:var(--accent);">
  <b>⚠️ IMP-007/008 · 低赔稳档 / 引擎平概率披露</b>
  <table class="t" style="margin-top:10px;font-size:12px;">
    <thead><tr><th>场次</th><th>对阵</th><th>胜/负赔</th><th>平赔/平概率</th><th>稳档上限</th><th>建议</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
        )
    return "\n".join(parts)


def extract_style_script(template_path: Path) -> tuple[str, str]:
    text = template_path.read_text(encoding="utf-8")
    doc = text.find("<!DOCTYPE")
    if doc < 0:
        raise ValueError("template missing DOCTYPE")
    text = text[doc:]
    style = re.search(r"<style>(.*?)</style>", text, re.S)
    script = re.search(r"<script>(.*?)</script>", text, re.S)
    if not style or not script:
        raise ValueError("template missing style or script")
    return style.group(1), script.group(1)


def render_top6_rows(top6: list[dict], hero_id: str) -> str:
    rows: list[str] = []
    for row in top6:
        sid = row["scheme_id"]
        dims = row["dims"]
        active = ' hero-link is-active' if sid == hero_id else ""
        st = row["status"]
        badge = "hero" if st == "主推" else ("in" if st == "入围" else "cut")
        badge_txt = st
        pt = row.get("play_type", "hcap")
        dot = PLAY_DOT.get(pt, "var(--accent)")
        d_ev, d_eng, d_fun, d_ind = (
            dims["ev_norm"],
            dims["engine"],
            dims["fundamentals"],
            dims["independence"],
        )
        detail = ""
        if sid != hero_id and st == "入围":
            detail = (
                f'<p style="margin:8px 0 0;font-size:11px;color:var(--muted);">'
                f"落选原因：综合分 {row['composite_score']} < 主推 {top6[0]['composite_score']}。</p>"
            )
        rows.append(
            f"""    <tr class="top6-row{active}" data-scheme-id="{sid}" data-score="{row['composite_score']}" data-amt="50"
        data-dims="{d_ev},{d_eng},{d_fun},{d_ind}" data-label="{row['match_no'][-3:]} {row['pick_label']}" data-odds="{row['odds']}" tabindex="0">
      <td class="num">{row['rank']}</td>
      <td><span class="play-type"><span class="play-dot" style="background:{dot}"></span>{row['category'][:2]}</span></td>
      <td>{row['match_no'][-3:]} {row['pick_label']}</td>
      <td class="ev-must num">{ev_pct(row['ev'])}</td>
      <td class="num">{row['composite_score']}</td>
      <td><div class="mini-dim"><i><b style="--w:{d_ev}%"></b></i><i><b style="--w:{d_eng}%"></b></i><i><b style="--w:{d_fun}%"></b></i><i><b style="--w:{max(d_ind,4)}%"></b></i></div></td>
      <td><span class="status {badge}">{badge_txt}</span></td>
    </tr>
    <tr class="top6-detail" data-for="{sid}"><td colspan="7"><div class="detail-inner">
      <div class="detail-grid">
        <div>EV<b class="num">{d_ev:.0f}</b></div><div>引擎<b class="num">{d_eng:.0f}</b></div>
        <div>基本面<b class="num">{d_fun:.0f}</b></div><div>独立<b class="num">{d_ind:.0f}</b></div>
      </div>{detail}</div></td></tr>"""
        )
    return "\n".join(rows)


def render_matchup(pred_row: dict, focus: bool = False) -> str:
    p = pred_row["prediction"]
    dims = p["dimensions"]
    op = p["outcome_probs"]
    xg = p.get("expected_goals") or {"home": 1.0, "away": 1.0}
    comp = p["composite"]["composite_home"]
    strength = dims.get("strength") or {}
    hi = strength.get("home_index")
    ai = strength.get("away_index")
    if hi is None or ai is None:
        hi = comp
        ai = 100.0 - comp
    mkt = (dims.get("market") or {}).get("probs") or op
    home_cn = pred_row.get("home_cn", "主队")
    away_cn = pred_row.get("away_cn", "客队")
    match_no = pred_row.get("match_no", "")
    sh, sa = bar_ratio(float(hi), float(ai))
    mh, ma = bar_ratio(mkt.get("胜", op["胜"]), mkt.get("负", op["负"]))
    eh, ea = bar_ratio(op["胜"], op["负"])
    xh, xa = bar_ratio(xg.get("home", 1.0), xg.get("away", 1.0))
    ph, pd, pl = op["胜"], op["平"], op["负"]
    focus_cls = " matchup focus" if focus else " matchup"
    tags = ""
    if focus:
        tags = f"""
    <div class="mu-tags">
      <span class="tag bet">主推场次 · S1</span>
      <span class="tag hot">引擎 Top1 主胜 {pct(op['胜'])}%</span>
    </div>"""
    forecast = render_forecast_inner_html(pred_row)
    foot = ""
    if focus:
        foot = f"""
    <div class="mu-foot">
      <span>主推场次 {match_no}</span>
      <span>综合主队优势 <b class="num">{comp:.1f}</b>/100</span>
    </div>"""
    return f"""
  <div class="{focus_cls.strip()}">
    <div class="mu-top">
      <span class="mu-id">{match_no}</span>
      <div class="mu-teams">
        <div class="team-side home"><div class="t-name">{home_cn}</div><div class="t-sub">主队</div></div>
        <span class="vs-badge">VS</span>
        <div class="team-side away"><div class="t-name">{away_cn}</div><div class="t-sub">客队</div></div>
      </div>
    </div>{tags}
    <div class="cmp-table">
      <div class="cmp-head"><span class="home-h">{home_cn}</span><span>对比参数</span><span class="away-h">{away_cn}</span></div>
      <div class="cmp-row">
        <span class="cmp-val home win">{float(hi):.0f}</span>
        <div><div class="cmp-label">硬实力 / 综合指数</div>
          <div class="cmp-bar-box"><div class="seg-h" style="width:{sh}%;"></div><div class="seg-a" style="width:{sa}%;"></div></div></div>
        <span class="cmp-val away">{float(ai):.1f}</span>
      </div>
      <div class="cmp-row">
        <span class="cmp-val home win">{pct(mkt.get('胜', op['胜']))}%</span>
        <div><div class="cmp-label">体彩去水胜率</div>
          <div class="cmp-bar-box"><div class="seg-h" style="width:{mh}%;"></div><div class="seg-a" style="width:{ma}%;"></div></div></div>
        <span class="cmp-val away">{pct(mkt.get('负', op['负']))}%</span>
      </div>
      <div class="cmp-row">
        <span class="cmp-val home win">{pct(op['胜'])}%</span>
        <div><div class="cmp-label">引擎综合胜率</div>
          <div class="cmp-bar-box"><div class="seg-h" style="width:{eh}%;"></div><div class="seg-a" style="width:{ea}%;"></div></div></div>
        <span class="cmp-val away">{pct(op['负'])}%</span>
      </div>
      <div class="cmp-row">
        <span class="cmp-val home">{xg.get('home', 1.0):.2f}</span>
        <div><div class="cmp-label">预期进球 xG</div>
          <div class="cmp-bar-box"><div class="seg-h" style="width:{xh}%;"></div><div class="seg-a" style="width:{xa}%;"></div></div></div>
        <span class="cmp-val away win">{xg.get('away', 1.0):.2f}</span>
      </div>
    </div>
    <div style="margin-top:12px;padding:10px 12px;background:rgba(15,23,42,.6);border-radius:8px;border:1px solid var(--line);">
      <div class="cmp-label" style="margin-bottom:6px;">胜平负概率（引擎）</div>
      <div class="prob-1x2">
        <div class="p-row"><span class="p-lab">胜</span><div class="p-bar"><i class="win-i" style="width:{pct(ph)}%;"></i></div><span class="p-val num">{pct(ph)}%</span></div>
        <div class="p-row"><span class="p-lab">平</span><div class="p-bar"><i class="draw-i" style="width:{pct(pd)}%;"></i></div><span class="p-val num">{pct(pd)}%</span></div>
        <div class="p-row"><span class="p-lab">负</span><div class="p-bar"><i class="lose-i" style="width:{pct(pl)}%;"></i></div><span class="p-val num">{pct(pl)}%</span></div>
      </div>
    </div>
    {forecast}{foot}
  </div>"""


def render_matchups_block(pred_idx: dict[str, dict], hero_match_no: str) -> str:
    """基本面已匹配场次并排展示（含预估赛果）。"""
    rows = [
        r for r in pred_idx.values()
        if r.get("fundamentals_matched")
    ]
    rows.sort(key=lambda x: x.get("match_no", ""))
    if not rows:
        hero = pred_idx.get(hero_match_no)
        return render_matchup(hero, focus=True) if hero else ""
    parts = []
    for r in rows:
        parts.append(render_matchup(r, focus=r["match_no"] == hero_match_no))
    return "\n".join(parts)


def render_top3_section(top3: list[dict], budget: int) -> str:
    if not top3:
        return ""
    rows = []
    for row in top3:
        stake = hero_stake(budget) if row["pick_rank"] == 1 else max(2, (budget // 4) - (budget // 4 % 2))
        win_gross = round(stake * float(row["odds"]), 2)
        rows.append(
            f"| **{row['pick_label_user']}** | {row['match_no']} | {row['pick_label']} | "
            f"{row['odds']} | {pct(row['p_true'])}% | {ev_pct(row['ev'])} | "
            f"{row['composite_score']} | {stake} 元 | **{win_gross} 元** | {row['win_gross']} 元（参考） |"
        )
    body = "\n".join(rows)
    return f"""
---

## Top 3 赢利方案（供选择 · T-5-7）

> 在 Top6 入围池内，按「参考注额 × 赔率」命中毛奖金降序排列；**方案 A** 为综合分最高主推，B/C 为赢利更高的备选玩法。

| 方案 | 场次 | 选项 | 赔率 | p_true | EV | 综合分 | 建议金额 | 命中奖金 | 参考排序奖金 |
|---|---|---|---|---|---|---|---|---|---|
{body}

**说明**：参考排序奖金按统一 {top3[0]['ref_stake']} 元注额计算，便于横向比较玩法赢利潜力；实际下单以建议金额为准。
"""


def render_top3_cards_html(
    top3: list[dict],
    budget: int,
    hero_candidate_id: str | None,
    pred_idx: dict[str, dict],
) -> str:
    if not top3:
        return ""
    cards: list[str] = []
    for row in top3:
        stake = hero_stake(budget) if row["pick_rank"] == 1 else alt_stake(budget)
        win_suggest = round(stake * float(row["odds"]), 2)
        cid = row.get("candidate_id") or ""
        is_match = bool(hero_candidate_id and cid == hero_candidate_id)
        match_cls = " is-hero-match" if is_match else ""
        badge = '<span class="hero-badge">同综合主推</span>' if is_match else ""
        match_line = matchup_line(pred_idx.get(row["match_no"]), row["match_no"])
        sid = row.get("scheme_id", "")
        card_fc = render_card_forecast_snippet(pred_idx.get(row["match_no"]))
        cards.append(
            f"""  <div class="top3-card{match_cls}" data-scheme-id="{sid}" data-candidate-id="{cid}" tabindex="0" role="button" aria-label="{row['pick_label_user']}">
    <div class="card-head">
      <span class="card-label">{row['pick_label_user']}</span>
      {badge}
    </div>
    <div class="match-line num">{match_line}</div>
    {card_fc}
    <div class="pick-line">{row['pick_label']} @ <span class="num">{row['odds']}</span></div>
    <div class="win-gross num">{win_suggest} 元</div>
    <div class="win-lab">命中毛奖金（建议 {stake} 元）</div>
    <div class="stat-row"><span>建议金额</span><span class="amt num">{stake} 元</span></div>
    <div class="stat-row"><span>p_true</span><span class="num">{pct(row['p_true'])}%</span></div>
    <div class="stat-row"><span>EV</span><span class="num">{ev_pct(row['ev'])}</span></div>
    <div class="stat-row"><span>综合分</span><span class="num">{row['composite_score']}</span></div>
    <div class="ref-note">参考排序：{row['ref_stake']} 元 × {row['odds']} = {row['win_gross']} 元</div>
  </div>"""
        )
    return "\n".join(cards)


def matchup_short(pred_row: dict | None, match_no: str) -> str:
    if pred_row:
        return f"{match_no} {pred_row.get('home_cn', '?')} vs {pred_row.get('away_cn', '?')}"
    return match_no


def apply_portfolio_stake_caps(
    portfolio: dict[str, Any],
    candidates: list[dict],
    budget: int,
    min_unit: int = 2,
) -> None:
    max_stakes: dict[str, int] = {}
    for leg in portfolio["legs"]:
        cand = candidate_by_id(candidates, leg.get("id"))
        cap = (cand.get("strategy_flags") or {}).get("max_stake_cap") if cand else None
        raw = int(leg["stake"])
        capped = stake_with_caps(raw, cand)
        max_stakes[leg["id"]] = int(cap) if cap is not None else budget
        leg["stake"] = capped
        leg["win_gross"] = round(leg["stake"] * float(leg["odds"]), 2)

    total = sum(int(l["stake"]) for l in portfolio["legs"])
    remainder = budget - total
    guard = 0
    while remainder > 0 and guard < 500:
        progressed = False
        for leg in portfolio["legs"]:
            if remainder <= 0:
                break
            leg_max = max_stakes.get(leg["id"], budget)
            if leg["stake"] + min_unit <= leg_max:
                leg["stake"] += min_unit
                leg["win_gross"] = round(leg["stake"] * float(leg["odds"]), 2)
                remainder -= min_unit
                progressed = True
        if not progressed:
            break
        guard += 1

    portfolio["total_stake"] = sum(int(l["stake"]) for l in portfolio["legs"])
    portfolio["budget"] = budget


def render_portfolio_md(
    portfolio: dict[str, Any],
    pred_idx: dict[str, dict],
    plan: dict[str, Any] | None = None,
) -> str:
    mode_label = portfolio.get("mode_label") or MODE_LABELS.get(portfolio.get("mode", ""), "组合")
    reason = (plan or {}).get("selection_reason") or portfolio.get("selection_reason") or ""
    reason_line = f"\n> **系统择优**：{reason}\n" if reason else ""
    alt = (plan or {}).get("alternate")
    alt_block = ""
    if alt:
        alt_block = f"""
> **备选方案**：{alt.get('mode_label', '—')} · {alt['leg_count']} 注 · 合计 {alt['total_stake']} 元（未锁定，供对照）
"""
    rows: list[str] = []
    for leg in portfolio["legs"]:
        pred_row = pred_idx.get(leg["match_no"])
        matchup = matchup_short(pred_row, leg["match_no"])
        role = {"primary": "主攻", "hedge": "防冷", "strike": "重注", "fill": "补位"}.get(
            leg.get("role", ""), "—"
        )
        rows.append(
            f"| **{leg['leg_id']}** | {matchup} | {leg['category']} | **{leg['pick_label']}** | "
            f"{leg['odds']} | **{leg['stake']} 元** | {leg['win_gross']} 元 | {ev_pct(leg['ev'])} | {role} |"
        )
    body = "\n".join(rows)
    mutex_lines = []
    for g in portfolio.get("mutex_groups") or []:
        mutex_lines.append(
            f"- **{g['match_no']}**：{', '.join(g['leg_ids'])} 同属一场，**最多中 1 注**"
        )
    mutex_md = "\n".join(mutex_lines) if mutex_lines else "- 各注独立单关，无串关。"
    return f"""## 0. 主推 · {mode_label}

> 合计 **{portfolio['total_stake']} 元** / 预算 {portfolio['budget']} 元 · **{portfolio['leg_count']}** 注独立单关 · 覆盖 **{portfolio['match_count']}** 场
{reason_line}{alt_block}
| 注 ID | 比赛 | 玩法 | 选择 | 赔率 | 金额 | 命中奖金 | EV | 角色 |
|---|---|---|---|---|---|---|---|---|
{body}

**互斥提示**

{mutex_md}

> 全部为**独立单关**（非串关）；底层按 **EV 加权**分配预算。
"""


def render_portfolio_action_md(portfolio: dict[str, Any], pred_idx: dict[str, dict]) -> str:
    rows: list[str] = []
    for leg in portfolio["legs"]:
        pred_row = pred_idx.get(leg["match_no"])
        home = pred_row.get("home_cn", leg.get("home_team", "?")) if pred_row else leg.get("home_team", "?")
        away = pred_row.get("away_cn", leg.get("away_team", "?")) if pred_row else leg.get("away_team", "?")
        rows.append(
            f"| **{leg['leg_id']}** | {leg['match_no']} {home}vs{away} | {leg['category']} | "
            f"**{leg['pick_label']}** | {leg['odds']} | **{leg['stake']} 元** |"
        )
    leg_ids = [l["leg_id"] for l in portfolio["legs"]]
    hook_header = " | ".join(leg_ids)
    hook_sep = "| " + " | ".join("---" for _ in leg_ids) + " |"
    hook_empty = "| " + " | ".join("" for _ in leg_ids) + " |"
    return f"""## 1. 行动卡 · 中国体彩格式（主推组合）

| 注 ID | 比赛 | 玩法 | 选择 | 赔率 | 金额 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

**合计投注：{portfolio['total_stake']} 元**

### 复盘 hook

| {hook_header} |
{hook_sep}
{hook_empty}
"""


def render_portfolio_html(
    portfolio: dict[str, Any],
    pred_idx: dict[str, dict],
    plan: dict[str, Any] | None = None,
) -> str:
    mode_label = portfolio.get("mode_label") or "组合单"
    reason = (plan or {}).get("selection_reason") or ""
    reason_html = f'<p class="hint">{reason}</p>' if reason else ""
    alt = (plan or {}).get("alternate")
    alt_html = ""
    if alt:
        alt_html = (
            f'<p class="hint">备选：{alt.get("mode_label", "—")} · '
            f'{alt["leg_count"]} 注 · {alt["total_stake"]} 元（对照，未锁定）</p>'
        )
    rows = ""
    for leg in portfolio["legs"]:
        pred_row = pred_idx.get(leg["match_no"])
        matchup = matchup_short(pred_row, leg["match_no"])
        role = {"primary": "主攻", "hedge": "防冷", "strike": "重注", "fill": "补位"}.get(
            leg.get("role", ""), "—"
        )
        rows += (
            f"<tr><td><b>{leg['leg_id']}</b></td><td>{matchup}</td>"
            f"<td>{leg['category']}</td><td><b>{leg['pick_label']}</b></td>"
            f"<td class=\"num\">{leg['odds']}</td><td class=\"num\"><b>{leg['stake']}</b> 元</td>"
            f"<td class=\"num\">{leg['win_gross']}</td><td>{role}</td></tr>"
        )
    mutex = ""
    for g in portfolio.get("mutex_groups") or []:
        mutex += f"<li><b>{g['match_no']}</b>：{', '.join(g['leg_ids'])} 最多中 1 注</li>"
    if not mutex:
        mutex = "<li>各注独立单关，无串关</li>"
    return f"""
<section class="portfolio-ticket" id="portfolio-ticket">
  <h2>🎯 主推 · {mode_label}</h2>
  {reason_html}{alt_html}
  <p class="hint">合计 <span class="num">{portfolio['total_stake']}</span> 元 / 预算 {portfolio['budget']} 元 · EV 加权分配</p>
  <table class="t portfolio-table">
    <thead><tr><th>注</th><th>比赛</th><th>玩法</th><th>选择</th><th>赔率</th><th>金额</th><th>命中奖</th><th>角色</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="warn" style="margin-top:12px;">
    <b>互斥提示</b><ul style="margin:8px 0 0;padding-left:18px;">{mutex}</ul>
  </div>
</section>
"""


def render_markdown(
    scan: dict[str, Any],
    hero: dict[str, Any],
    top6: list[dict],
    top3: list[dict],
    stake: int,
    budget: int,
    ts: str,
    workflow_md: str = "",
    strategy_gates: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
    pred_idx: dict[str, dict] | None = None,
    plan: dict[str, Any] | None = None,
) -> str:
    summary = scan["scan_summary"]
    meta = scan["meta"]
    win_amt = round(stake * hero["odds"], 2)
    miss_pct = 1 - hero["p_true"]
    dims = hero["dims"]
    top6_lines = "\n".join(
        f"| {r['rank']} | {r['scheme_id']} | {r['match_no']} {r['pick_label']} | {r['odds']} | {ev_pct(r['ev'])} | {r['composite_score']} | {r['status']} |"
        for r in top6
    )
    gates_md = render_strategy_gates_md(strategy_gates, budget)
    shrink_note = f"（缩量至 {budget} 元）" if (strategy_gates or {}).get("budget", {}).get("shrink_applied") else ""
    pred_idx = pred_idx or {}
    hero_pred = pred_idx.get(hero["match_no"])
    hero_match = matchup_short(hero_pred, hero["match_no"])
    portfolio_block = ""
    action_block = ""
    if portfolio:
        portfolio_block = render_portfolio_md(portfolio, pred_idx, plan) + f"""
---

## 0b. 单注参考（漏斗 S1 · 若只下一注）

| 项 | 值 |
|---|---|
| **scheme** | **{hero['scheme_id']}** |
| 比赛 | {hero_match} |
| 玩法 | {hero['pick_label']} |
| 赔率 | **{hero['odds']}** |
| 综合分 | **{hero['composite_score']}** |

"""
        action_block = render_portfolio_action_md(portfolio, pred_idx)
    else:
        portfolio_block = f"""## 0. 最终推荐 · 如果本期只下一注

| 项 | 值 |
|---|---|
| **scheme** | **{hero['scheme_id']}** |
| 比赛 | {hero_match} |
| 玩法 | {hero['pick_label']} |
| 赔率 | **{hero['odds']}** |
| p_true | {pct(hero['p_true'])}% |
| EV | **{ev_pct(hero['ev'])}** |
| 综合分 | **{hero['composite_score']}** |
| 建议金额 | **{stake} 元** |
| 命中奖金 | {win_amt} 元 |
| 未中亏损 | −{stake} 元 |

**四维理由**：EV {dims['ev_norm']:.0f} · 引擎 {dims['engine']:.0f} · 基本面 {dims['fundamentals']:.1f} · 独立性 {dims['independence']:.0f}

"""
        action_block = f"""## 1. 行动卡 · 主推单注

| 注 ID | 比赛 | 玩法 | 选择 | 赔率 | 金额 |
|---|---|---|---|---|---|
| **{hero['scheme_id']}** | {hero_match} | {hero.get('category', '—')} | **{hero['pick_label']}** | {hero['odds']} | **{stake} 元** |

**合计投注：{stake} 元**

### 结局（单注）

| 结局 | 概率 | 净收益 |
|---|---|---|
| 命中 | {pct(hero['p_true'])}% | **+{round(win_amt - stake, 2)} 元** |
| 未中 | {pct(miss_pct)}% | **−{stake} 元** |

---

## 4. 复盘 hook

| scheme | 实际比分 | 命中？ | 实际收益 |
|---|---|---|---|
| {hero['scheme_id']} | | | |
"""

    title_suffix = "双方案择优 · T-5-9" if portfolio else "6 进 1 · T-5-4"
    return f"""# 投注决策 · 期号 {meta['issue_no']}（{title_suffix}）

{workflow_md}
> 策略骨架：**A · 风险预算型**{shrink_note}
{gates_md}
> 数据快照：`{meta['odds_source']}`
> 预测引擎：`{meta['prediction_source']}`
> 扫描：`scan_candidates.py` · {summary['total_candidates']} 候选 / {summary['eligible_count']} 过闸
> 决策时间：{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}
> 数据验证：validation_run_id=待 promote 写入

---

{portfolio_block}
> 玩法扫描覆盖六类（不让球/让球/总进球/比分/半全场/串关）；{summary['rejected_below']} 注被 `reject_below` 砍掉。
{render_top3_section(top3, budget)}
---

## Top 6 漏斗（EV + 二次评估）

| # | scheme | 选项 | 赔率 | EV | 综合分 | 状态 |
|---|---|---|---|---|---|---|
{top6_lines}

---

{action_block}

---

## 2. 扫描与闸

| 指标 | 值 |
|---|---|
| 候选总数 | {summary['total_candidates']} |
| EV 过闸 | {summary['eligible_count']} |
| reject_below 砍掉 | {summary['rejected_below']} |
| 六类覆盖 | {', '.join(summary['by_category'].keys())} |

---

## 3. 风险提示

1. 长期负 EV 已知；本期最优 EV 约 {ev_pct(hero['ev'])}。
2. 主推由 **EV 加权** 在防御/进攻方案中自动择优；全部为独立单关（非串关）。
3. 本报告须经 `validate_gate.py --promote` 后方为正式交付。

---

> skill: football-betting-strategist v2.2 · {'T-5-9 portfolio-plan' if portfolio else 'T-5-4 funnel.hero'}
"""


def render_html(
    scan: dict[str, Any],
    hero: dict[str, Any],
    top6: list[dict],
    top3: list[dict],
    pred_row: dict,
    pred_idx: dict[str, dict],
    stake: int,
    budget: int,
    style: str,
    script: str,
    workflow_html: str = "",
    gate_run_id: str | None = None,
    strategy_gates: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> str:
    dims = hero["dims"]
    win_amt = round(stake * hero["odds"], 2)
    profit = round(win_amt - stake, 2)
    miss_w = round((1 - hero["p_true"]) * 100, 1)
    hit_w = round(hero["p_true"] * 100, 1)
    meta = scan["meta"]
    summary = scan["scan_summary"]
    day_code = meta.get("match_date_code") or str(meta.get("issue_no", ""))[:6] or "unknown"
    sid = hero["scheme_id"]
    top6_html = render_top6_rows(top6, sid)
    matchups = render_matchups_block(pred_idx, hero["match_no"])
    hero_title = matchup_line(pred_row, hero["match_no"])
    pick_line = f"{hero['pick_label']} @ <span class=\"num\">{hero['odds']}</span>"
    hero_forecast = render_hero_forecast_html(pred_row)
    summary_rows = collect_forecast_summary_rows(
        pred_idx, hero["match_no"], top6, top3
    )
    forecast_summary_html = render_forecast_summary_table_html(
        summary_rows, hero["match_no"]
    )
    forecast_section = ""
    if forecast_summary_html:
        forecast_section = f"""
<h2>📈 赛果概率预估<span class="hint">引擎五维 + xG · 基本面 Agent 8.7</span></h2>
{forecast_summary_html}
"""
    top3_html = render_top3_cards_html(
        top3, budget, hero.get("candidate_id"), pred_idx
    )
    top3_block = ""
    if top3_html:
        top3_block = f"""
<h2>Top 3 赢利方案（供选择）<span class="hint">按参考注额×赔率 · 命中毛奖金降序</span></h2>
<div class="top3-picks" id="top3-picks">
{top3_html}
</div>
"""

    gates_html = render_strategy_gates_html(strategy_gates, budget)
    shrink_label = "缩量" if (strategy_gates or {}).get("budget", {}).get("shrink_applied") else "风险预算"
    display_stake = portfolio["total_stake"] if portfolio else stake
    portfolio_html = render_portfolio_html(portfolio, pred_idx, plan) if portfolio else ""
    hero_eyebrow = "单注参考 · 漏斗 S1" if portfolio else "最终推荐 · 如果本期只下一注"
    page_title = f"{day_code} · {portfolio.get('mode_label', '组合')}" if portfolio else f"{day_code} · 6 进 1 主推"
    warn_block = gates_html or f"""<div class="warn">
  <b>⚠️ catastrophic 警戒 · 预算 {budget} 元</b>
  2606131 亏损触发警戒。本期由 <code>scan_candidates.py</code> 全量扫描 {summary['total_candidates']} 候选后 6 进 1。
  <small>主推 {sid} 与旧版 4 注组合不同；以漏斗数据为准。</small>
</div>"""

    body = f"""<div class="wrap">

<header class="h">
  <h1>🇨🇳 投注决策 · {page_title}</h1>
  <div class="sub">期号 {meta['issue_no']} · 扫描 {summary['total_candidates']} 候选 → Top6 → {'组合单 ' + str(portfolio['leg_count']) + ' 注' if portfolio else 'Top3 供选'}</div>
  <div class="meta">
    <div><b>骨架</b><br>A · {shrink_label}</div>
    <div><b>本期投注</b><br><span class="num">{display_stake} 元</span> / 预算 {budget} 元</div>
    <div><b>主推</b><br>{'组合 ' + str(portfolio['leg_count']) + ' 注' if portfolio else hero['scheme_id'] + ' · ' + hero['match_no']}</div>
    <div><b>决策时间</b><br>v2.2 · T-5-9 双方案</div>
  </div>
</header>
{workflow_html}
{warn_block}
{portfolio_html}

<div class="kpi">
  <div class="c gold"><div class="lab">主推 EV</div><div class="v num">{ev_pct(hero['ev'])}</div></div>
  <div class="c green"><div class="lab">p_true</div><div class="v num">{pct(hero['p_true'])}%</div></div>
  <div class="c red"><div class="lab">未中亏损</div><div class="v num">−{stake} 元</div></div>
  <div class="c grey"><div class="lab">综合分 Top1</div><div class="v num">{hero['composite_score']}</div></div>
</div>
{forecast_section}
<section class="hero-pick" id="hero-pick" data-scheme-id="{sid}" tabindex="0" aria-label="最终推荐">
  <div>
    <div class="eyebrow">{hero_eyebrow}</div>
    <div class="title">{hero_title}</div>
    <div class="pick-line">{pick_line}</div>
    {hero_forecast}
    <div class="meta-line">scheme <b>{sid}</b> · 引擎 Top1 同向 · scan funnel</div>
  </div>
  <div class="right">
    <div class="amt num" id="hero-amt">{stake}</div>
    <div class="amt-lab">建议金额（元）</div>
    <div class="score-val num" id="hero-score">{hero['composite_score']}</div>
    <div class="dim-bars" id="hero-dims">
      <div class="dim-row"><span>EV</span><div class="db"><i style="--w:{dims['ev_norm']}%"></i></div><span class="num">{dims['ev_norm']:.0f}</span></div>
      <div class="dim-row"><span>引擎</span><div class="db"><i style="--w:{dims['engine']}%"></i></div><span class="num">{dims['engine']:.0f}</span></div>
      <div class="dim-row"><span>基本面</span><div class="db"><i style="--w:{dims['fundamentals']}%"></i></div><span class="num">{dims['fundamentals']:.0f}</span></div>
      <div class="dim-row"><span>独立性</span><div class="db"><i style="--w:{max(dims['independence'],4)}%"></i></div><span class="num">{dims['independence']:.0f}</span></div>
    </div>
  </div>
</section>
{top3_block}
<p class="hero-ribbon" id="hero-ribbon" aria-live="polite">悬停 Top6 行可对比落选方案 · 点击 Top3 卡或 Top6 行联动主推区</p>

<h2>🏆 Top 6 漏斗</h2>
<div class="top6-wrap">
<table class="top6">
  <thead><tr><th>#</th><th>玩法</th><th>选项</th><th>EV</th><th>综合分</th><th>四维</th><th>状态</th></tr></thead>
  <tbody id="top6-body">
{top6_html}
  </tbody>
</table>
</div>
<p style="font-size:12px;color:var(--muted);margin:0 0 20px;">扫描 {summary['total_candidates']} 候选 · 过闸 {summary['eligible_count']} · EV 闸砍 {summary['rejected_below']}</p>

<h2>⚔️ 对阵基本面与预估赛果</h2>
<div class="matchups">{matchups}
</div>

<h2>📊 主推单注 · 结局条</h2>
<div class="ov">
  <div class="lab-row"><span>{hero['pick_label']} @ {hero['odds']} · {stake} 元</span><span class="num">100%</span></div>
  <div class="ov-bar">
    <div class="seg" style="width:{miss_w}%;background:#dc2626;color:#fff;">未中<small>−{stake} · {miss_w:.0f}%</small></div>
    <div class="seg" style="width:{hit_w}%;background:#22c55e;color:#fff;">命中<small>+{profit} · {hit_w:.0f}%</small></div>
  </div>
</div>

<div class="cut">
  <b>被砍统计</b> · reject_below 砍掉 {summary['rejected_below']} 注（总进球/比分/串关为主）
</div>

<footer>
  <span>football-betting-strategist v2.1 · T-6-7 Top3</span>
  <span class="sep">|</span>
  <span>数据：{meta['odds_source']}</span>
  <span class="sep">|</span>
  <span>预测：{meta['prediction_source']}</span>
  <br>
  <span class="validation-run">validation_run_id={gate_run_id or "PENDING"}</span>
  <br>
  <span style="margin-top:6px;display:inline-block;">本报告非投资建议；竞彩长期 EV 为负；金额自担。</span>
</footer>

</div>
<script>{script}</script>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投注决策 · {day_code} · 6进1主推</title>
<!-- {f"validation_run_id: {gate_run_id}" if gate_run_id else "validation_run_id: 待 promote"} -->
<style>{style}</style>
</head>
<body>
{body}
</body>
</html>"""


def render_decision_payload(
    scan: dict[str, Any],
    hero: dict[str, Any],
    top6: list[dict],
    top3: list[dict],
    stake: int,
    budget: int,
    ts: str,
    wf_steps: list[dict[str, Any]],
    wf_ts: str,
    strategy_gates: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
    pred_idx: dict[str, dict] | None = None,
    plan: dict[str, Any] | None = None,
    gate_run_id: str | None = None,
    template_path: Path | str | None = None,
) -> dict[str, Any]:
    meta = scan.get("meta") or {}
    return {
        "schema_version": "1.0",
        "artifact_type": "decision_draft",
        "generated_at": ts,
        "gate_run_id": gate_run_id,
        "match_date_code": meta.get("match_date_code"),
        "issue_no": meta.get("issue_no"),
        "budget": budget,
        "stake": stake,
        "scan_summary": scan.get("scan_summary"),
        "meta": meta,
        "hero": hero,
        "top6": top6,
        "top3": top3,
        "strategy_gates": strategy_gates,
        "portfolio": portfolio,
        "plan": plan,
        "prediction_index": pred_idx or {},
        "workflow": {"steps": wf_steps, "updated_at": wf_ts},
        "template_path": str(template_path) if template_path else None,
    }


def write_md_from_json(json_path: Path, md_path: Path) -> None:
    data = load_json(json_path)
    scan = {
        "meta": data.get("meta") or {},
        "scan_summary": data.get("scan_summary") or {},
    }
    wf = data.get("workflow") or {}
    workflow_md = render_workflow_pipeline_md(wf.get("steps") or [], wf.get("updated_at") or "")
    md_path.write_text(
        render_markdown(
            scan,
            data["hero"],
            data["top6"],
            data["top3"],
            int(data["stake"]),
            int(data["budget"]),
            data.get("generated_at", ""),
            workflow_md=workflow_md,
            strategy_gates=data.get("strategy_gates"),
            portfolio=data.get("portfolio"),
            pred_idx=data.get("prediction_index") or {},
            plan=data.get("plan"),
        ),
        encoding="utf-8",
    )


def write_html_from_json(
    json_path: Path,
    html_path: Path,
    template_path: Path | None = None,
) -> None:
    """从决策草案 JSON 派生 HTML（canonical JSON → 视图）。"""
    data = load_json(json_path)
    tpl_raw = template_path or data.get("template_path") or TEMPLATE
    tpl = resolve(str(tpl_raw))
    style, script = extract_style_script(tpl)
    scan = {
        "meta": data.get("meta") or {},
        "scan_summary": data.get("scan_summary") or {},
    }
    hero = data["hero"]
    pred_idx = data.get("prediction_index") or {}
    pred_row = pred_idx.get(hero["match_no"]) or {}
    wf = data.get("workflow") or {}
    workflow_html = render_workflow_pipeline_html(
        wf.get("steps") or [], wf.get("updated_at") or ""
    )
    html_path.write_text(
        render_html(
            scan,
            hero,
            data["top6"],
            data["top3"],
            pred_row,
            pred_idx,
            int(data["stake"]),
            int(data["budget"]),
            style,
            script,
            workflow_html=workflow_html,
            gate_run_id=data.get("gate_run_id"),
            strategy_gates=data.get("strategy_gates"),
            portfolio=data.get("portfolio"),
            plan=data.get("plan"),
        ),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="从 scan 漏斗生成决策草案")
    ap.add_argument("--scan", required=True)
    ap.add_argument("--prediction", required=True)
    ap.add_argument("--template", default=str(TEMPLATE))
    ap.add_argument("--prefix", required=True, help="输出文件名前缀（无扩展名）")
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--out-dir", default="validation/drafts")
    ap.add_argument("--stamp", help="固定时间戳（phase3 重生成用）")
    ap.add_argument("--gate-run-id", help="门禁 run_id（工作流 3.3 状态）")
    ap.add_argument("--promoted", action="store_true", help="已 promote 正式报告")
    from artifact_lib import add_emit_md_arg  # noqa: WPS433

    add_emit_md_arg(ap)
    args = ap.parse_args()

    scan = load_json(resolve(args.scan))
    prediction = load_json(resolve(args.prediction))
    hero = scan["funnel"]["hero"]
    if not hero:
        print("[!] funnel.hero 为空 → 合法空单，不生成主推草案", file=__import__("sys").stderr)
        return 1

    top6 = scan["funnel"]["top6"]
    top3 = scan["funnel"].get("top3") or []
    candidates = scan.get("candidates") or []
    strategy_gates = scan.get("strategy_gates")
    hero_cand = candidate_by_id(candidates, hero.get("candidate_id"))
    stake = stake_with_caps(hero_stake(args.budget), hero_cand)

    plan = select_portfolio_plan(scan, prediction, args.budget, strategy_gates=strategy_gates)
    portfolio = plan["primary"] if plan else None
    if portfolio:
        apply_portfolio_stake_caps(portfolio, candidates, args.budget)
        if plan.get("alternate"):
            apply_portfolio_stake_caps(plan["alternate"], candidates, args.budget)

    ts = args.stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{args.prefix}_{ts}"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"
    html_path = out_dir / f"{base}.html"

    meta = scan.get("meta") or {}
    day_code = meta.get("match_date_code") or str(meta.get("issue_no", ""))[:6] or "unknown"
    prefix_match = re.match(r"decision_(\d{6})_", args.prefix)
    workflow_day = prefix_match.group(1) if prefix_match else day_code
    wf_steps, wf_ts = steps_from_state_or_infer(
        workflow_day,
        scan=scan,
        scan_path=resolve(args.scan),
        draft_json_path=json_path,
        draft_html_path=html_path,
        gate_run_id=args.gate_run_id,
        promoted=args.promoted,
        prefer_state=bool(args.gate_run_id),
    )

    pred_idx = pred_index(prediction)
    tpl_path = resolve(args.template)
    payload = render_decision_payload(
        scan,
        hero,
        top6,
        top3,
        stake,
        args.budget,
        ts,
        wf_steps,
        wf_ts,
        strategy_gates=strategy_gates,
        portfolio=portfolio,
        pred_idx=pred_idx,
        plan=plan,
        gate_run_id=args.gate_run_id,
        template_path=tpl_path,
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html_from_json(json_path, html_path, template_path=tpl_path)
    if args.emit_md:
        write_md_from_json(json_path, md_path)
    print(f"[OK] {json_path}")
    if args.emit_md:
        print(f"[OK] {md_path}")
    print(f"[OK] {html_path}")
    if portfolio and plan:
        print(f"  主推 {portfolio.get('mode_label')}: {portfolio['leg_count']} 注 · 合计 {portfolio['total_stake']} 元")
        print(f"    择优: {plan.get('selection_reason', '')}")
        for leg in portfolio["legs"]:
            print(f"    {leg['leg_id']}: {leg['match_no']} {leg['pick_label']} @ {leg['odds']} · {leg['stake']} 元")
        alt = plan.get("alternate")
        if alt:
            print(f"  备选 {alt.get('mode_label')}: {alt['leg_count']} 注 · {alt['total_stake']} 元")
    else:
        print(f"  主推 {hero['scheme_id']}: {hero['pick_label']} @ {hero['odds']} · {stake} 元")
    for row in top3:
        print(
            f"  Top3 {row['pick_label_user']}: {row['pick_label']} · "
            f"命中奖 {row['win_gross']} 元（参考 {row['ref_stake']} 元）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
