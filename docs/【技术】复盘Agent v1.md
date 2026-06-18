# 【技术】复盘 Agent v1

| 字段 | 值 |
|---|---|
| 版本 | v1.1 |
| Skill | `.cursor/skills/football-replay-analyst/SKILL.md` |
| 对应 PRD | T-4-9 延伸 · C-5 · AGENT_ROADMAP P0-1 |
| 状态 | ✅ skill 已建 |
| 编排 | **独立 Agent**，不挂 `football-pm-orchestrator` |

## 定位

**改进对象 = 投注方案（选注 / 仓位 / 玩法结构），不是软件工程。**

| 层级 | 模块 | 职责 |
|---|---|---|
| L1 | `replay_decision.py` | 记账：盈亏、tracking、decision 赛后态 |
| L2 | `football-replay-analyst` | 评 **预测方案 + 决策方案**；写 **方案级** backlog（人类审批） |

### 方案改进 vs 工程改进

| | 本 Agent ✅ | 不属于本 Agent ❌ |
|---|---|---|
| 改进对象 | 下一期怎么买：防冷是否叠、是否缩量、稳档封顶、Top3 是否换主推 | 改 Python、skill、门禁、PRD、HTML 模板 |
| 典型 backlog | 「碾压盘禁止叠防冷注」「catastrophic 缩量」「主胜 <1.20 稳档封顶」 | 「validate_gate 加检查项」「重构 scan_candidates」 |
| 落地 | `improvements_backlog.md` → 人类批采纳/驳回 → 用户下一期调整下注或再议 yaml | PM 阶段 4、工程迭代 |

详见产品总览：`docs/【产品】Agent工作流总览.md` §4.1

## 产物

| 路径 | 说明 |
|---|---|
| `replay/replay_report_<issue>.md` | 双 Agent 评分报告 |
| `replay/improvements_backlog.md` | **投注方案**改进建议（人类审批；不直接改 yaml / 代码） |
| `replay/runs/<issue>_<ts>.json` | L1 结算归档（由 replay_decision 写） |

## 触发方式

- 用户直接：`复盘 260616` / `@football-replay-analyst`
- Loop：赛后 FT 事件 → 调用本 skill（**不经 PM 编排**）
- 策略师步骤 10：委托本 skill 完成 L2；L1 仍跑 `replay_decision.py`

## 赛果来源

ESPN：`https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD`

## 与 F 档 `decision_*_review_*` 的区别

| | 赛后复盘 | F 档 review |
|---|---|---|
| 时机 | 赛后 | 赛前 |
| 命名 | `replay/replay_report_*` | `decision_*_review_*` |
| 可下单 | 否（复盘认知） | 否（只读预览） |

## 禁止

- PM orchestrator 阶段流水线挂载
- 直接改 `STRATEGY_DEFAULT.yaml` / 代码 / skill / 门禁（仅可 **建议**，由人类审批后另行处理）
- 样本 <10 期建议切骨架/放宽 EV 闸
- 把 backlog 条目写成工程任务（如「加单元测试」「改 validate_gate」）
