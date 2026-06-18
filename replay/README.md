# 赛后复盘 · `replay/`

> **T-4-9** L1 记账 + **football-replay-analyst** L2 评分（独立 Agent，非 PM 编排）

## Agent 入口

用户说「复盘 260616」或 `@football-replay-analyst` → 见 `.cursor/skills/football-replay-analyst/SKILL.md`

L2 产物：`replay/replay_report_<issue>.md` · `improvements_backlog.md`

## L1 命令（记账）

```bash
cd /Users/CursorProject/football

# 按比赛日自动找最新 decision_<code>_*.md
python3 replay_decision.py --code 260616 --scores "周二017:2:0"

# 指定决策 + 虚拟跟踪
python3 replay_decision.py \\
  --decision decision_260616_match017_FUNNEL_REGEN.md \\
  --scores "周二017:2:0" \\
  --scan validation/drafts/scan_260616_demo.json
```

## 产出

| 目标 | 内容 |
|---|---|
| `decision_*.md` | 复盘 hook 表填比分/命中/收益 |
| `decision_*.html` | hero 金边变绿/红、结局条切实际、复盘表 |
| `tracking.md` | 注级明细匹配行回填（期号+注ID） |
| `tracking.md` 虚拟段 | 有 scan 时自动刷新 |
| `replay/runs/*.json` | 结算归档 |

## 与虚拟跟踪关系

`replay_decision.py` 在赛后**自动调用** `virtual_tracking` 逻辑（除非 `--no-virtual`）。  
赛前仍需 `scan_candidates.py` 生成 `scan_*.json`。

## 归档

```
replay/runs/<issue_no>_<timestamp>.json
```
