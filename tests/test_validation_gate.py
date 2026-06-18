"""validate_gate / validation_lib 自测。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import validation_lib as vl  # noqa: E402


def test_sha256_and_run_id():
    odds = ROOT / "odds_260616_20260616-212759.json"
    assert odds.exists()
    h = vl.sha256_file(odds)
    assert len(h) == 64


def test_gate_pass_on_real_snapshot():
    odds = ROOT / "odds_260616_20260616-212759.json"
    pred = ROOT / "prediction_260616_20260616-214115.json"
    assert odds.exists() and pred.exists()
    run_id = f"test-pass-{vl.make_run_id()}"
    report, run_dir = vl.run_gate(
        odds=odds,
        prediction=pred,
        run_id=run_id,
    )
    assert report.overall == "PASS"
    assert (run_dir / "checks.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert not (run_dir / "report.md").exists()
    data = json.loads((run_dir / "checks.json").read_text(encoding="utf-8"))
    assert data["overall"] == "PASS"


def test_gate_fail_bad_odds_ref():
    odds = ROOT / "odds_260616_20260616-212759.json"
    pred = ROOT / "prediction_260616_20260616-214115.json"
    pred_data = json.loads(pred.read_text(encoding="utf-8"))
    pred_data["meta"]["odds_source"] = "nonexistent_odds.json"
    tmp = ROOT / "validation" / "runs" / "test-fixture-bad-ref.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(pred_data, ensure_ascii=False), encoding="utf-8")
    report, _ = vl.run_gate(
        odds=odds,
        prediction=tmp,
        run_id="test-fail-ref",
    )
    assert report.overall == "FAIL"
    assert any(c.check_id == "reference_chain" and c.status == "FAIL" for c in report.checks)


def test_draft_odds_fail():
    odds = ROOT / "odds_260616_20260616-212759.json"
    pred = ROOT / "prediction_260616_20260616-214115.json"
    odds_data = vl.load_json(odds)
    draft = "周二017 让球 @99.99 幻觉赔率"
    c = vl.check_draft_odds_mention(draft, odds_data)
    assert c.status == "FAIL"


def test_stamp_decision_md():
    md = "# 标题\n\n正文"
    out = vl.stamp_decision_md(md, "run-123")
    assert "validation_run_id=run-123" in out
    assert "validation/runs/run-123/checks.json" in out


def test_promote_blocked_on_fail():
    odds = ROOT / "odds_260616_20260616-212759.json"
    pred = ROOT / "prediction_260616_20260616-214115.json"
    pred_data = vl.load_json(pred)
    pred_data["meta"]["odds_source"] = "bad.json"
    tmp = ROOT / "validation" / "runs" / "test-promote-fail.json"
    tmp.write_text(json.dumps(pred_data, ensure_ascii=False), encoding="utf-8")
    report, run_dir = vl.run_gate(odds=odds, prediction=tmp, run_id="test-promote-fail")
    assert report.overall == "FAIL"
    try:
        vl.promote_artifacts(report, run_dir, draft_md=None, promote_prediction_file=True, prediction=tmp)
        raise AssertionError("expected PromoteBlockedError")
    except vl.PromoteBlockedError:
        pass


def test_promote_draft_to_fixture():
    odds = ROOT / "odds_260616_20260616-212759.json"
    pred_src = ROOT / "prediction_260616_20260616-214115.json"
    draft_src = ROOT / "decision_260616_match017_020_20260616-213000.md"
    assert draft_src.exists() and pred_src.exists()
    fixture_dir = ROOT / "tests" / "fixtures" / "promote"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    out_md = fixture_dir / "out_decision.md"
    out_pred = fixture_dir / "out_prediction.json"
    for p in (out_md, out_pred):
        if p.exists():
            p.unlink()
    out_pred.write_text(pred_src.read_text(encoding="utf-8"), encoding="utf-8")
    report, run_dir = vl.run_gate(
        odds=odds,
        prediction=out_pred,
        draft_md=draft_src,
        run_id="test-promote-ok",
    )
    assert report.overall == "PASS"
    result = vl.promote_artifacts(
        report,
        run_dir,
        draft_md=draft_src,
        out_md=out_md,
        promote_prediction_file=True,
        prediction=out_pred,
        force=True,
    )
    assert out_md.exists()
    text = out_md.read_text(encoding="utf-8")
    assert "validation_run_id=test-promote-ok" in text
    pred_data = vl.load_json(out_pred)
    assert pred_data["meta"].get("validation_run_id") == "test-promote-ok"
    assert result.artifacts["prediction"] == "tests/fixtures/promote/out_prediction.json"
    promote_doc = json.loads((run_dir / "promote.json").read_text(encoding="utf-8"))
    assert promote_doc["artifacts"]["decision_md"] == "tests/fixtures/promote/out_decision.md"


if __name__ == "__main__":
    test_sha256_and_run_id()
    test_gate_pass_on_real_snapshot()
    test_gate_fail_bad_odds_ref()
    test_draft_odds_fail()
    test_stamp_decision_md()
    test_promote_blocked_on_fail()
    test_promote_draft_to_fixture()
    print("OK validation tests")
