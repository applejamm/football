"""预估赛果格式化（基本面分析 + 决策报告共用）。"""

from __future__ import annotations

from typing import Any


def pct(n: float, digits: int = 1) -> str:
    return f"{n * 100:.{digits}f}"


def top_entries(probs: dict[str, float], n: int = 5) -> list[tuple[str, float]]:
    return sorted(probs.items(), key=lambda x: x[1], reverse=True)[:n]


def pick_forecast_score(top_scorelines: dict[str, float] | None) -> tuple[str, float]:
    if not top_scorelines:
        return "—", 0.0
    score, prob = max(top_scorelines.items(), key=lambda x: x[1])
    return score, float(prob)


def pick_forecast_total_goals(total_goals_probs: dict[str, float] | None) -> tuple[str, float]:
    if not total_goals_probs:
        return "—", 0.0
    key, prob = max(total_goals_probs.items(), key=lambda x: x[1])
    label = f"{key}球" if key != "7+" else "7+球"
    return label, float(prob)


def primary_scheme(schemes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not schemes:
        return None
    for s in schemes:
        if s.get("score") and s["score"] != "—":
            return s
    return schemes[0]


def forecast_summary(prediction: dict[str, Any]) -> dict[str, Any]:
    schemes = prediction.get("schemes") or []
    scheme = primary_scheme(schemes) or {}
    score, score_p = pick_forecast_score(prediction.get("top_scorelines"))
    tg_label, tg_p = pick_forecast_total_goals(prediction.get("total_goals_probs"))
    op = prediction.get("outcome_probs") or {}
    wdl = scheme.get("wdl") or max(op, key=op.get)
    return {
        "wdl": wdl,
        "wdl_prob": float(op.get(wdl, 0)),
        "total_goals": scheme.get("total_goals") or tg_label.replace("球", "").replace("+", "+"),
        "total_goals_prob": tg_p,
        "score": scheme.get("score") if scheme.get("score") != "—" else score,
        "score_prob": score_p if scheme.get("score") == "—" else scheme.get("combined_prob", score_p),
        "expected_goals": prediction.get("expected_goals") or {},
        "top_scorelines": top_entries(prediction.get("top_scorelines") or {}, 5),
        "top_total_goals": top_entries(prediction.get("total_goals_probs") or {}, 5),
        "schemes": schemes[:3],
    }


def render_forecast_markdown_blocks(fc: dict[str, Any], match_no: str = "") -> list[str]:
    """从已落盘的 forecast 字段生成 8.7 节 markdown。"""
    eg = fc.get("expected_goals") or {}
    title = "### 8.7 预估赛果（引擎 · 基本面 + 市场 + xG）"
    if match_no:
        title += f" · {match_no}"
    lines = [
        title,
        "",
        "| 项 | 预估 | 概率 |",
        "|---|---|---|",
        f"| **胜平负** | **{fc['wdl']}** | {pct(fc['wdl_prob'])}% |",
        f"| **总进球数** | **{fc['total_goals']}** | {pct(fc['total_goals_prob'])}% |",
        f"| **比分** | **{fc['score']}** | {pct(float(fc['score_prob']))}% |",
        f"| 预期进球 xG | 主 {eg.get('home', '—')} · 客 {eg.get('away', '—')} | — |",
        "",
        "**最热比分 Top5**",
        "",
        "| 比分 | 概率 |",
        "|---|---|",
    ]
    for sc, pr in fc.get("top_scorelines") or []:
        lines.append(f"| {sc} | {pct(pr)}% |")
    lines.extend(["", "**总进球分布 Top5**", "", "| 进球数 | 概率 |", "|---|---|"])
    for item in fc.get("top_total_goals") or []:
        if isinstance(item, (list, tuple)):
            k, pr = item[0], item[1]
        else:
            continue
        lab = f"{k}球" if k != "7+" else "7+球"
        lines.append(f"| {lab} | {pct(pr)}% |")
    schemes = fc.get("schemes") or []
    if schemes:
        lines.extend(["", "**组合方案 Top3**", ""])
        for s in schemes:
            lines.append(
                f"- {s['id']}: {s['wdl']} / 总进球 {s['total_goals']} / 比分 {s['score']} "
                f"（{pct(s['combined_prob'])}%）"
            )
    lines.append("")
    lines.append("> 预估由五维引擎 + xG 泊松生成，仅供分析，不构成投注建议。")
    lines.append("")
    return lines


def render_forecast_markdown(pred_row: dict[str, Any]) -> list[str]:
    p = pred_row["prediction"]
    fc = forecast_summary(p)
    fc_serializable = {
        **fc,
        "top_scorelines": list(fc["top_scorelines"]),
        "top_total_goals": list(fc["top_total_goals"]),
    }
    return render_forecast_markdown_blocks(fc_serializable, pred_row.get("match_no", ""))


def render_forecast_inner_html(pred_row: dict[str, Any]) -> str:
    fc = forecast_summary(pred_row["prediction"])
    eg = fc["expected_goals"]
    score_rows = "".join(
        f"<tr><td>{sc}</td><td class=\"num\">{pct(pr)}%</td></tr>"
        for sc, pr in fc["top_scorelines"]
    )
    tg_rows = "".join(
        f"<tr><td>{(k + '球' if k != '7+' else '7+球')}</td><td class=\"num\">{pct(pr)}%</td></tr>"
        for k, pr in fc["top_total_goals"]
    )
    return f"""
    <div class="forecast-block">
      <div class="forecast-hero">
        <span class="fc-lab">预估赛果</span>
        <span class="fc-val">胜平负 <b>{fc['wdl']}</b> ({pct(fc['wdl_prob'])}%)</span>
        <span class="fc-sep">·</span>
        <span class="fc-val">总进球 <b>{fc['total_goals']}</b> ({pct(fc['total_goals_prob'])}%)</span>
        <span class="fc-sep">·</span>
        <span class="fc-val">比分 <b>{fc['score']}</b> ({pct(float(fc['score_prob']))}%)</span>
        <span class="fc-xg num">xG {eg.get('home', '—')} : {eg.get('away', '—')}</span>
      </div>
      <div class="forecast-grid">
        <div class="forecast-col">
          <div class="cmp-label">最热比分 Top5</div>
          <table class="fc-t"><tbody>{score_rows}</tbody></table>
        </div>
        <div class="forecast-col">
          <div class="cmp-label">总进球分布 Top5</div>
          <table class="fc-t"><tbody>{tg_rows}</tbody></table>
        </div>
      </div>
    </div>"""


def collect_forecast_summary_rows(
    pred_idx: dict[str, dict],
    hero_match_no: str,
    top6: list[dict],
    top3: list[dict],
) -> list[dict]:
    """汇总报告需展示的场次：基本面已匹配 + 漏斗涉及场次。"""
    match_nos: set[str] = {hero_match_no}
    for row in top6:
        match_nos.add(row["match_no"])
    for row in top3:
        match_nos.add(row["match_no"])
    for r in pred_idx.values():
        if r.get("fundamentals_matched"):
            match_nos.add(r["match_no"])
    return [pred_idx[m] for m in sorted(match_nos) if m in pred_idx]


def render_hero_forecast_html(pred_row: dict[str, Any]) -> str:
    fc = forecast_summary(pred_row["prediction"])
    op = pred_row["prediction"]["outcome_probs"]
    eg = fc["expected_goals"]
    return f"""<div class="hero-forecast" id="hero-forecast">
  <span class="hf-lab">引擎赛果预估</span>
  <span class="hf-wdl">
    <span class="w">胜 {pct(op['胜'])}%</span>
    <span class="d">平 {pct(op['平'])}%</span>
    <span class="l">负 {pct(op['负'])}%</span>
  </span>
  <span class="hf-sep">·</span>
  <span>比分 <b>{fc['score']}</b> ({pct(float(fc['score_prob']))}%)</span>
  <span class="hf-sep">·</span>
  <span>总进球 <b>{fc['total_goals']}</b></span>
  <span class="hf-sep">·</span>
  <span class="hf-xg num">xG {eg.get('home', '—')}:{eg.get('away', '—')}</span>
</div>"""


def render_card_forecast_snippet(pred_row: dict[str, Any] | None) -> str:
    if not pred_row:
        return ""
    op = pred_row["prediction"]["outcome_probs"]
    fc = forecast_summary(pred_row["prediction"])
    return (
        f'<div class="card-forecast">引擎 '
        f'<span class="w">胜{pct(op["胜"])}%</span> '
        f'<span class="d">平{pct(op["平"])}%</span> '
        f'<span class="l">负{pct(op["负"])}%</span> · 比分 {fc["score"]}</div>'
    )


def render_forecast_summary_table_html(
    rows: list[dict[str, Any]],
    hero_match_no: str,
) -> str:
    if not rows:
        return ""
    trs: list[str] = []
    for r in rows:
        mno = r["match_no"]
        row_cls = " class=\"is-hero-row\"" if mno == hero_match_no else ""
        op = r["prediction"]["outcome_probs"]
        fc = forecast_summary(r["prediction"])
        eg = fc["expected_goals"]
        trs.append(
            f"<tr{row_cls}>"
            f"<td class=\"num\">{mno}</td>"
            f"<td>{r['home_cn']} vs {r['away_cn']}</td>"
            f"<td class=\"num w-col\">{pct(op['胜'])}%</td>"
            f"<td class=\"num d-col\">{pct(op['平'])}%</td>"
            f"<td class=\"num l-col\">{pct(op['负'])}%</td>"
            f"<td class=\"num\"><b>{fc['score']}</b> <small>({pct(float(fc['score_prob']))}%)</small></td>"
            f"<td class=\"num\"><b>{fc['total_goals']}</b></td>"
            f"<td class=\"num\">{eg.get('home', '—')}:{eg.get('away', '—')}</td>"
            f"</tr>"
        )
    body = "\n".join(trs)
    return f"""
<div class="forecast-summary" id="forecast-summary">
<table class="fs-table">
  <thead>
    <tr>
      <th>场次</th><th>对阵</th>
      <th class="w-col">胜</th><th class="d-col">平</th><th class="l-col">负</th>
      <th>预估比分</th><th>总进球</th><th>xG</th>
    </tr>
  </thead>
  <tbody>
{body}
  </tbody>
</table>
<p class="fs-note">胜平负为五维引擎概率；比分/总进球来自 xG 泊松 · 高亮行为本期主推场次</p>
</div>"""


def day_to_calendar(day: str) -> str:
    if len(day) == 6 and day.isdigit():
        return f"20{day}"
    return day
