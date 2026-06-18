"""generate_decision_draft 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generate_decision_draft import (  # noqa: E402
    extract_style_script,
    hero_stake,
    load_json,
    render_html,
    render_top3_cards_html,
    write_html_from_json,
)


def test_extract_style_after_doctype():
    tpl = ROOT.parent / ".cursor/skills/football-betting-strategist/DECISION_HTML_TEMPLATE.html"
    style, script = extract_style_script(tpl)
    assert ":root" in style
    assert "hero-pick" in style
    assert "top3-picks" in style
    assert "top3-card" in style
    assert "forecast-block" in style
    assert "workflow-pipeline" in style
    assert "getElementById" in script
    assert "top3Cards" in script
    assert "复制本文件" not in style


def test_generate_from_scan():
    scan = load_json(ROOT / "validation/drafts/scan_260616_demo.json")
    hero = scan["funnel"]["hero"]
    assert hero["scheme_id"] == "S1"
    assert hero["match_no"] == "周二017"
    assert hero_stake(100) == 50


def test_top3_cards_html():
    scan_path = ROOT / "validation/drafts/scan_260616_20260617-221535.json"
    if not scan_path.exists():
        return
    scan = load_json(scan_path)
    top3 = scan["funnel"].get("top3") or []
    hero = scan["funnel"]["hero"]
    pred = load_json(ROOT / "prediction_260616_20260617-003251.json")
    from generate_decision_draft import pred_index  # noqa: E402

    pred_idx = pred_index(pred)
    html = render_top3_cards_html(top3, 100, hero.get("candidate_id"), pred_idx)
    assert "top3-card" in html
    assert "win-gross" in html
    assert top3[0]["pick_label_user"] in html
    assert html.count("top3-card") >= 3


def test_full_html_has_top3_section():
    scan_path = ROOT / "validation/drafts/scan_260616_20260617-221535.json"
    pred_path = ROOT / "prediction_260616_20260617-003251.json"
    if not scan_path.exists() or not pred_path.exists():
        return
    scan = load_json(scan_path)
    prediction = load_json(pred_path)
    hero = scan["funnel"]["hero"]
    top3 = scan["funnel"].get("top3") or []
    top6 = scan["funnel"]["top6"]
    from generate_decision_draft import pred_index  # noqa: E402

    pred_idx = pred_index(prediction)
    pred_row = pred_idx[hero["match_no"]]
    tpl = ROOT.parent / ".cursor/skills/football-betting-strategist/DECISION_HTML_TEMPLATE.html"
    style, script = extract_style_script(tpl)
    page = render_html(scan, hero, top6, top3, pred_row, pred_idx, 50, 100, style, script)
    assert "top3-picks" in page
    assert page.count("top3-card") >= 3
    assert "forecast-block" in page
    assert "forecast-summary" in page
    assert "赛果概率预估" in page
    assert "workflow-pipeline" in page
    assert "PM 工作流" in page
    assert "预估赛果" in page
    assert top3[0]["pick_label_user"] in page


def test_html_from_json_matches_direct_render(tmp_path):
    scan_path = ROOT / "validation/drafts/scan_260616_20260617-221535.json"
    pred_path = ROOT / "prediction_260616_20260617-003251.json"
    if not scan_path.exists() or not pred_path.exists():
        return
    import subprocess

    out_json = tmp_path / "decision_test_test001.json"
    out_html = tmp_path / "decision_test_test001.html"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "generate_decision_draft.py"),
            "--scan",
            str(scan_path),
            "--prediction",
            str(pred_path),
            "--prefix",
            "decision_test",
            "--budget",
            "100",
            "--stamp",
            "test001",
            "--out-dir",
            str(tmp_path),
        ],
        check=True,
        cwd=str(ROOT),
    )
    assert out_json.exists()
    assert out_html.exists()
    direct = out_html.read_text(encoding="utf-8")
    regen = tmp_path / "decision_test_regen.html"
    write_html_from_json(out_json, regen)
    assert regen.read_text(encoding="utf-8") == direct


if __name__ == "__main__":
    test_extract_style_after_doctype()
    test_generate_from_scan()
    test_top3_cards_html()
    test_full_html_has_top3_section()
    test_html_from_json_matches_direct_render(None)
    print("OK")
