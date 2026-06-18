"""replay_lib 自测。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from replay_lib import (  # noqa: E402
    parse_bets_from_md,
    parse_decision_meta,
    settle_bets,
    update_decision_md_replay,
)


SAMPLE = """# 投注决策 · 260616

> 期号 2606161

## 1. 行动卡 · 主推单注

| 注 ID | 比赛 | 玩法 | 选择 | 赔率 | 金额 |
|---|---|---|---|---|---|
| **S1** | 周二017 法国vs塞内加尔 | 让球[-1] | **胜（法国让球胜）** | 2.07 | **50 元** |

## 4. 复盘 hook

| scheme | 实际比分 | 命中？ | 实际收益 |
|---|---|---|---|
| S1 | | | |
"""


def test_parse_and_settle_hero_hit():
    meta = parse_decision_meta(SAMPLE)
    assert meta["issue_no"] == "2606161"
    bets = parse_bets_from_md(SAMPLE)
    assert len(bets) == 1
    assert bets[0].bet_id == "S1"
    settled = settle_bets(bets, {"周二017": (2, 0)})
    assert len(settled) == 1
    assert settled[0].hit is True
    assert settled[0].pnl == 53.5


def test_settle_miss():
    bets = parse_bets_from_md(SAMPLE)
    settled = settle_bets(bets, {"周二017": (2, 2)})
    assert settled[0].hit is False
    assert settled[0].pnl == -50


def test_replay_hook_fill():
    bets = parse_bets_from_md(SAMPLE)
    settled = settle_bets(bets, {"周二017": (2, 0)})
    out = update_decision_md_replay(SAMPLE, settled)
    assert "| S1 | 2:0 | ✓ | +53.50 |" in out


if __name__ == "__main__":
    test_parse_and_settle_hero_hit()
    test_settle_miss()
    test_replay_hook_fill()
    print("OK")
