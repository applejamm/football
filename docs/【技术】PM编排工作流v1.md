# 【技术】PM 编排工作流 v1

> 产品需求：`docs/prd.md` §2 模块 0 · skill：`football-pm-orchestrator`

## 架构

```
football-pm-orchestrator (Cursor skill)
        │
        ▼
run_workflow.py  ←→  workflow_lib.py
        │
   ┌────┴────┬────────────┬──────────────┐
   ▼         ▼            ▼              ▼
阶段1      阶段2         阶段3      validate_gate.py
fetch_*   predict_engine scan+draft   (每阶段末尾)
```

## 阶段与产物

| 阶段 | 命令 | 产物 | 门禁 |
|---|---|---|---|
| 1 | `run_workflow.py --phase 1` | `odds_window_24h_*` · `odds_*` · `fundamentals_*` | 输入存在性 + matches 非空 |
| 2 | `run_workflow.py --phase 2` | `prediction_*` | `validate_gate` 实体锚定 |
| 3 | `run_workflow.py --phase 3` | `scan_*` · `decision_*.json` 草案 | `validate_gate` + `--promote` → **`reports/report_*.html`** |
| 4 | 文档对账（推荐） | `prd.md` + `【技术】*.md` 更新 | Rule `football-prd-doc-parity.mdc` 清单 |

状态文件：`validation/workflow/<day>_state.json`

## Top3 算法（T-5-7）

实现：`scan_candidates_lib.rank_top3_picks()`

1. 输入：`rank_top6()` 产出的 `scored` 列表（已含 composite_score）
2. 对每条计算 `win_gross = ref_stake × odds`（默认 ref_stake=100）
3. 按 `(win_gross, composite_score, p_true)` 降序
4. 取前 3，标注 `pick_label_user`：方案 A/B/C

与 `funnel.hero`（综合分最高）可能不同：Top3 按赢利潜力排序，hero 仍按综合分。

## 单关组合单（T-5-8 / T-5-9）

实现：`portfolio_lib.select_portfolio_plan()` · 渲染：`generate_decision_draft.py`

1. 过闸单关池 → **防御型**（3–4 注覆盖）+ **进攻型**（1–2 注重注）
2. 金额：防御 65/35 · 进攻 EV 加权；IMP-007 稳档封顶后余量回填
3. 自动择优 → 决策卡 `## 0. 主推`；另一套备选一行
4. **非串关**；预算默认 200（IMP-006 缩量已驳回）

详见：`docs/【技术】玩法扫描与6进1漏斗v1.md` §单关组合单

## CLI

```bash
python3 run_workflow.py --day 260617                    # 全流程
python3 run_workflow.py --day 260617 --phase 1          # 仅采集
python3 run_workflow.py --day 260617 --budget 200 --promote  # 全流程 + promote

./scripts/prefetch.sh workflow 260617 200 --promote
```

## Agent 手动补全（脚本外）

阶段 2 后建议调用 `football-odds-analyst` 生成 V2（脚本不强制）。  
阶段 3 草案生成后建议调用 `football-betting-strategist` 润色后再跑门禁。

## 任务映射

| PRD 任务 | 实现 |
|---|---|
| T-0-1 | `football-pm-orchestrator/SKILL.md` |
| T-0-2 | `workflow_lib.validate_inputs` + 阶段1 |
| T-0-3 | `run_workflow.py` |
| T-0-4 | `prefetch.sh workflow` |
| T-0-5 | `.cursor/rules/football-prd-doc-parity.mdc` + PM skill 阶段 4 |
| T-5-7 | `rank_top3_picks` + `generate_decision_draft` Top3 JSON + HTML |
| T-6-7 | `DECISION_HTML_TEMPLATE` v2.1 · `report_merge_lib` 合并交付 |

产物格式详见：`docs/【技术】产物格式约定v1.md`
