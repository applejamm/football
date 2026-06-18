"""workflow_status_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from workflow_status_lib import infer_workflow_steps, steps_from_state_or_infer  # noqa: E402


def test_infer_scan_passes_with_explicit_scan_path():
    scan_path = ROOT / "validation/drafts/scan_260619_20260618-210344.json"
    if not scan_path.is_file():
        return
    steps = infer_workflow_steps("260619", scan_path=scan_path)
    scan_step = next(s for s in steps if s["id"] == "3.1")
    assert scan_step["status"] == "PASS", scan_step
    assert "261" in scan_step["detail"]


def test_steps_from_state_uses_workflow_day_not_match_date_code():
    scan_path = ROOT / "validation/drafts/scan_260619_20260618-210344.json"
    state_path = ROOT / "validation/workflow/260619_state.json"
    if not scan_path.is_file() or not state_path.is_file():
        return
    steps, _ = steps_from_state_or_infer(
        "260619",
        scan_path=scan_path,
        gate_run_id="test-promote-ok",
        promoted=True,
        prefer_state=True,
    )
    scan_step = next(s for s in steps if s["id"] == "3.1")
    draft_step = next(s for s in steps if s["id"] == "3.2")
    assert scan_step["status"] == "PASS", scan_step
    assert draft_step["status"] == "PASS", draft_step


def test_wrong_day_without_scan_path_used_to_fail():
    scan_path = ROOT / "validation/drafts/scan_260619_20260618-210344.json"
    if not scan_path.is_file():
        return
    steps, _ = steps_from_state_or_infer(
        "260618",
        scan_path=scan_path,
        prefer_state=False,
    )
    scan_step = next(s for s in steps if s["id"] == "3.1")
    assert scan_step["status"] == "PASS", scan_step


if __name__ == "__main__":
    test_infer_scan_passes_with_explicit_scan_path()
    test_steps_from_state_uses_workflow_day_not_match_date_code()
    test_wrong_day_without_scan_path_used_to_fail()
    print("OK")
