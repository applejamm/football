"""workflow_lib 自测。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from workflow_lib import fundamentals_date_from_odds  # noqa: E402


def test_fundamentals_date_from_odds_list_date():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "odds.json"
        p.write_text(
            json.dumps(
                {
                    "list_date": "2026-06-18",
                    "match_date_code": "260619",
                    "matches": [],
                }
            ),
            encoding="utf-8",
        )
        assert fundamentals_date_from_odds(p) == "20260618"


if __name__ == "__main__":
    test_fundamentals_date_from_odds_list_date()
    print("OK")
