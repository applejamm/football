"""artifact_lib 路径约定自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from artifact_lib import (  # noqa: E402
    BACKTEST_REPORTS_DIR,
    REPORTS_DIR,
    SNAPSHOT_FUNDAMENTALS_DIR,
    SNAPSHOT_ODDS_DIR,
    SNAPSHOT_PREDICTION_DIR,
    delivery_path,
    latest_in_dirs,
    odds_search_dirs,
    rel_snapshot,
    resolve_snapshot,
)


def test_reports_dir_under_root():
    assert REPORTS_DIR == ROOT / "reports"
    assert BACKTEST_REPORTS_DIR == ROOT / "reports" / "backtest"


def test_snapshot_dirs():
    assert SNAPSHOT_ODDS_DIR == ROOT / "snapshots" / "odds"
    assert SNAPSHOT_PREDICTION_DIR == ROOT / "snapshots" / "prediction"
    assert SNAPSHOT_FUNDAMENTALS_DIR == ROOT / "snapshots" / "fundamentals"


def test_resolve_snapshot_legacy_root():
    legacy = ROOT / "odds_260616_20260616-212759.json"
    if legacy.is_file():
        resolved = resolve_snapshot(legacy.name)
        assert resolved == legacy


def test_latest_in_dirs_finds_legacy():
    found = latest_in_dirs("odds_260616_*.json", odds_search_dirs())
    if (ROOT / "odds_260616_20260616-212759.json").is_file():
        assert found is not None


def test_rel_snapshot():
    p = SNAPSHOT_ODDS_DIR / "odds_test.json"
    assert rel_snapshot(p) == "snapshots/odds/odds_test.json"


def test_delivery_path():
    p = delivery_path("report_260619_test.html")
    assert p.parent == REPORTS_DIR
    assert p.name == "report_260619_test.html"


if __name__ == "__main__":
    test_reports_dir_under_root()
    test_snapshot_dirs()
    test_delivery_path()
    print("OK artifact_lib tests")
