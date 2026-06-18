#!/usr/bin/env python3
"""
PRD 预测引擎 CLI：五维权重 → 3–5 套组合方案 → JSON 落盘（默认不写独立 HTML；promote 时并入 report_*.html）。

用法：
    python3 predict_engine.py --day 260614
    python3 predict_engine.py --odds odds_260614_*.json --fundamentals fundamentals_*.json
    python3 predict_engine.py --day 260614 --match 周日009
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

from forecast_lib import render_forecast_markdown
from predict_lib import (
    cn_to_en,
    extract_cn_1x2_odds,
    find_fundamentals_record,
    predict_match,
)

from artifact_lib import (
    SNAPSHOT_PREDICTION_DIR,
    fundamentals_search_dirs,
    latest_in_dirs,
    odds_search_dirs,
    rel_snapshot,
)

DEFAULT_DIR = SNAPSHOT_PREDICTION_DIR


def find_latest(pattern: str, dirs: list[Path] | None = None) -> Path | None:
    if dirs is None:
        dirs = [SNAPSHOT_PREDICTION_DIR, Path(__file__).resolve().parent]
    return latest_in_dirs(pattern, dirs)


def render_markdown(results: list[dict], meta: dict) -> str:
    lines = [
        f"# 赛事预测 · {meta.get('match_date_code', '?')}",
        "",
        f"- 生成时间：{meta.get('generated_at')}",
        f"- 数据源：{meta.get('odds_source', '?')} + {meta.get('fundamentals_source', '无')}",
        f"- 权重配置：`weights.yaml`",
        "",
        "---",
        "",
    ]
    for r in results:
        lines.append(f"## {r['match_no']} {r['home_cn']} vs {r['away_cn']}")
        lines.append("")
        lines.append(f"**综合主队优势** {r['prediction']['composite']['composite_home']}/100")
        lines.append("")
        lines.append("### 五维得分")
        lines.append("")
        lines.append("| 维度 | 得分 | 可用 | 说明 |")
        lines.append("|---|---|---|---|")
        labels = {
            "strength": "硬实力 30%",
            "personnel": "人员 25%",
            "tournament": "大赛 20%",
            "h2h": "H2H 15%",
            "market": "市场 10%",
        }
        for k, label in labels.items():
            d = r["prediction"]["dimensions"][k]
            av = "✅" if d.get("available") else "暂无"
            lines.append(f"| {label} | {d.get('score', '—')} | {av} | {d.get('detail', '')} |")
        lines.append("")
        op = r["prediction"]["outcome_probs"]
        lines.append(f"**胜平负概率**：胜 {op['胜']:.1%} / 平 {op['平']:.1%} / 负 {op['负']:.1%}")
        eg = r["prediction"]["expected_goals"]
        lines.append(f"**预期进球**：主 {eg['home']} · 客 {eg['away']}")
        lines.append("")
        if r["prediction"].get("scenario_flags"):
            lines.append("**异常场景**：" + "；".join(r["prediction"]["scenario_flags"]))
            lines.append("")
        lines.extend(render_forecast_markdown(r))
        lines.append("### 组合方案（3–5 套）")
        lines.append("")
        for s in r["prediction"]["schemes"]:
            lines.append(f"#### {s['id']} · 综合概率 {s['combined_prob']:.1%}")
            lines.append(f"- 胜平负：**{s['wdl']}**")
            lines.append(f"- 总进球：**{s['total_goals']}**")
            lines.append(f"- 比分：**{s['score']}**")
            lines.append(f"- 逻辑：{s['logic']}")
            lines.append("")
        lines.append("---")
        lines.append("")
    lines.append("> 本报告由 PRD 五维权重引擎 v1 自动生成，不构成投注建议。")
    return "\n".join(lines)


HTML_TMPL = Template(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>赛事预测 · ${code}</title>
<style>
  body{font-family:-apple-system,"PingFang SC",sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;line-height:1.55}
  .wrap{max-width:960px;margin:0 auto}
  h1{font-size:22px;margin-bottom:8px}
  .meta{color:#94a3b8;font-size:13px;margin-bottom:24px}
  .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px;margin-bottom:18px}
  .card h2{font-size:17px;margin:0 0 12px}
  table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}
  th,td{border:1px solid #334155;padding:8px 10px;text-align:left}
  th{background:#0f172a;color:#94a3b8}
  .scheme{border-left:3px solid #38bdf8;padding-left:12px;margin:14px 0}
  .scheme .id{font-weight:700;color:#38bdf8}
  .prob{font-variant-numeric:tabular-nums;color:#4ade80}
  footer{margin-top:24px;font-size:12px;color:#64748b}
</style>
</head>
<body><div class="wrap">
<h1>赛事预测 · ${code}</h1>
<div class="meta">生成 ${generated_at} · ${match_count} 场 · weights.yaml v1</div>
${cards}
<footer>PRD 五维权重预测引擎 v1 · 仅供体彩店赛事分析参考</footer>
</div></body></html>
""")


def render_html(results: list[dict], meta: dict) -> str:
    cards = []
    for r in results:
        dims_rows = ""
        labels = {"strength": "硬实力", "personnel": "人员", "tournament": "大赛", "h2h": "H2H", "market": "市场"}
        for k, lb in labels.items():
            d = r["prediction"]["dimensions"][k]
            av = "有" if d.get("available") else "暂无"
            dims_rows += f"<tr><td>{lb}</td><td>{d.get('score','—')}</td><td>{av}</td><td>{d.get('detail','')}</td></tr>"
        schemes_html = ""
        for s in r["prediction"]["schemes"]:
            schemes_html += f"""<div class="scheme">
              <div class="id">{s['id']} · <span class="prob">{s['combined_prob']:.1%}</span></div>
              <div>胜平负 {s['wdl']} · 总进球 {s['total_goals']} · 比分 {s['score']}</div>
              <div style="font-size:12px;color:#94a3b8;margin-top:4px">{s['logic']}</div>
            </div>"""
        op = r["prediction"]["outcome_probs"]
        cards.append(f"""<div class="card">
          <h2>{r['match_no']} {r['home_cn']} vs {r['away_cn']}</h2>
          <div>综合主队优势 <strong>{r['prediction']['composite']['composite_home']}</strong>/100</div>
          <table><tr><th>维度</th><th>得分</th><th>数据</th><th>说明</th></tr>{dims_rows}</table>
          <div>胜平负：胜 {op['胜']:.1%} / 平 {op['平']:.1%} / 负 {op['负']:.1%}</div>
          {schemes_html}
        </div>""")
    return HTML_TMPL.substitute(
        code=meta.get("match_date_code", "?"),
        generated_at=meta.get("generated_at", ""),
        match_count=len(results),
        cards="\n".join(cards),
    )


def write_html_from_json(json_path: Path, html_path: Path) -> None:
    """从 prediction JSON 派生 HTML。"""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    html_path.write_text(
        render_html(payload["predictions"], payload["meta"]),
        encoding="utf-8",
    )


def run_predictions(
    odds_data: dict,
    fundamentals_data: dict | None,
    match_filter: str | None = None,
) -> list[dict]:
    records = (fundamentals_data or {}).get("records") or []
    ref_date = (fundamentals_data or {}).get("meta", {}).get("date", "")
    if ref_date and len(ref_date) == 8:
        ref_date = f"{ref_date[:4]}-{ref_date[4:6]}-{ref_date[6:8]}"
    results: list[dict] = []
    for m in odds_data.get("matches", []):
        mno = m.get("match_no", "")
        if match_filter and match_filter not in mno:
            continue
        home_cn = m.get("home_team", "")
        away_cn = m.get("away_team", "")
        rec = find_fundamentals_record(records, home_cn, away_cn)
        features: dict[str, Any] = {}
        home_en, away_en = home_cn, away_cn
        if rec:
            features = rec.get("features", {})
            home_en = rec["event"].get("home", cn_to_en(home_cn))
            away_en = rec["event"].get("away", cn_to_en(away_cn))
        cn_odds = extract_cn_1x2_odds(m)
        pred = predict_match(home_en, away_en, features, cn_odds, ref_date or None)
        results.append({
            "match_no": mno,
            "home_cn": home_cn,
            "away_cn": away_cn,
            "home_en": home_en,
            "away_en": away_en,
            "fundamentals_matched": rec is not None,
            "prediction": pred,
        })
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--day", help="比赛日 code，如 260614")
    p.add_argument("--odds", help="odds JSON 路径")
    p.add_argument("--fundamentals", help="fundamentals JSON 路径")
    p.add_argument("--match", help="只预测指定场次，如 周日009")
    p.add_argument("--dir", default=str(DEFAULT_DIR))
    p.add_argument("--stdout", action="store_true", help="JSON 输出到 stdout")
    from artifact_lib import add_emit_html_arg, add_emit_md_arg  # noqa: WPS433

    add_emit_md_arg(p)
    add_emit_html_arg(p)
    args = p.parse_args(argv)

    base = Path(args.dir)
    if args.odds:
        odds_path = Path(args.odds)
    elif args.day:
        odds_path = (
            find_latest("odds_window_24h_*.json", odds_search_dirs())
            or find_latest(f"odds_{args.day}_*.json", odds_search_dirs())
        )
    else:
        odds_path = find_latest("odds_*.json", odds_search_dirs())
    if not odds_path or not odds_path.exists():
        print("[!] 找不到 odds 文件，先跑 fetch_odds.py", file=sys.stderr)
        return 1

    if args.fundamentals:
        fund_path = Path(args.fundamentals)
    elif args.day:
        fund_path = (
            find_latest(f"fundamentals_*_{args.day[:6]}*.json", fundamentals_search_dirs())
            or find_latest("fundamentals_*.json", fundamentals_search_dirs())
        )
    else:
        fund_path = find_latest("fundamentals_*.json", fundamentals_search_dirs())

    odds_data = json.loads(odds_path.read_text("utf-8"))
    fundamentals_data = None
    if fund_path and fund_path.exists():
        fundamentals_data = json.loads(fund_path.read_text("utf-8"))
        print(f"[*] 基本面 {fund_path.name}", file=sys.stderr)
    else:
        print("[*] 无基本面快照，市场维度仍可用", file=sys.stderr)

    results = run_predictions(odds_data, fundamentals_data, args.match)
    if not results:
        print("[!] 无匹配比赛", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    code = args.day or odds_data.get("match_date_code") or "unknown"
    meta = {
        "schema_version": "1.0",
        "match_date_code": code,
        "odds_window_hours": odds_data.get("window_hours"),
        "match_days_included": odds_data.get("match_days_included"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "odds_source": rel_snapshot(odds_path),
        "fundamentals_source": rel_snapshot(fund_path) if fund_path and fund_path.exists() else None,
        "match_count": len(results),
    }
    payload = {"meta": meta, "predictions": results}
    json_out = base / f"prediction_{code}_{stamp}.json"
    md_out = base / f"prediction_{code}_{stamp}.md"
    html_out = base / f"prediction_{code}_{stamp}.html"

    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    print(f"[OK] {json_out.name}", file=sys.stderr)
    if args.emit_html:
        write_html_from_json(json_out, html_out)
        print(f"[OK] {html_out.name}", file=sys.stderr)
    if args.emit_md:
        md_out.write_text(render_markdown(results, meta), "utf-8")
        print(f"[OK] {md_out.name}", file=sys.stderr)
    for r in results:
        comp = r["prediction"]["composite"]["composite_home"]
        top = r["prediction"]["schemes"][0] if r["prediction"]["schemes"] else {}
        print(
            f"  {r['match_no']} {r['home_cn']} vs {r['away_cn']}  composite={comp}  top={top.get('id')} {top.get('wdl')}/{top.get('score')}",
            file=sys.stderr,
        )
    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
