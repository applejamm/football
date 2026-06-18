"""report_merge_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from report_merge_lib import (  # noqa: E402
    merge_report_html,
    report_filename_from_decision_json,
    write_merged_report,
)


def test_report_filename():
    name = report_filename_from_decision_json(
        Path("decision_260619_workflow_20260618-220808.json")
    )
    assert name == "report_260619_workflow_20260618-220808.html"


def test_merge_contains_both_sections():
    pred = ROOT / "prediction_260619_20260618-220808.html"
    dec = ROOT / "decision_260619_workflow_20260618-220808.html"
    if not pred.exists() or not dec.exists():
        return
    merged = merge_report_html(
        pred.read_text(encoding="utf-8"),
        dec.read_text(encoding="utf-8"),
        day_code="260619",
        run_id="test-merge-001",
        generated_at="2026-06-18T22:08:08",
    )
    assert "section-prediction" in merged
    assert "section-decision" in merged
    assert "一、赛事预测" in merged
    assert "二、投注决策" in merged
    assert "validation_run_id: test-merge-001" in merged


def test_write_merged_from_json(tmp_path):
    pred_json = ROOT / "prediction_260619_20260618-220808.json"
    dec_json = ROOT / "validation/drafts/decision_260619_workflow_20260618-220808.json"
    if not pred_json.exists() or not dec_json.exists():
        return
    out = tmp_path / "report_test.html"
    write_merged_report(
        pred_json,
        dec_json,
        out,
        run_id="test-merge-002",
    )
    text = out.read_text(encoding="utf-8")
    assert out.exists()
    assert "section-prediction" in text
    assert "section-decision" in text
    assert "hero-pick" in text
    assert "周四025" in text


if __name__ == "__main__":
    test_report_filename()
    test_merge_contains_both_sections()
    test_write_merged_from_json(Path("/tmp"))
    print("OK report merge tests")
