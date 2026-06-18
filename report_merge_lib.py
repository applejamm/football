"""合并预测 + 决策 HTML 为单份人类可读报告（工作流 promote 最后一步）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)

MERGE_NAV_STYLE = """
.report-shell{max-width:1080px;margin:0 auto;padding:28px 22px 60px;}
.report-top{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #2c3a55;border-radius:14px;padding:22px 24px;margin-bottom:22px;}
.report-top h1{margin:0 0 8px;font-size:24px;font-weight:700;color:#e2e8f0;}
.report-top .sub{color:#94a3b8;font-size:13px;}
.report-nav{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;}
.report-nav a{color:#60a5fa;text-decoration:none;font-size:13px;font-weight:600;padding:6px 14px;border:1px solid rgba(96,165,250,.35);border-radius:999px;background:rgba(96,165,250,.08);}
.report-nav a:hover{background:rgba(96,165,250,.18);}
.report-part{margin-bottom:36px;}
.report-part-title{font-size:18px;color:#60a5fa;margin:0 0 16px;padding-bottom:8px;border-bottom:1px solid #2c3a55;}
.report-prediction .wrap{max-width:none;padding:0;margin:0;}
.report-prediction h1{display:none;}
.report-prediction .meta{margin-bottom:16px;}
.report-decision .wrap{max-width:none;padding:0;margin:0;}
.report-decision header.h{margin-top:0;}
.report-footer{margin-top:28px;padding-top:16px;border-top:1px solid #2c3a55;font-size:12px;color:#64748b;}
"""


def extract_body(html: str) -> str:
    match = BODY_RE.search(html)
    return match.group(1).strip() if match else html.strip()


def extract_styles(html: str) -> str:
    return "\n".join(STYLE_RE.findall(html))


def strip_outer_wrap(body: str) -> str:
    """去掉最外层 .wrap，避免合并后双层容器。"""
    wrapped = re.match(
        r'^\s*<div class="wrap"[^>]*>(.*)</div>\s*$',
        body,
        re.DOTALL,
    )
    if wrapped:
        return wrapped.group(1).strip()
    return body


def report_filename_from_decision_json(decision_json: Path) -> str:
    """decision_260619_workflow_<ts>.json → report_260619_workflow_<ts>.html"""
    return decision_json.name.replace("decision_", "report_", 1).replace(".json", ".html")


def merge_report_html(
    prediction_html: str,
    decision_html: str,
    *,
    day_code: str,
    run_id: str,
    generated_at: str = "",
) -> str:
    pred_body = strip_outer_wrap(extract_body(prediction_html))
    dec_body = strip_outer_wrap(extract_body(decision_html))
    pred_styles = extract_styles(prediction_html)
    dec_styles = extract_styles(decision_html)
    ts_line = f"生成 {generated_at} · " if generated_at else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>本期报告 · {day_code}</title>
<!-- validation_run_id: {run_id} -->
<style>
{pred_styles}
{dec_styles}
{MERGE_NAV_STYLE}
</style>
</head>
<body>
<div class="report-shell">
  <header class="report-top">
    <h1>本期完整报告 · {day_code}</h1>
    <div class="sub">{ts_line}预测 + 投注决策 · validation_run_id={run_id}</div>
    <nav class="report-nav" aria-label="报告导航">
      <a href="#section-prediction">一、赛事预测</a>
      <a href="#section-decision">二、投注决策</a>
    </nav>
  </header>
  <section id="section-prediction" class="report-part report-prediction">
    <h2 class="report-part-title">一、赛事预测</h2>
    {pred_body}
  </section>
  <section id="section-decision" class="report-part report-decision">
    <h2 class="report-part-title">二、投注决策</h2>
    {dec_body}
  </section>
  <footer class="report-footer">
    体彩足球 Agent 工作流 · 本报告非投资建议；竞彩长期 EV 为负；金额自担。
  </footer>
</div>
</body>
</html>"""


def write_merged_report(
    prediction_json: Path,
    decision_json: Path,
    out_path: Path,
    *,
    run_id: str,
    stamp_html: Any | None = None,
) -> Path:
    """从 prediction / decision JSON 各派生 HTML 片段，合并写入 out_path。"""
    from generate_decision_draft import write_html_from_json as write_decision_html  # noqa: WPS433
    from predict_engine import write_html_from_json as write_prediction_html  # noqa: WPS433

    if stamp_html is None:
        from validation_lib import stamp_decision_html  # noqa: WPS433

        stamp_html = stamp_decision_html

    tmp_pred = out_path.parent / f"_merge_pred_{decision_json.stem}.html"
    tmp_dec = out_path.parent / f"_merge_dec_{decision_json.stem}.html"
    try:
        write_prediction_html(prediction_json, tmp_pred)
        write_decision_html(decision_json, tmp_dec)
        decision_data = json.loads(decision_json.read_text(encoding="utf-8"))
        pred_data = json.loads(prediction_json.read_text(encoding="utf-8"))
        day_code = (
            decision_data.get("match_date_code")
            or (decision_data.get("meta") or {}).get("match_date_code")
            or "?"
        )
        generated_at = (pred_data.get("meta") or {}).get("generated_at") or decision_data.get(
            "generated_at", ""
        )
        merged = merge_report_html(
            tmp_pred.read_text(encoding="utf-8"),
            tmp_dec.read_text(encoding="utf-8"),
            day_code=str(day_code),
            run_id=run_id,
            generated_at=generated_at,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(stamp_html(merged, run_id), encoding="utf-8")
    finally:
        for tmp in (tmp_pred, tmp_dec):
            if tmp.exists():
                tmp.unlink()
    return out_path
