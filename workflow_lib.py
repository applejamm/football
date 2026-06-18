"""PM 编排工作流共享逻辑（T-0-3）。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from artifact_lib import (
    SNAPSHOT_FUNDAMENTALS_DIR,
    fundamentals_search_dirs,
    latest_in_dirs,
    odds_search_dirs,
    prediction_search_dirs,
)

ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "validation" / "workflow"
DEFAULT_STRATEGY = ROOT.parent / ".cursor/skills/football-betting-strategist/STRATEGY_DEFAULT.yaml"
TRACKING_PATH = ROOT / "tracking.md"


def latest_file(pattern: str, roots: list[Path] | None = None) -> Path | None:
    if roots is None:
        roots = [ROOT]
    return latest_in_dirs(pattern, roots)


def latest_odds(day: str | None = None, window_hours: int | None = None) -> Path | None:
    if window_hours:
        found = latest_file(f"odds_window_{window_hours}h_*.json", odds_search_dirs())
        if found:
            return found
    pat = f"odds_{day}_*.json" if day else "odds_*_*.json"
    return latest_file(pat, odds_search_dirs())


def latest_fundamentals(day: str | None = None) -> Path | None:
    if day:
        merged = SNAPSHOT_FUNDAMENTALS_DIR / f"fundamentals_fifa.world_{day}-merged.json"
        if merged.is_file():
            return merged
        cal = day_to_calendar(day)
        for pat in (f"fundamentals_*_{day}*.json", f"fundamentals_*_{cal}*.json"):
            found = latest_file(pat, fundamentals_search_dirs())
            if found:
                return found
        day_keys = {day, cal, cal[-6:] if len(cal) == 8 else day}
        matched: list[Path] = []
        for directory in fundamentals_search_dirs():
            if not directory.is_dir():
                continue
            for p in directory.glob("fundamentals_*.json"):
                if p.name == "fundamentals_db.json":
                    continue
                try:
                    meta = json.loads(p.read_text(encoding="utf-8")).get("meta") or {}
                    if meta.get("date") in day_keys:
                        matched.append(p)
                except (json.JSONDecodeError, OSError):
                    continue
        if matched:
            return sorted(matched, key=lambda x: x.name)[-1]
        return None
    return latest_file("fundamentals_*_*.json", fundamentals_search_dirs())


def latest_prediction(day: str | None = None, window_hours: int | None = None) -> Path | None:
    if day:
        found = latest_file(f"prediction_{day}_*.json", prediction_search_dirs())
        if found:
            return found
    if window_hours:
        return latest_file(
            f"prediction_window_{window_hours}h_*.json", prediction_search_dirs()
        ) or latest_file("prediction_window_*.json", prediction_search_dirs())
    return latest_file("prediction_*_*.json", prediction_search_dirs())


def run_cmd(args: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def write_state(day: str, payload: dict[str, Any]) -> Path:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKFLOW_DIR / f"{day}_state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_state(day: str) -> dict[str, Any] | None:
    path = WORKFLOW_DIR / f"{day}_state.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_inputs(odds: Path, fundamentals: Path | None) -> tuple[bool, str]:
    if not odds.is_file():
        return False, f"odds 不存在: {odds}"
    data = json.loads(odds.read_text(encoding="utf-8"))
    matches = data.get("matches") or []
    if not matches:
        return False, "odds 无 matches 字段"
    if fundamentals and not fundamentals.is_file():
        return False, f"fundamentals 不存在: {fundamentals}"
    return True, "inputs_ok"


def day_to_calendar(day: str) -> str:
    if len(day) == 6 and day.isdigit():
        return f"20{day}"
    return day


def fundamentals_date_from_odds(odds_path: Path) -> str:
    """从 odds 快照推导 ESPN scoreboard 日期（list_date 优先）。"""
    data = json.loads(odds_path.read_text(encoding="utf-8"))
    list_date = data.get("list_date") or ""
    if list_date:
        return list_date.replace("-", "")
    for m in data.get("matches") or []:
        kickoff = m.get("kickoff_local") or ""
        if kickoff[:10]:
            return kickoff[:10].replace("-", "")
    code = data.get("match_date_code") or ""
    if code:
        return day_to_calendar(code)
    return datetime.now().strftime("%Y%m%d")


def sync_merged_fundamentals(day: str, fund_path: Path) -> Path:
    """工作流用：复制最新基本面到 snapshots/fundamentals/*_{day}-merged.json。"""
    SNAPSHOT_FUNDAMENTALS_DIR.mkdir(parents=True, exist_ok=True)
    merged = SNAPSHOT_FUNDAMENTALS_DIR / f"fundamentals_fifa.world_{day}-merged.json"
    merged.write_text(fund_path.read_text(encoding="utf-8"), encoding="utf-8")
    return merged


def phase1_collect(day: str, window_hours: int = 24) -> dict[str, Path]:
    from workflow_status_lib import infer_workflow_steps, merge_steps_into_state  # noqa: WPS433

    run_cmd(
        [
            "python3",
            "fetch_odds.py",
            "--within-hours",
            str(window_hours),
            "--emit-window",
            "--diff-min-pct",
            "1",
        ]
    )
    odds = latest_odds(day, window_hours=window_hours) or latest_odds(day)
    if not odds:
        raise FileNotFoundError(f"阶段1失败：未找到 odds_{day}_*.json")
    cal = fundamentals_date_from_odds(odds)
    run_cmd(
        [
            "python3",
            "fetch_fundamentals.py",
            "--date",
            cal,
            "--odds",
            str(odds),
        ]
    )
    snaps = sorted(
        [
            p
            for directory in fundamentals_search_dirs()
            if directory.is_dir()
            for p in directory.glob("fundamentals_fifa.world_*.json")
            if "-merged" not in p.name
        ],
        key=lambda p: p.name,
    )
    snap = snaps[-1] if snaps else None
    if not snap:
        raise FileNotFoundError("阶段1失败：未找到 fundamentals 快照")
    fund = sync_merged_fundamentals(day, snap)
    ok, msg = validate_inputs(odds, fund)
    if not ok:
        raise RuntimeError(f"阶段1校验失败: {msg}")
    steps = infer_workflow_steps(day, odds_path=odds, fund_path=fund)
    merge_steps_into_state(day, steps)
    return {"odds": odds, "fundamentals": fund, "workflow_steps": steps}


def phase2_analyze(day: str, odds: Path, window_hours: int = 24) -> Path:
    from workflow_status_lib import infer_workflow_steps, merge_steps_into_state  # noqa: WPS433

    run_cmd(["python3", "predict_engine.py", "--day", day, "--odds", str(odds)])
    pred = latest_prediction(day, window_hours=window_hours)
    if not pred:
        raise FileNotFoundError(f"阶段2失败：未找到 prediction_{day}_*.json")
    fund = latest_fundamentals(day)
    gate_cmd = [
        "python3",
        "validate_gate.py",
        "--odds",
        str(odds),
        "--prediction",
        str(pred),
    ]
    if fund:
        gate_cmd.extend(["--fundamentals", str(fund)])
    run_cmd(gate_cmd)
    gate_run_id = _latest_run_id()
    steps = infer_workflow_steps(
        day,
        odds_path=odds,
        fund_path=fund,
        pred_path=pred,
        gate_run_id=gate_run_id,
    )
    merge_steps_into_state(day, steps)
    return pred


def _latest_run_id() -> str | None:
    runs = sorted((ROOT / "validation" / "runs").glob("*"), key=lambda p: p.name)
    if not runs:
        return None
    return runs[-1].name


def phase3_decide(
    day: str,
    odds: Path,
    prediction: Path,
    budget: int,
    promote: bool = False,
    allow_full_budget: bool = False,
) -> dict[str, Path | str]:
    from strategy_gates_lib import load_strategy_config, resolve_effective_budget  # noqa: WPS433

    cfg = load_strategy_config(DEFAULT_STRATEGY)
    budget_res = resolve_effective_budget(
        budget,
        strategy=cfg,
        tracking_path=TRACKING_PATH,
        allow_full_budget_override=allow_full_budget,
    )
    effective_budget = budget_res.effective
    if budget_res.shrink_applied or budget_res.override_used:
        print(f"[i] IMP-006 预算闸: {budget_res.reason}")
        print(f"    请求 {budget_res.requested} 元 → 有效 {effective_budget} 元")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    scan_out = ROOT / "validation" / "drafts" / f"scan_{day}_{stamp}.json"
    run_cmd(
        [
            "python3",
            "scan_candidates.py",
            "--odds",
            str(odds),
            "--prediction",
            str(prediction),
            "--out",
            str(scan_out),
        ]
    )
    prefix = f"decision_{day}_workflow"
    _enrich_scan_strategy_gates(scan_out, odds, prediction, budget_res)
    _run_generate_draft(scan_out, prediction, prefix, effective_budget, stamp)

    drafts = sorted((ROOT / "validation" / "drafts").glob(f"{prefix}_{stamp}.json"), key=lambda p: p.name)
    if not drafts:
        raise FileNotFoundError("阶段3失败：未生成 decision 草案 JSON")
    draft_json = drafts[-1]
    draft_html = draft_json.with_suffix(".html")

    gate_args = [
        "python3",
        "validate_gate.py",
        "--odds",
        str(odds),
        "--prediction",
        str(prediction),
        "--draft-json",
        str(draft_json),
    ]
    if draft_html.is_file():
        gate_args.extend(["--draft-html", str(draft_html)])
    fund = latest_fundamentals(day)
    if fund:
        gate_args.extend(["--fundamentals", str(fund)])
    if DEFAULT_STRATEGY.is_file():
        gate_args.extend(["--strategy", str(DEFAULT_STRATEGY)])
    run_cmd(gate_args)

    gate_run_id = _latest_run_id()
    from workflow_status_lib import infer_workflow_steps, merge_steps_into_state  # noqa: WPS433

    steps = infer_workflow_steps(
        day,
        odds_path=odds,
        fund_path=fund,
        pred_path=prediction,
        scan_path=scan_out,
        draft_json=draft_json,
        draft_html=draft_html,
        gate_run_id=gate_run_id,
        promoted=False,
    )
    merge_steps_into_state(day, steps)

    _run_generate_draft(
        scan_out,
        prediction,
        prefix,
        effective_budget,
        stamp,
        gate_run_id=gate_run_id,
        promoted=promote,
        budget_resolution=budget_res,
    )

    if promote:
        promote_args = [
            "python3",
            "validate_gate.py",
            "--odds",
            str(odds),
            "--prediction",
            str(prediction),
            "--draft-json",
            str(draft_json),
        ]
        if draft_html.is_file():
            promote_args.extend(["--draft-html", str(draft_html)])
        if fund:
            promote_args.extend(["--fundamentals", str(fund)])
        if DEFAULT_STRATEGY.is_file():
            promote_args.extend(["--strategy", str(DEFAULT_STRATEGY)])
        promote_args.extend(["--promote", "--force"])
        run_cmd(promote_args)
        steps = infer_workflow_steps(
            day,
            odds_path=odds,
            fund_path=fund,
            pred_path=prediction,
            scan_path=scan_out,
            draft_json=draft_json,
            draft_html=draft_html,
            gate_run_id=gate_run_id,
            promoted=True,
        )
        merge_steps_into_state(day, steps)

    from artifact_lib import delivery_path  # noqa: WPS433
    from report_merge_lib import report_filename_from_decision_json  # noqa: WPS433

    report_name = report_filename_from_decision_json(draft_json)
    report_path = delivery_path(report_name) if promote else None

    return {
        "scan": scan_out,
        "draft_json": draft_json,
        "draft_html": draft_html if draft_html.is_file() else "",
        "report_html": str(report_path) if report_path else "",
        "gate_run_id": gate_run_id or "",
        "budget_requested": budget,
        "budget_effective": effective_budget,
        "budget_resolution": budget_res.to_dict(),
    }


def _enrich_scan_strategy_gates(
    scan_out: Path,
    odds_path: Path,
    prediction_path: Path,
    budget_res: Any,
) -> None:
    from strategy_gates_lib import enrich_scan_payload, load_json  # noqa: WPS433

    payload = load_json(scan_out)
    odds_data = load_json(odds_path)
    pred_data = load_json(prediction_path)
    enrich_scan_payload(
        payload,
        odds_data,
        pred_data,
        budget_resolution=budget_res,
        strategy_path=DEFAULT_STRATEGY,
    )
    scan_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_generate_draft(
    scan_out: Path,
    prediction: Path,
    prefix: str,
    budget: int,
    stamp: str,
    gate_run_id: str | None = None,
    promoted: bool = False,
    budget_resolution: Any | None = None,
) -> None:
    cmd = [
        "python3",
        "generate_decision_draft.py",
        "--scan",
        str(scan_out),
        "--prediction",
        str(prediction),
        "--prefix",
        prefix,
        "--budget",
        str(budget),
        "--stamp",
        stamp,
    ]
    if gate_run_id:
        cmd.extend(["--gate-run-id", gate_run_id])
    if promoted:
        cmd.append("--promoted")
    run_cmd(cmd)


def run_full_workflow(
    day: str,
    budget: int = 200,
    promote: bool = False,
    window_hours: int = 24,
    allow_full_budget: bool = False,
) -> dict[str, Any]:
    ts = datetime.now().isoformat(timespec="seconds")
    paths1 = phase1_collect(day, window_hours=window_hours)
    pred = phase2_analyze(day, paths1["odds"], window_hours=window_hours)
    paths3 = phase3_decide(
        day, paths1["odds"], pred, budget, promote=promote, allow_full_budget=allow_full_budget
    )
    fund = latest_fundamentals(day)
    state = {
        "day": day,
        "updated_at": ts,
        "phase": 3,
        "status": "complete",
        "paths": {
            "odds": str(paths1["odds"]),
            "fundamentals": str(fund or paths1.get("fundamentals") or ""),
            "prediction": str(pred),
            "scan": str(paths3["scan"]),
            "draft_json": str(paths3["draft_json"]),
            "draft_html": str(paths3.get("draft_html") or ""),
            "report_html": str(paths3.get("report_html") or ""),
        },
        "budget": budget,
        "budget_effective": paths3.get("budget_effective", budget),
        "promoted": promote,
    }
    write_state(day, state)
    return state
