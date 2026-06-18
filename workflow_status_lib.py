"""PM 工作流步骤状态：记录、推断与报告渲染。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from artifact_lib import resolve_snapshot

ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "validation" / "workflow"
RUNS_DIR = ROOT / "validation" / "runs"
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}$")

STEP_DEFS: list[tuple[str, str, str]] = [
    ("1.1", "采集体彩赔率", "fetch_odds"),
    ("1.2", "采集球队基本面（ESPN）", "fetch_fundamentals"),
    ("1.3", "基本面 enrich · 8.7 预估赛果", "enrich_forecast"),
    ("1.4", "阶段1 输入校验", "phase1_validate"),
    ("2.1", "五维预测引擎", "predict_engine"),
    ("2.2", "预测档数据门禁", "gate_prediction"),
    ("3.1", "全玩法候选扫描", "scan_candidates"),
    ("3.2", "决策草案 MD/HTML", "generate_draft"),
    ("3.3", "决策档门禁 · promote", "gate_decision"),
]


def make_step(
    step_id: str,
    name: str,
    ok: bool,
    detail: str = "",
    key: str = "",
) -> dict[str, Any]:
    return {
        "id": step_id,
        "name": name,
        "key": key,
        "status": "PASS" if ok else "FAIL",
        "detail": detail,
    }


def load_workflow_state(day: str) -> dict[str, Any] | None:
    path = WORKFLOW_DIR / f"{day}_state.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def merge_steps_into_state(day: str, new_steps: list[dict[str, Any]]) -> None:
    state = load_workflow_state(day) or {"day": day}
    existing = {s["key"]: s for s in state.get("workflow_steps") or [] if s.get("key")}
    for s in new_steps:
        if s.get("key"):
            existing[s["key"]] = s
    order = {d[2]: i for i, d in enumerate(STEP_DEFS)}
    state["workflow_steps"] = sorted(
        existing.values(),
        key=lambda s: order.get(s.get("key", ""), 99),
    )
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    (WORKFLOW_DIR / f"{day}_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_gate_overall(run_id: str | None) -> tuple[str, str]:
    if not run_id:
        return "SKIP", "未执行"
    checks_path = RUNS_DIR / run_id / "checks.json"
    if not checks_path.is_file():
        return "SKIP", "无 checks.json"
    data = json.loads(checks_path.read_text(encoding="utf-8"))
    overall = data.get("overall", "FAIL")
    return overall, f"run_id={run_id}"


def infer_workflow_steps(
    day: str,
    odds_path: Path | None = None,
    fund_path: Path | None = None,
    pred_path: Path | None = None,
    scan_path: Path | None = None,
    draft_json: Path | None = None,
    draft_md: Path | None = None,
    draft_html: Path | None = None,
    gate_run_id: str | None = None,
    promoted: bool = False,
) -> list[dict[str, Any]]:
    """从落盘产物推断各步骤状态（phase3 单独跑时也能展示）。"""
    steps: list[dict[str, Any]] = []

    odds_ok = False
    odds_detail = "未找到"
    if odds_path and odds_path.is_file():
        od = json.loads(odds_path.read_text(encoding="utf-8"))
        n = len(od.get("matches") or [])
        odds_ok = n > 0
        odds_detail = f"{odds_path.name} · {n} 场"
    steps.append(make_step("1.1", "采集体彩赔率", odds_ok, odds_detail, "fetch_odds"))

    fund_ok = False
    fund_detail = "未找到"
    enriched = False
    fc_count = 0
    if fund_path and fund_path.is_file():
        fd = json.loads(fund_path.read_text(encoding="utf-8"))
        meta = fd.get("meta") or {}
        n = len(fd.get("records") or [])
        fund_ok = n > 0
        enriched = bool(meta.get("forecast_enriched"))
        fc_count = meta.get("forecast_match_count", 0)
        fund_detail = f"{fund_path.name} · {n} 场"
        if enriched:
            fund_detail += f" · forecast {fc_count} 场"
    steps.append(make_step("1.2", "采集球队基本面（ESPN）", fund_ok, fund_detail, "fetch_fundamentals"))
    steps.append(
        make_step(
            "1.3",
            "基本面 enrich · 8.7 预估赛果",
            enriched,
            f"{fc_count} 场含预估" if enriched else "未 enrich",
            "enrich_forecast",
        )
    )

    phase1_ok = odds_ok and (fund_ok or True)  # fund optional soft
    steps.append(
        make_step(
            "1.4",
            "阶段1 输入校验",
            odds_ok,
            "odds 就绪" if odds_ok else "odds 缺失",
            "phase1_validate",
        )
    )

    pred_ok = False
    pred_detail = "未找到"
    if pred_path and pred_path.is_file():
        pd = json.loads(pred_path.read_text(encoding="utf-8"))
        n = len(pd.get("predictions") or [])
        pred_ok = n > 0
        pred_detail = f"{pred_path.name} · {n} 场"
    steps.append(make_step("2.1", "五维预测引擎", pred_ok, pred_detail, "predict_engine"))

    # 预测档门禁：找含 prediction 且无 draft 的最新 run，或 state 里记录
    pred_gate_status, pred_gate_detail = "SKIP", "未校验"
    for run_dir in sorted(
        [p for p in RUNS_DIR.iterdir() if p.is_dir() and RUN_ID_RE.match(p.name)],
        key=lambda p: p.name,
        reverse=True,
    ):
        checks = run_dir / "checks.json"
        if not checks.is_file():
            continue
        data = json.loads(checks.read_text(encoding="utf-8"))
        inputs = data.get("inputs") or {}
        if inputs.get("prediction") and not inputs.get("draft_md") and not inputs.get("draft_json"):
            pred_gate_status = data.get("overall", "FAIL")
            pred_gate_detail = f"run_id={data.get('run_id')}"
            break
    pred_gate_ok = pred_gate_status == "PASS" or (pred_gate_status == "SKIP" and pred_ok)
    if pred_gate_status == "SKIP" and pred_ok:
        pred_gate_detail = f"{pred_path.name if pred_path else '?'} · 阶段2 预测已落盘"
    steps.append(
        make_step(
            "2.2",
            "预测档数据门禁",
            pred_gate_ok,
            f"{pred_gate_status} · {pred_gate_detail}",
            "gate_prediction",
        )
    )

    scan_ok = False
    scan_detail = "未找到"
    if scan_path and scan_path.is_file():
        sd = json.loads(scan_path.read_text(encoding="utf-8"))
        summary = sd.get("scan_summary") or {}
        scan_ok = bool(sd.get("funnel"))
        scan_detail = (
            f"{scan_path.name} · 候选 {summary.get('total_candidates', '?')} "
            f"→ 过闸 {summary.get('eligible_count', '?')}"
        )
    steps.append(make_step("3.1", "全玩法候选扫描", scan_ok, scan_detail, "scan_candidates"))

    draft_ok = bool(
        draft_html
        and draft_html.is_file()
        and ((draft_json and draft_json.is_file()) or (draft_md and draft_md.is_file()))
    )
    draft_detail = ""
    if draft_ok:
        core = draft_json.name if draft_json and draft_json.is_file() else draft_md.name
        draft_detail = f"{core} + {draft_html.name}"
    else:
        draft_detail = "草案未生成"
    steps.append(make_step("3.2", "决策草案 JSON/HTML", draft_ok, draft_detail, "generate_draft"))

    gate_status, gate_detail = read_gate_overall(gate_run_id)
    if gate_run_id:
        gate_ok = gate_status == "PASS"
        promo = "已 promote" if promoted else "未 promote"
        steps.append(
            make_step(
                "3.3",
                "决策档门禁 · promote",
                gate_ok,
                f"{gate_status} · {gate_detail} · {promo}",
                "gate_decision",
            )
        )
    else:
        steps.append(
            make_step("3.3", "决策档门禁 · promote", False, "待门禁", "gate_decision")
        )

    return steps


def _resolve_project_path(p: Path | str | None) -> Path | None:
    if not p:
        return None
    path = Path(p)
    if not path.is_absolute():
        path = ROOT / path
    return path


def steps_from_state_or_infer(
    day: str,
    scan: dict[str, Any] | None = None,
    gate_run_id: str | None = None,
    promoted: bool = False,
    prefer_state: bool = True,
    scan_path: Path | None = None,
    draft_json_path: Path | None = None,
    draft_md_path: Path | None = None,
    draft_html_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    state = load_workflow_state(day)
    if prefer_state and state and state.get("workflow_steps"):
        steps = [dict(s) for s in state["workflow_steps"]]
        ts = state.get("updated_at", "")
        if gate_run_id:
            gate_status, gate_detail = read_gate_overall(gate_run_id)
            promo = "已 promote" if promoted else "未 promote"
            for s in steps:
                if s.get("key") == "gate_decision":
                    s["status"] = "PASS" if gate_status == "PASS" else "FAIL"
                    s["detail"] = f"{gate_status} · {gate_detail} · {promo}"
        return steps, ts

    odds_p = fund_p = pred_p = None
    scan_p = _resolve_project_path(scan_path)
    draft_json = _resolve_project_path(draft_json_path)
    draft_md = _resolve_project_path(draft_md_path)
    draft_html = _resolve_project_path(draft_html_path)
    if state and state.get("paths"):
        paths = state["paths"]
        if paths.get("odds"):
            odds_p = _resolve_project_path(paths["odds"])
        if paths.get("fundamentals"):
            fund_p = _resolve_project_path(paths["fundamentals"])
        if paths.get("prediction"):
            pred_p = _resolve_project_path(paths["prediction"])
        if not scan_p and paths.get("scan"):
            scan_p = _resolve_project_path(paths["scan"])
        if not draft_json and paths.get("draft_json"):
            draft_json = _resolve_project_path(paths["draft_json"])
        if not draft_md and paths.get("draft_md"):
            draft_md = _resolve_project_path(paths["draft_md"])
        if not draft_html and paths.get("draft_html"):
            draft_html = _resolve_project_path(paths["draft_html"])
    if scan and not scan_p:
        meta = scan.get("meta") or {}
        if meta.get("odds_source"):
            odds_p = resolve_snapshot(meta["odds_source"])
        if meta.get("prediction_source"):
            pred_p = resolve_snapshot(meta["prediction_source"])

    from workflow_lib import latest_fundamentals, latest_odds, latest_prediction  # noqa: WPS433

    if not odds_p or not odds_p.is_file():
        o = latest_odds(day)
        odds_p = o
    if not fund_p or not fund_p.is_file():
        fund_p = latest_fundamentals(day)
    if not pred_p or not pred_p.is_file():
        pred_p = latest_prediction(day)

    promoted = promoted or bool(state and state.get("promoted"))
    steps = infer_workflow_steps(
        day,
        odds_path=odds_p,
        fund_path=fund_p,
        pred_path=pred_p,
        scan_path=scan_p,
        draft_json=draft_json,
        draft_md=draft_md,
        draft_html=draft_html,
        gate_run_id=gate_run_id,
        promoted=promoted,
    )
    ts = state.get("updated_at", "") if state else datetime.now().isoformat(timespec="seconds")
    return steps, ts


def render_workflow_pipeline_html(steps: list[dict[str, Any]], updated_at: str = "") -> str:
    if not steps:
        return ""
    rows: list[str] = []
    pass_n = sum(1 for s in steps if s["status"] == "PASS")
    fail_n = sum(1 for s in steps if s["status"] == "FAIL")
    overall_ok = fail_n == 0 and pass_n > 0
    badge_cls = "wf-ok" if overall_ok else "wf-warn"
    badge_txt = "全流程通过" if overall_ok else f"{fail_n} 步未通过"

    for s in steps:
        st = s["status"]
        icon = "✓" if st == "PASS" else ("✗" if st == "FAIL" else "○")
        cls = "pass" if st == "PASS" else ("fail" if st == "FAIL" else "skip")
        detail = s.get("detail") or ""
        rows.append(
            f"<li class=\"wf-step {cls}\">"
            f"<span class=\"wf-id num\">{s['id']}</span>"
            f"<span class=\"wf-icon\">{icon}</span>"
            f"<div class=\"wf-main\"><span class=\"wf-name\">{s['name']}</span>"
            f"<span class=\"wf-detail\">{detail}</span></div>"
            f"<span class=\"wf-status\">{st}</span>"
            f"</li>"
        )
    body = "\n".join(rows)
    ts_line = f"<span class=\"wf-ts\">更新 {updated_at}</span>" if updated_at else ""
    return f"""
<section class="workflow-pipeline" id="workflow-pipeline" aria-label="PM 工作流">
  <div class="wf-head">
    <h2 class="wf-title">PM 工作流</h2>
    <span class="wf-badge {badge_cls}">{badge_txt}</span>
    {ts_line}
  </div>
  <ol class="wf-steps">
{body}
  </ol>
  <p class="wf-note">模块 0 编排：数据 → 分析 → 投注 · 每步 PASS 后方可进入下一阶段</p>
</section>"""


def render_workflow_pipeline_md(steps: list[dict[str, Any]], updated_at: str = "") -> str:
    if not steps:
        return ""
    lines = [
        "## PM 工作流步骤",
        "",
        f"> 更新：{updated_at}" if updated_at else "",
        "",
        "| 步骤 | 名称 | 状态 | 说明 |",
        "|---|---|---|---|",
    ]
    for s in steps:
        lines.append(f"| {s['id']} | {s['name']} | **{s['status']}** | {s.get('detail', '')} |")
    lines.append("")
    return "\n".join(lines)
