"""strategy_gates_lib 自测（IMP-006/007/008）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategy_gates_lib import (  # noqa: E402
    apply_low_odds_flags_to_candidates,
    collect_draw_risk_alerts,
    detect_low_odds_traps,
    is_catastrophic_triggered,
    parse_last_period_summary,
    resolve_effective_budget,
    stake_with_caps,
)

TRACKING_SAMPLE = """
## 期汇总
| 期号 | 比赛日 | 场次 | 骨架 | 预算 | 总投注 | 总收益 | ROI | 落入概率档 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| 2606171 | 260617 | x | A | 200 | 200 | **−77.82** | x | x | x |

## 累计
| 是否触发 catastrophic（80%）| **是 ⚠️** |
"""


def test_catastrophic_triggered():
    assert is_catastrophic_triggered(-200.0, 200, 0.8) is True
    assert is_catastrophic_triggered(-77.82, 200, 0.8) is False
    assert is_catastrophic_triggered(-160.0, 200, 0.8) is True


def test_parse_last_period():
    issue, pnl = parse_last_period_summary(TRACKING_SAMPLE)
    assert issue == "2606171"
    assert pnl == -77.82


def test_resolve_budget_shrink_after_catastrophic(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    res = resolve_effective_budget(
        200,
        strategy={
            "max_loss_per_round": 200,
            "catastrophic_threshold": 0.8,
            "catastrophic_shrink_factor": 0.5,
            "allow_full_budget_override": False,
            "min_unit": 2,
        },
        tracking_path=empty,
        allow_full_budget_override=False,
    )
    assert res.effective == 200
    assert res.catastrophic_active is False


def test_resolve_budget_shrink_with_tracking(tmp_path):
    tracking = tmp_path / "tracking.md"
    tracking.write_text(TRACKING_SAMPLE, encoding="utf-8")
    res = resolve_effective_budget(
        200,
        strategy={
            "max_loss_per_round": 200,
            "catastrophic_threshold": 0.8,
            "catastrophic_shrink_factor": 0.5,
            "allow_full_budget_override": False,
            "min_unit": 2,
        },
        tracking_path=tracking,
        allow_full_budget_override=False,
    )
    assert res.catastrophic_active is True
    assert res.effective == 100
    assert res.shrink_applied is True
    assert res.override_used is False


def test_shrink_disabled_when_factor_one(tmp_path):
    tracking = tmp_path / "tracking.md"
    tracking.write_text(TRACKING_SAMPLE, encoding="utf-8")
    res = resolve_effective_budget(
        200,
        strategy={
            "max_loss_per_round": 200,
            "catastrophic_threshold": 0.8,
            "catastrophic_shrink_factor": 1.0,
            "allow_full_budget_override": True,
            "min_unit": 2,
        },
        tracking_path=tracking,
        allow_full_budget_override=False,
    )
    assert res.effective == 200
    assert res.catastrophic_active is False
    assert res.shrink_applied is False


def test_full_budget_override_requires_flag(tmp_path):
    tracking = tmp_path / "tracking.md"
    tracking.write_text(TRACKING_SAMPLE, encoding="utf-8")
    res = resolve_effective_budget(
        200,
        strategy={
            "max_loss_per_round": 200,
            "catastrophic_threshold": 0.8,
            "catastrophic_shrink_factor": 0.5,
            "allow_full_budget_override": True,
            "min_unit": 2,
        },
        tracking_path=tracking,
        allow_full_budget_override=True,
    )
    assert res.override_used is True
    assert res.effective == 200


def test_low_odds_trap_021():
    odds = {
        "matches": [
            {
                "match_no": "周三021",
                "home_team": "葡萄牙",
                "away_team": "刚果金",
                "markets": [
                    {
                        "type": "胜平负",
                        "odds": {"胜": 1.13, "平": 11.0, "负": 31.0},
                    }
                ],
            }
        ]
    }
    traps = detect_low_odds_traps(
        odds,
        {"low_odds_win_max": 1.20, "low_odds_draw_min": 3.5, "low_odds_stable_cap": 25},
    )
    assert len(traps) == 1
    assert traps[0].match_no == "周三021"
    assert traps[0].win_odds == 1.13
    assert traps[0].max_stable_stake == 25


def test_low_odds_candidate_cap():
    traps = detect_low_odds_traps(
        {
            "matches": [
                {
                    "match_no": "周三021",
                    "home_team": "葡萄牙",
                    "away_team": "刚果金",
                    "markets": [{"type": "胜平负", "odds": {"胜": 1.13, "平": 11.0, "负": 31.0}}],
                }
            ]
        },
        {"low_odds_win_max": 1.20, "low_odds_draw_min": 3.5, "low_odds_stable_cap": 25},
    )
    cands = [
        {
            "id": "C1",
            "match_no": "周三021",
            "play_type": "wdl",
            "pick": "胜",
            "odds": 1.13,
        }
    ]
    apply_low_odds_flags_to_candidates(cands, traps)
    assert cands[0]["strategy_flags"]["max_stake_cap"] == 25
    assert stake_with_caps(55, cands[0]) == 24  # cap 25 → 24（2 元整数倍）


def test_draw_risk_alert():
    prediction = {
        "predictions": [
            {
                "match_no": "周三021",
                "home_cn": "葡萄牙",
                "away_cn": "刚果金",
                "prediction": {"outcome_probs": {"胜": 0.656, "平": 0.199, "负": 0.145}},
            }
        ]
    }
    alerts = collect_draw_risk_alerts(
        prediction, {"周三021"}, {"draw_risk_threshold": 0.15}
    )
    assert len(alerts) == 1
    assert alerts[0].draw_prob == 0.199


if __name__ == "__main__":
    test_catastrophic_triggered()
    test_parse_last_period()
    test_resolve_budget_shrink_after_catastrophic()
    test_resolve_budget_shrink_with_tracking()
    test_shrink_disabled_when_factor_one()
    test_full_budget_override_requires_flag()
    test_low_odds_candidate_cap()
    test_draw_risk_alert()
    print("OK")
