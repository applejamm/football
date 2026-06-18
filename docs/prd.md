### 需求PRD文档：体彩足球赛事预测AI系统  

| 字段 | 值 |
|---|---|
| **版本** | v1.6.0 |
| **状态** | 迭代中 · PM 四阶段 · 单关双方案择优（T-5-9）· IMP-006 驳回（满预算 200） |
| **维护者** | 产品 + 工程共建 |
| **关联文档** | `docs/【技术】预测引擎v1.md` · `docs/【技术】数据验证门禁v1.md` · `docs/【技术】玩法扫描与6进1漏斗v1.md` · `docs/【产品】Agent工作流总览.md` · `AGENT_ROADMAP.md` · `DECISION_HTML_GUIDE.md` · `validation/README.md` |

#### **〇、文档说明**

- **读者**：产品、工程、Agent skill 维护者。  
- **用途**：定义做什么、怎么验收、任务拆到哪；**不**替代技术设计细节（见技术 doc）。  
- **维护节奏**：每完成里程碑或变更验收策略 → 更新任务状态 + 变更日志。  
- **章节索引**：一 目标 → 二 功能 → 三 验收 → 四 交互 → 五 任务（含 **TODO**）。  
- **产物分层**：**正式交付**（根目录 `prediction_*` / `decision_*` / `tracking.md`）与 **验证调试**（`validation/` · `simulation/` · `backtest/` · `tests/`）**不得混放、不得互相覆盖**。

#### **术语表（Brief）**

| 术语 | 含义 |
|---|---|
| EV | 期望价值；体彩语境下恒为负，「最优」= 亏损最少 |
| p_true | 去水后的真实概率估计 |
| 预测层 | 五维引擎 → 3–5 套赛果组合（准确率导向） |
| 下注层 | 全玩法扫描 → Top6 → **Top3 供选** + **主推单关组合单**（防御/进攻双方案自动择优；**非串关**） |
| 单关组合单 | 3–4 笔独立单关 + 金额分配；同场多注互斥；与 2 串 1 无关 |
| 防御型 / 进攻型 | 防御=多场覆盖主攻+防冷；进攻=1–2 笔重注；系统按 EV+不确定性自动锁定主推 |
| PM 编排层 | 调度数据 → 分析 → 投注三阶段；每阶段过闸后才进下一步 |
| 空单 | 本期全部候选不过 EV 底线 → 合法输出「不建议下注」 |
| forward 验证 | 赛前锁定预测、赛后结算，非事后反推 |
| 数据验证门禁 | 发布正式报告前的可复算校验；FAIL 时只落盘 `validation/`，不产出正式报告 |
| 正式产物 | 已通过门禁、可供用户/体彩店直接阅读的 `prediction_*` / `decision_*` |
| 验证产物 | 门禁运行记录、逐项检查结果、调试摘要；仅工程/Agent 使用 |

---  

#### **一、核心目标**

开发一套基于 AI 决策的足球赛事预测与下注辅助系统，自动获取官方数据，通过多维度权重分析，完成两条闭环：

1. **预测层**：输出胜平负、总进球数、具体比分的 3–5 套组合方案，提升预测准确性。  
2. **下注层**：在竞彩全部玩法中扫描候选，筛出期望收益最优的 **6 套方案**进入二次评估，**输出 Top 3 赢利方案供选**；并自动生成 **防御型 / 进攻型** 两套**单关组合单**（含金额分配），由系统按 **加权 EV + 不确定性** 自动锁定主推（用户接受满预算 200，IMP-006 catastrophic 缩量已驳回）。

> **业务边界**：竞彩全市场长期负 EV，「最赚钱」= **期望亏损最少**（EV 相对最优），不是保证盈利。

**非目标（明确不做）**

- 不承诺盈利或提升绝对胜率；不做 xG / ELO / 自训 ML（见 T-4-15 ⏸️）。  
- 不替代用户最终下单判断；系统输出建议，不构成投资建议。  
- 不在本届世界杯用已知赛果做盲测回测（见 B 档延后）。  
- v1 不建设 Web App；交付物为 CLI + 静态 HTML / Markdown。  
- v1 不允许跳过 E 档门禁直接发布正式报告（Agent 手工落盘亦同）。

**目标用户与核心场景**

| 角色 | 场景 | 成功态 |
|---|---|---|
| 体彩店分析员 | 赛前 30 分钟出本期报告 | 打开 decision HTML → 3s 内看到 **主推组合单** + Top3 |
| Agent 维护者 | 按 PRD 迭代 skill / 模板 | 任务 ID 与验收档一一对应 |
| 复盘者（赛后） | 核对命中与盈亏、评 Agent | `football-replay-analyst` → tracking + `replay/replay_report_*` |
| 工程调试者 | 排查 Agent 幻觉 / 数值偏离 | 打开 `validation/runs/<id>/` 定位 FAIL 项与源 JSON 差异 |

**发布原则（v1.3 新增）**

> 任何 **正式** `prediction_*` / `decision_*` 必须先过 **E 档数据验证门禁**；验证过程与结论只写入 `validation/`，**禁止**把调试日志、FAIL 摘要、中间态 HTML 与正式报告同名或同目录混放。

---

#### **二、功能模块**

##### **0. PM 编排工作流（Agent 总控 · v1.4 新增）**

> **定位**：本项目的第一入口不是单个分析/投注 skill，而是 **PM Agent** 按固定顺序调度子 Agent 与脚本，每阶段完成且 **数据验证通过** 后才进入下一阶段。人类或 Cursor 对话触发「本期工作流」时，默认走本模块。

**0.1 角色与 skill 映射**

| 阶段 | PM 调度对象 | 职责 | 产物 |
|---|---|---|---|
| **阶段 1 · 数据采集** | 脚本 + 可选 `openclaw-skills-football-data` | 拉取体彩赔率、球队基本面；写入快照 | `odds_*.json` · `fundamentals_*.json` |
| **阶段 1 · 门禁** | `validate_gate.py`（输入档） | 校验快照完整、场次可锚定；**FAIL 则阻塞** | `validation/runs/<id>/` |
| **阶段 2 · 胜率分析** | `predict_engine.py` + `football-odds-analyst` | 五维预测 + 盘口 V2 分析（去水概率、胜率叙事） | `prediction_*` · `analysis_*_v2.md` |
| **阶段 2 · 门禁** | `validate_gate.py`（预测档） | 预测 JSON 与 odds 实体锚定一致 | 同上 |
| **阶段 3 · 投注决策** | `scan_candidates.py` + `portfolio_lib.py` + `generate_decision_draft.py` + `football-betting-strategist` | 全玩法扫描 → Top6 → **防御/进攻双方案** → 自动择优 → Top3 供选 | `validation/drafts/scan_*` · `decision_*` 草案 |
| **阶段 3 · 门禁** | `validate_gate.py` + `--promote` | 决策草案八类必检；PASS 后 promote 正式报告 | 根目录 `decision_*` |

**PM Agent skill**：`football-pm-orchestrator`（`.cursor/skills/football-pm-orchestrator/`）  
**一键脚本**：`run_workflow.py`（`./scripts/prefetch.sh workflow <day>` 等价入口）

**0.2 三阶段流水线（必须顺序执行）**

```
用户 / 体彩店：「跑本期 260617」
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 阶段 1 · 数据采集（PM 调度）                                │
│   fetch_odds → fetch_fundamentals → 输入门禁 PASS         │
└───────────────────────────┬───────────────────────────────┘
                            │ PASS
                            ▼
┌───────────────────────────────────────────────────────────┐
│ 阶段 2 · 胜率分析（PM 调度分析 Agent）                     │
│   predict_engine → football-odds-analyst（V2 可选）         │
│   → 预测门禁 PASS                                           │
└───────────────────────────┬───────────────────────────────┘
                            │ PASS
                            ▼
┌───────────────────────────────────────────────────────────┐
│ 阶段 3 · 投注决策（PM 调度投注 Agent）                     │
│   scan_candidates → portfolio_lib（双方案择优）            │
│   → generate_decision_draft → strategist 润色 → promote    │
└───────────────────────────┬───────────────────────────────┘
                            ▼
              正式 decision：主推组合单 + Top3 卡 + S1 单注参考
```

**0.3 阶段完成定义（DoD）**

| 阶段 | DoD | FAIL 时 |
|---|---|---|
| 1 | 最新 `odds_window_24h_*` 或 `odds_*` 含目标场次；`fundamentals_*` 覆盖主客队；输入门禁 PASS | 不进入阶段 2；输出 `validation/runs/*/report.md` |
| 2 | `prediction_*.json` 存在且与 odds 场次一致；可选 V2 报告已生成 | 不进入阶段 3 |
| 3 | `funnel.top3` 非空或合法空单；**主推组合单**（`portfolio_lib` 择优）已写入决策草案；门禁 PASS 并已 promote | 根目录无新正式 `decision_*` |
| 4（推荐） | `prd.md` 变更日志 + 进度/差距表与实现一致 | 不阻塞交付，但须在下次迭代前补齐 |

**0.4 阶段 4 · 文档对账（v1.5 新增）**

- **触发**：工作流 promote 后；或修改 `football/*.py` / 门禁 / football skill 后；用户说「对齐 PRD」
- **执行**：`football-pm-orchestrator` 阶段 4 + Rule `.cursor/rules/football-prd-doc-parity.mdc`
- **DoD**：`prd.md` 变更日志 + 任务/进度与实现一致；相关 `【技术】*.md` 已更新

**0.5 与现有 skill 的关系**

- `project-pm`：通用 Scrum/蓝皮书 PM；**不替代**本项目的足球专用编排 skill。  
- `football-odds-analyst` / `football-betting-strategist`：**被 PM 调度**，不自行跳过阶段 1/2 直接写正式报告。  
- 子 skill 步骤 8「先 validate 后 publish」与本模块阶段门禁 **叠加**，不冲突。

---

##### **1. 数据获取模块**  
- **数据源**：体彩官方公布的赛事数据（下注页同源 API：`getMatchCalculatorV1.qry`）、国际足联/欧足联等权威机构的历史赛事统计。  
- **可投注候选池（v1.5）**：`fetch_odds.py --within-hours 24 --emit-window` → `odds_window_24h_<ts>.json`；仅 **status=Selling、未开赛、未来 24h 内** 场次；扫描与决策**优先**读此文件。  
- **采集内容**：  
  - 球队硬实力：近10场胜率、世界杯淘汰赛历史晋级率、本届主力阵型、近5场场均进球/失球数；  
  - 关键人员状态：主力伤病名单、核心球员大赛进球/助攻效率、球队红黄牌累计数；  
  - 大赛适应性：小组赛出线形势、赛事举办地气候/海拔适应情况；  
  - 对战历史：两队近3次正式交锋结果；  
  - 市场数据：体彩官方实时赔率、让球数。  
- **更新频率**：赛前24小时更新一次，赛前2小时补充最新伤病/阵容信息。  

##### **2. AI决策模块**  
- **权重模型**：按“球队硬实力30%+关键人员状态25%+大赛适应性20%+对战历史15%+市场数据10%”计算各维度得分。  
- **组合方案生成**：基于各维度得分，匹配胜平负、总进球数、具体比分，生成3-5套综合胜率最高的组合方案，每套方案需附逻辑说明。  

##### **3. 测试与数据验证模块**

> **定位拆分**：本模块含两条独立链路——**效果验证**（猜得准不准）与 **数据验证门禁**（报出来的数是不是源数据、有没有幻觉）。二者产物目录分离，门禁是正式报告发布的**前置条件**。

**3.1 效果验证（已有 · 与正式报告目录隔离）**

| 子项 | 目录 | 用途 |
|---|---|---|
| 历史回测 | `backtest/` | 管道调试；100 场 B 档延后 |
| Forward 模拟 | `simulation/` | 赛前锁定 → 赛后结算（A 档） |
| 异常场景 | `backtest/test_scenarios.py` | 伤退 / 生死战 / 高平局 H2H |
| 单元测试 | `tests/` | 引擎与结算脚本自测 |

**3.2 数据验证门禁（v1.3 新增 · 防偏离 / 防幻觉）**

在 Agent 或脚本**发布正式报告之前**，对当期全部输入快照与输出草案做可复算校验：

```
输入快照 manifest
  odds_*.json · fundamentals_*.json · prediction_*.json · STRATEGY_DEFAULT.yaml
        │
        ▼
  validate_gate.py（或 skill 等价步骤）
        │
   ┌────┴────┐
 PASS      FAIL
   │          └→ 仅写 validation/runs/<run_id>/
   │               checks.json + report.md + diff 摘要
   │               **不**生成/覆盖根目录正式 decision_* / prediction_*
   ▼
  promote → 根目录正式产物 + manifest 中记录 run_id
```

**必检项（任一 FAIL → 整期 BLOCK）**

| 类别 | 检查内容 | 防什么 |
|---|---|---|
| **实体锚定** | 场次编号、主客队名、开球时间 ∈ 当期 `odds_*.json` | 虚构比赛 / 张冠李戴 |
| **赔率锚定** | 报告中每条注的赔率 = 源 JSON 对应玩法字段（容差 0） | 编造赔率 |
| **概率可复算** | `p_true`、去水概率与源赔率公式一致（容差 ≤ 0.5pp） | EV 链幻觉 |
| **EV 可复算** | 候选 EV 与 `p_true × odds − 1` 一致（容差 ≤ 0.3pp） | 决策排序失真 |
| **引用链** | decision 草案声明的 `prediction_*.json` 存在且被读取 | 引擎一致度空引用 |
| **决策自洽** | Top6 第 1 名 `scheme_id` = 主推 `.hero-pick`；空单 ⇔ 全部 EV < reject_below | 漏斗逻辑偏离 PRD |
| **金额边界** | 建议金额 ∈ 策略预算与 catastrophic 缩量规则 | 资金建议越界 |
| **文案-数据一致** | HTML/MD 中展示的 EV、赔率、队名与 JSON 源逐字段比对 | Agent 叙述幻觉 |

**验证产物规范（与正式报告严格隔离）**

| 路径 | 内容 | 规则 |
|---|---|---|
| `validation/runs/<run_id>/manifest.json` | 本期引用的全部源文件路径 + sha256 | 可追溯 |
| `validation/runs/<run_id>/checks.json` | 每项 PASS/FAIL + 期望值/实际值 | 机器可读 |
| `validation/runs/<run_id>/report.md` | 人类可读摘要 + FAIL 修复建议 | **非**正式决策报告 |
| `validation/latest/` | 指向最近一次 run（或 symlink） | 快速调试入口 |
| `validation/README.md` | 目录约定与运行命令 | 工程 onboarding |

**禁止事项**

- 禁止将 `validation/**` 内文件命名为 `decision_*` / `prediction_*` 或复制到根目录冒充正式交付。  
- 禁止在正式 HTML Footer 只写「数据快照路径」却不附 `validation_run_id`（待 T-3-11）。  
- 禁止跳过门禁直接由 Agent skill 写根目录正式报告（待 T-3-12 skill 约束）。

**3.3 历史数据回测 / 实时模拟 / 异常场景**（效果向，见 §三 A/B 档）

- **历史数据回测**：近 3 届大赛 100 场 → B 档延后；产物只在 `backtest/reports/`。  
- **实时模拟测试**：`daily_simulate.py` → `simulation/`；与正式 `prediction_*` 可同源生成，但 sim 档案**不得**替代正式报告。  
- **异常场景测试**：`backtest/test_scenarios.py`；验证逻辑字段存在，不验 ROI。

##### **4. 下注决策模块**（预测层与资金层衔接）

> **定位**：把「市场赔率 + 预测引擎 + 基本面」转化为**单一可执行推荐**；与模块 2 的 3–5 套预测方案互补，不替代。

**4.1 玩法枚举（全量扫描）**

每期对当期全部场次，按体彩竞彩规则生成候选池，覆盖但不限于：

| 玩法类别 | 示例 |
|---|---|
| 不让球胜平负 | 法国胜 / 平 / 负 |
| 让球胜平负 | 让球[-1] 平（净胜 1 球） |
| 总进球数 | 0–7 球各档 |
| 比分单关 | 1:0、2:1 等 |
| 半全场 | 胜胜、平平、胜平等 9 档 |
| 串关 | 2 串 1 抽样（Top N 单关两两组合；非全矩阵混合过关） |

**4.2 决策漏斗与量化规则**

```
阶段 A · 广撒网（玩法扫描）
  当期全部场次 × 全部玩法 → 结构化候选池（含 odds, p_true, EV）

阶段 B · Top 6 入围（期望收益排序）
  按 EV 降序取前 6 套方案进入二次评估
  · 不足 6 套：输出实际数量 + 被 reject_below 砍掉的数量
  · EV 相同 tie-break：p_true 降序 → 引擎一致度降序 → 相关性单元数升序

阶段 C · 二次评估（6 进 1）
  综合分 = EV_norm×40% + Engine_align×25% + Fundamentals×20% + Independence×15%
  · EV_norm：将 Top6 的 EV 线性映射到 0–100（最高 EV = 100）
  · Engine_align：与 prediction Top1 同向=100，Top3 内=70，否则=40
  · Fundamentals：score_fundamentals 或五维硬实力差映射 0–100
  · Independence：独立判断单元越少越高（1 单元=100，每多 1 单元 −20，下限 0）
  · 综合分最高者 = 主推；同分取 EV 更高者

阶段 D · 最终输出（v1.4：Top3 供选）
  · **Top 3 赢利方案**：在 Top6 入围池内，按「参考注额 × 赔率」命中毛奖金降序取前 3，附 p_true / EV / 综合分
  · **主推标注**：综合分最高者 = 方案 A（`.hero-pick`）；B/C 为备选，用户可任选其一下单
  · **Top 6 明细表**：EV、四维子分、综合分、状态（主推/入围/被砍）
  · **合法空单**：Top6 全部 EV < reject_below（默认 −20%）→「本期不建议下注」
```

**阈值引用**（实现以 `STRATEGY_DEFAULT.yaml` 为准，变更须同步 PRD）：

| 参数 | 默认值 | 含义 |
|---|---|---|
| `reject_below` | −0.20 | 低于此 EV 不进 Top6 展示（被砍区） |
| `must_have` | −0.12 | 可入决策的 EV 下限 |
| `preferred` | −0.08 | 优先加注 EV 线 |

**4.3 与现有产物的映射**

| PRD 概念 | 当前产物 | 差距 |
|---|---|---|
| 24h 可投注池 | `odds_window_24h_*.json` | ✅ v1.5 已落地 |
| 玩法全量扫描（六类） | `scan_candidates.py` | ✅ 含半全场；串关仍为 2×1 抽样 |
| Top 6 入围 | `rank_top6()` + decision Top6 表 | ✅ |
| 主推 + Top3 供选 | `funnel.hero` + `funnel.top3` | ✅ 主推=综合分；Top3=赢利排序，需在 UI 区分 |
| 复盘只读模式 | `decision_*_review_*` | ⚠️ 惯例已用，待 F 档正式化 |
| 预测层输入 | `prediction_*.json` | ⚠️ skill 未强制引用（T-2-5） |
| 决策队名锚定 | E 档文案一致 | ❌ 待 `decision_team_anchor` + 去硬编码 |

**4.4 产出物**

- `decision_<期号>_match*_<时间>.md` / `.html` — 含 Top 6 表 + **主推 1 套**区块（**须**附 `validation_run_id`，见 E 档）  
- `tracking.md` — 赛后命中与盈亏归档  
- `validation/runs/<run_id>/` — 门禁过程产物；**非**正式交付，仅供调试


#### **三、测试验收标准**

> **2026-06-16 修订**：当前处于 2026 世界杯赛程中，**可用样本极少**，且多数赛果已知——**不能用「已知结果」做盲测回测**。验收分两档：

**A 档 · 当前世界杯（小样本 forward 验证，主路径）**

1. **赛前锁定**：开球前运行 `daily_simulate.py` / `predict_engine.py`，预测写入 `simulation/`（带时间戳，不可事后改）。
2. **赛后结算**：填入实际比分，统计「胜平负 + 总进球 + 比分」组合命中；**不做 60% 硬性门槛**（样本 < 20 场时统计无意义）。
3. **过程指标**：每场比赛 3–5 套方案均有逻辑说明；异常场景（伤退 / 生死战 / 高平局 H2H）逻辑中有体现。

**B 档 · 历史档案回测（延后，非当前阻塞项）**

1. 需另建「赛前快照库」（当时赔率 + 基本面 + 预测），不是拿赛果反推。
2. 目标仍为组合准确率 ≥ 60%，但 **不纳入本届世界杯验收**；待 2026 赛后或下一届大赛前再补 100 场档案。

**异常场景（不变）**

特殊场景下，系统能在方案逻辑中明确体现关键变量的影响。

**C 档 · 下注决策（6 进 1，与 A 档并行验收）**

1. **候选覆盖**：每期决策报告附「玩法扫描范围」说明；至少覆盖不让球、让球、总进球、比分、**半全场**、串关**六类**。  
2. **Top 6 入围**：报告含 EV 排序 Top 6 表（不足 6 时列实际数量 + 被 EV 闸砍掉统计）。  
3. **主推 1 套**：报告有且仅有 **1 个**「最终推荐」区块，含玩法、选项、金额、四维综合理由。  
4. **空单合法**：全部候选 EV 低于底线时，输出空单而非强行推荐。  
5. **过程指标（样本 < 20 期）**：不做 ROI 硬性门槛；追踪「主推方案 vs Top6 其余 vs 被砍注」虚拟收益（见 T-5-5）。

**D 档 · 交互体验（与 C 档并行，见第四节）**

1. **3 秒读懂**：打开决策 HTML，用户能在 3 秒内定位「本期主推 1 套」区块。  
2. **漏斗可追踪**：Top 6 表与主推区块有视觉层级区分（主推 > 入围 > 被砍）。  
3. **状态完整**：赛前 / 空单 / 赛后复盘三种态均有对应布局，不混用。  
4. **动效克制**：所有过渡 ≤ 300ms；尊重 `prefers-reduced-motion`。  
5. **移动端可读**：375px 宽度下主推区块无需横向滚动即可读完。

**E 档 · 数据验证门禁（v1.3 · 正式报告发布前置，与 A/C 并行）**

> **目标**：决策方案不偏离 PRD 漏斗、不产生未锚定数据的「叙述幻觉」、数值可独立复算。  
> **原则**：E 档 FAIL = **本期无正式报告**；用户只看到上一期合法产物或明确「本期验证未通过」提示（由工程/Agent 处理，不输出半真半假 decision HTML）。

1. **目录隔离**：验证产物仅存在于 `validation/`；根目录 `decision_*` / `prediction_*` 须带 `validation_run_id` 元数据（JSON 字段或 HTML comment，待 T-3-11）。  
2. **全项 PASS**：§2 模块 3.2 八类必检项全部 PASS 方可 promote 正式报告。  
3. **FAIL 可调试**：每次 FAIL 在 `validation/runs/<run_id>/` 留完整 manifest + checks + report；工程师无需打开正式 HTML 即可定位差异字段。  
4. **Agent 约束**：`football-betting-strategist` / `football-odds-analyst` 生成流程中，**先**跑门禁 **后**写根目录正式文件（T-3-12）。  
5. **过程指标（不设准确率门槛）**：每期记录 PASS/FAIL 率、FAIL 类别分布；样本 < 20 期不做「门禁通过率 ≥ X%」硬门槛，只做趋势监控。  
6. **与 A 档关系**：A 档 forward 模拟验证「猜得准」；E 档验证「说得对、算得对」——**两者独立，均须满足后才算一期完整交付**。

**F 档 · 复盘只读模式（v1.5 · 与 C 并行，非实盘）**

> 开球后或销售截止后，用**冻结快照**生成仅供查看的决策，**不得**作为实盘下单依据。

1. **输入**：历史 `odds_window_24h_*` 或 `odds_*` + 同期 `prediction_*`（不重新 `--within-hours` 过滤）
2. **命名**：`decision_<code>_review_<ts>.{md,html}`；页眉/MD 标明「复盘 · 不可下单」
3. **tracking**：不写实盘投注行；可选写虚拟跟踪
4. **门禁**：仍跑 `validate_gate`；promote 可选

**E 档验收检查表（摘要）**

| ID | 检查项 | 通过条件 |
|---|---|---|
| VAL-1 | 目录隔离 | 无 `validation/**` 文件与根目录正式报告同名 |
| VAL-2 | 实体锚定 | checks.json 中 entity_anchor = PASS |
| VAL-3 | 数值可复算 | odds / p_true / EV 三项复算 PASS |
| VAL-4 | 决策自洽 | Top6#1 = hero-pick；空单逻辑 PASS |
| VAL-5 | 引用链 | prediction JSON 路径存在且被读取 |
| VAL-6 | promote 追溯 | 正式产物 manifest 含 validation_run_id |

---

#### **四、交互设计规范**

> **目标**：让用户在 30 秒内完成「看懂 → 信任 → 执行」；交互服务于 **6 进 1 决策漏斗**，不做装饰性动效。  
> **权威实现**：`football-betting-strategist/DECISION_HTML_TEMPLATE.html` + `DECISION_HTML_GUIDE.md`；本节为 PRD 级产品约束，模板迭代须回溯本节。

##### **4.1 设计原则（Purposeful Motion）**

| 原则 | 业务含义 | 在本系统中的落地 |
|---|---|---|
| **反馈** | 用户操作/阅读后有确认感 | 主推卡 hover 微抬升；Top 6 行 hover 高亮对应维度分 |
| **导向** | 视线按决策优先级流动 | 固定阅读顺序：警告 → KPI → **主推 1 套** → Top 6 → 基本面 → 被砍区 |
| **聚焦** | 最重要信息一眼可见 | 主推区块用 `.hero-pick` 金边 + 最大字号；其余降一级对比度 |
| **连续** | 切换状态不丢失上下文 | 赛前→赛后只改 KPI/结局条颜色，区块顺序不变 |

**禁止**：自动轮播、无限循环脉冲、阻塞点击的入场动画、纯装饰粒子背景。

##### **4.2 页面类型与信息架构**

| 页面 | 产物 | 用户任务 | 核心交互 |
|---|---|---|---|
| **预测报告** | `prediction_*.html` | 看 3–5 套预测组合谁更准 | 方案卡并列对比；Top1 标「引擎首选」 |
| **下注决策** | `decision_*.html` | **只推 1 套**，理解为何不下其余 | 漏斗 + 主推英雄区 + Top 6 表 |
| **盘口分析** | `analysis_*_v2.md` | 深度读市场（Agent 中间产物） | Markdown，无强制动效 |
| **数据验证** | `validation/runs/*/report.md` | 排查幻觉 / 数值偏离 | **非用户交付**；工程师调试专用 |
| **国际盘对照** | `compare_intl_*.html` | 验证体彩定价偏差 | 双源 bar 对比；偏差 >3pp 标黄 |
| **基本面信号** | `scores_*.html` | 核对硬实力 / 形式 | 球队对比 bar（已有） |
| **赛后复盘** | decision HTML §复盘 | 核对盈亏、更新认知 | 命中行变绿 / 未中变红（T-4-9） |

##### **4.3 核心用户路径（对齐模块 4 漏斗）**

```
打开 decision HTML
    │
    ▼
[0–3s] 读 Header + 警告条 → 知本期预算/风险态（catastrophic 缩量等）
    │
    ▼
[3–8s] 读 KPI 四卡 → 知「赚钱概率 / 最坏亏损」量级
    │
    ▼
[8–15s] ★ 主推 1 套（.hero-pick）→ 玩法 / 选项 / 金额 / 四维理由
    │         └─ 主 CTA 心智：「如果只下一注，就下这个」
    ▼
[15–30s] Top 6 表（.top6）→ 看落选原因；可展开四维得分明细
    │
    ▼
[可选] 对阵基本面 / 被砍区 / 复盘 hook
```

**空单路径**：跳过 KPI 收益态 → 居中「本期不建议下注」+ 被砍统计饼图/数字 → 仍展示 Top 6（含 EV 不足项）供学习。

##### **4.4 组件与微交互规范**

**4.4.1 决策页区块顺序（v2.0 目标，在 v1.1 基础上扩展）**

| # | 区块 | class | 动效 | 说明 |
|---|---|---|---|---|
| 1 | Header | `header.h` | 无 | 期号 / 骨架 / 时间戳 |
| 2 | 警告条 | `.warn` | 入场 fade 200ms | catastrophic / 勘误 |
| 3 | KPI 四卡 | `.kpi` | 错峰 fade 各 +50ms | 最佳 / 赚钱率 / 亏钱率 / 均损 |
| 4 | **主推 1 套** | `.hero-pick` | 入场 slide-up 250ms | **新增**；C 档必须项 |
| 4b | **Top3 供选** | `.top3-picks` | 三卡 stagger 各 +50ms | **v2.1**；T-6-7 |
| 5 | **Top 6 表** | `.top6` | 行 stagger 40ms | **新增**；EV 排序 + 综合分 |
| 6 | 对阵基本面 | `.matchups` | bar width 200ms ease-out | 仅主推涉及场次 `.focus` |
| 7 | 补充注单（可选） | `.bets` | hover translateY −2px | 骨架 A 多注时保留；非主推 |
| 8 | 结局全景条 | `.ov` | bar 宽度过渡 300ms | 概率段合计 100% |
| 9 | 被砍区 | `.cut` | 无 | EV / 相关性闸 |
| 10 | 复盘 hook | `table.t.replay` | 赛后行色 150ms | T-4-9 填充后触发 |
| 11 | Footer | `footer` | 无 | 数据快照路径 + `validation_run_id`（E 档） |

**4.4.2 主推英雄区 `.hero-pick`（T-5-4 视觉标准）**

- 布局：左「玩法 + 选项 + 赔率」/ 右「建议金额 + 综合分雷达或四维条」  
- 视觉：金边 `border-color: var(--gold)` + 浅金背景；金额用 `28px+` 等宽数字  
- 交互：hover `transform: translateY(-2px); box-shadow` 200ms；无 click 必填项  
- 文案：首行固定模板「**最终推荐 · 如果本期只下一注**」

**4.4.3 Top 6 表 `.top6`（T-5-2 视觉标准）**

| 列 | 内容 | 交互 |
|---|---|---|
| 排名 | 1–6 | 第 1 行与 `.hero-pick` 联动高亮（同 scheme_id） |
| 玩法 | 不让球 / 让球 / 总进球 / 比分 / 串关 | 玩法图标色区分（五类各一色，色盲友好加文字） |
| EV | −11.4% 等 | EV ≥ preferred 绿；must_have 黄；< reject 灰删线 |
| 综合分 | 0–100 | 迷你四维 bar（EV/引擎/基本面/独立性） |
| 状态 | 主推 / 入围 / 被砍 | 被砍行 opacity 0.55，hover 显示砍因 tooltip |

**4.4.4 数据可视化微交互（沿用并扩展 v1.1）**

| 元素 | 时长 | 缓动 | 用途 |
|---|---|---|---|
| 对比 bar 宽度 | 200ms | ease-out | 基本面 / 概率「谁更强」 |
| 注单胜率 `.bar` | 200ms | ease-out | p_true 可视化 |
| KPI 数字 | 150ms | ease-out | 赛后复盘数字翻色（绿/红） |
| Top 6 行 hover | 150ms | ease-out | 背景提亮，不位移 |
| 页面区块入场 | 200–250ms | ease-out | 仅首次加载；`prefers-reduced-motion` 时禁用 |

**时序上限**：单页所有 CSS 过渡合计感知 < 500ms；禁止 500ms+ 编排动画。

##### **4.5 状态与过渡**

| 状态 | 触发 | UI 变化 | 过渡 |
|---|---|---|---|
| **赛前默认** | 生成 decision | KPI 中性色；复盘表空 | — |
| **主推态** | Top 6 有 ≥1 过闸 | 显示 `.hero-pick` + Top 6 | hero slide-up 250ms |
| **空单态** | 全部 EV < 底线 | KPI 改灰；隐藏 `.bets`/`.ov`；保留 Top 6 | warn 条强调原因 |
| **缩量态** | catastrophic 触发 | warn 条 + KPI「预算减半」 | warn 边框 pulse 1 次 300ms |
| **赛后命中** | T-4-9 复盘 | 主推行背景绿；KPI 更新 | 色变 150ms |
| **赛后未中** | T-4-9 复盘 | 主推行背景红；结局条切实际段 | 色变 150ms |

状态切换**不改变区块顺序**，仅改内容与颜色，保持用户空间记忆。

##### **4.6 无障碍与性能**

- **色彩**：红/绿不单独传达命中；必附「命中 / 未中 / 被砍」文字标签  
- **动效**：全局 `@media (prefers-reduced-motion: reduce)` 关闭 transition / animation  
- **数字**：金额、赔率、EV 使用 `tabular-nums`（现有 `.num`）  
- **对比度**：正文 `#e2e8f0` on `#0b1220` ≥ WCAG AA；muted 文字不低于 4.5:1  
- **性能**：仅动画 `transform` / `opacity` / `width`（bar）；禁止 layout thrashing  
- **离线**：决策 HTML 自包含 CSS，无 CDN 依赖（现有约定保持）

##### **4.7 交互验收标准（D 档 · 摘要）**

| ID | 检查项 | 通过条件 |
|---|---|---|
| UX-1 | 主推可见性 | 首屏或一次滚动内可见 `.hero-pick` |
| UX-2 | 漏斗一致 | Top 6 第 1 名 = 主推 scheme_id |
| UX-3 | 空单不误导 | 空单页无「建议金额 >0」的主推 |
| UX-4 | 动效克制 | Lighthouse 无 CLS；reduced-motion 下无动画 |
| UX-5 | 移动适配 | 375px 下 hero / Top6 表可读，无横向滚动 |
| UX-6 | 赛后闭环 | 复盘后 KPI + 主推行状态与 tracking 一致 |

##### **4.8 与开发任务映射**

| PRD 任务 | 交互交付 |
|---|---|
| T-5-2 Top 6 | `.top6` 表 + stagger 入场 |
| T-5-4 主推 1 套 | `.hero-pick` 英雄区 |
| T-5-4 + T-4-3 | 更新 `DECISION_HTML_TEMPLATE.html` → v2.0 |
| T-4-9 复盘 | 赛后状态过渡 + 复盘表填色 |
| T-2-4 预测 HTML | 方案卡 Top1 高亮 + 并列对比 |

**现状差距**：M6 下注决策已闭环（260619 `decision_*_workflow` + T-5-9 组合单）；VAL-4 决策自洽（Top6#1 vs hero vs 组合主推）仍待补。

---

#### **五、开发任务拆分与进度跟踪**

> **维护说明**：每完成一项，将状态改为 ✅ 并填写「完成日期 / 产物路径」。  
> **模块阅读顺序**（按依赖）：1 数据 → **3.2 验证门禁** → 2 预测 → 3.1 效果测试 → **4 基础设施** → 5 下注 6 进 1 → 6 交互。  
> **发布顺序**：采集完成 → 生成草案 → **E 档 PASS** → promote 正式 `prediction_*` / `decision_*`。
> **状态图例**：✅ 已完成 · ⚠️ 部分完成 · ❌ 未开始 · 🔜 进行中 · ⏸️ 暂缓  
> **上次盘点**：2026-06-18（v1.5 文档对账 · 24h 窗口 · 六类玩法）

##### **进度总览**

| 模块 | 已完成 | 部分 | 未开始/延后 | 合计 |
|---|---|---|---|---|
| 1. 数据获取 | 9 | 2 | 7 | 18 |
| 2. AI 决策（预测层） | 5 | 2 | 0 | 7 |
| 3. 测试与数据验证 | 6 | 3 | 2 | 11 |
| 4. 现有工具链（EV Agent 基础设施） | 8 | 0 | 8 | 16 |
| 5. 下注决策（6 进 1 + Top3） | 7 | 1 | 1 | 9 |
| 6. 交互设计 | 5 | 2 | 1 | 8 |
| **PRD 核心链路（模块 1–3 + 5 + 6）** | **31** | **10** | **11** | **52** |

**PRD 最小闭环**：✅ 预测层 · ✅ 6 进 1 + Top3 · ✅ 交互 v2.1 · ⚠️ E 档 VAL-3/4 扩展 · ⚠️ 文档对账靠阶段 4 流程保障  
**验证路径**：E 档数据门禁 + A 档 forward + C 档决策 + D 档交互 + **F 档复盘（只读）**

---

##### **TODO · 未完成需求（活跃清单）**

> **维护规则**：完成 → 任务表改 ✅ + 此处 `[x]` + 变更日志一行。  
> **执行原则**：**从 P0 #1 开始做**；P1 在 P0 核心闭环后；P2 有余力再做；**P3 本期不做**。

**优先级定义**

| 级别 | 含义 | 当前策略 |
|---|---|---|
| **P0** | 阻塞正式交付或信任基座（E/C/D 档核心） | **立即做**，严格按下方序号 1→N |
| **P1** | 闭环增强；不阻塞「门禁 + 6 进 1 + 交互 v2.0」最小可用 | P0 核心完成后启动 |
| **P2** | 体验 polish、数据丰富、运营向增强 | 排期靠后 |
| **P3** | 延后、待决策、或 PRD 明确不做 | **本期不实施** |

**统计（2026-06-17）**：P0 未完成 **11**（含 ⚠️ 5）· P1 **12** · P2 **10** · P3 **3**（⏸️）· 合计活跃 **36**

---

###### **P0 · 立即执行（#1 = 最高优先级，按序做）**

| # | 状态 | ID | 待办 | 验收档 | 备注 |
|---|---|---|---|---|---|
| 1 | `[x]` | T-3-9 | `validation/` 目录规范 + README | E, VAL-1 | 2026-06-17 ✅ |
| 2 | `[ ]` | T-3-10 | `validate_gate.py` 八类必检 + checks.json（⚠️ 7/8 项 v1） | E, VAL-2~4 | 依赖 #1 ✅ |
| 3 | `[x]` | T-3-11 | promote：PASS → 根目录正式产物 + run_id | E, VAL-6 | 2026-06-17 ✅ |
| 4 | `[x]` | T-3-12 | skill 强制「先 validate 后 publish」 | E, VAL-5 | 2026-06-17 ✅ |
| 5 | `[x]` | T-5-1 | 玩法全量扫描（**六类** × 当期场次 → 候选池） | C-1 | scan_candidates.py ✅ |
| 6 | `[x]` | T-5-2 | Top 6 入围排序 + 决策报告 Top6 表 | C-2 | rank_top6 ✅ |
| 7 | `[x]` | T-5-3 | 二次评估四维打分（§2.4.2 公式） | C-3 | lib ✅ |
| 8 | `[x]` | T-5-4 | **主推 1 套**输出（funnel.hero → 正式报告） | C-3 | 2026-06-17 ✅ generate + promote |
| 9 | `[x]` | T-6-2 | 决策 HTML `.top6` 表 + 行联动 | D, UX-2 | 2026-06-17 ✅ 模板+script |
| 10 | `[x]` | T-6-1 | 决策 HTML `.hero-pick` 英雄区 | D, UX-1 | 2026-06-17 ✅ 模板 |
| 11 | `[x]` | T-6-3 | DECISION_HTML_TEMPLATE / GUIDE → v2.0 | D | 2026-06-17 ✅ |
| 12 | `[x]` | T-4-9 | 赛后复盘自动化 → tracking + 复盘 UI | C-5, UX-6 | 2026-06-17 ✅ replay_decision.py |
| 13 | `[ ]` | T-1-6 | 近 10 场胜率稳定满 10 场（⚠️） | A 前提 | ESPN 5 场 + DB 合并 |
| 14 | `[ ]` | T-1-17 | 赛前 2h 伤病/阵容增量（⚠️） | A 前提 | cron 可跑；伤停源仍缺 |

**P0 推荐泳道**（同一 `#` 可并行，下一 `#` 依赖上一组 PASS）：

```
#1→#4  门禁（E 档）     #5→#8  6 进 1 逻辑（C 档）     #9→#11 交互 v2.0（D 档）
                              #12 复盘（C-5）           #13–#14 数据收尾（可穿插）
```

---

###### **P1 · 次优先（P0 #1–#11 核心闭环后）**

| # | 状态 | ID | 待办 | 验收档 | 备注 |
|---|---|---|---|---|---|
| 15 | `[ ]` | T-2-5 | skill 强制引用 `prediction_*.json` | C-3 | 与 T-5-6 同批 |
| 16 | `[ ]` | T-5-6 | 预测引擎一致度分接入二次评估 | C-3 | 依赖 #15 |
| 17 | `[x]` | T-5-5 | Top6 / 主推 / 被砍注虚拟收益跟踪 | C-5 | 2026-06-17 ✅ virtual_tracking.py |
| 18 | `[ ]` | T-6-4 | 空单 / 缩量 / 赛后三态 UI 齐全（⚠️） | D, UX-3/6 | 赛后态 ✅；空单/缩量待补 |
| 19 | `[x]` | T-4-11 | 被砍注虚拟跟踪列 | C-5 | 合并入 T-5-5 ✅ |
| 20 | `[ ]` | T-4-10 | 用户外部方案评估模式 | — | ROADMAP |
| 21 | `[ ]` | T-4-12 | 跨市场矛盾自动检测 | — | ROADMAP |
| 22 | `[ ]` | T-4-16 | odds-analyst 自动调用 score_fundamentals | — | ROADMAP |
| 23 | `[ ]` | T-3-4 | ≥5 期样本后权重调参闭环（⚠️） | A | 样本不足，触发后做 |
| 24 | `[ ]` | T-6-5 | `prefers-reduced-motion` 全局降级 | D, UX-4 | §4.6 |
| 25 | `[ ]` | T-2-6 | 基本面信号与 PRD 五维并存说明（⚠️） | — | 对照文档 |
| 26 | `[ ]` | T-1-10 | 主力伤病名单（俱乐部场景验证） | A 增强 | 国家队仍缺源 |
| 27 | `[ ]` | T-1-9 | 本届主力阵型 | A 增强 | 国家队 ESPN 无 |
| 28 | `[ ]` | T-1-13 | 小组赛出线形势 | A 增强 | 需积分榜 |

---

###### **P2 · 增强（有余力再做）**

| # | 状态 | ID | 待办 | 备注 |
|---|---|---|---|---|
| 29 | `[ ]` | T-3-8 | 投注追踪档案扩至 PRD 量级（⚠️） | 现 2 期 / 7 注 |
| 30 | `[ ]` | T-6-6 | 预测 HTML 方案卡 Top1 高亮 | 预测页 polish |
| 31 | `[ ]` | T-1-8 | 世界杯淘汰赛历史晋级率 | 需历史库 |
| 32 | `[ ]` | T-1-11 | 核心球员大赛进球/助攻效率 | 需球员 API |
| 33 | `[ ]` | T-1-12 | 球队红黄牌累计 | 需赛事统计源 |
| 34 | `[ ]` | T-1-14 | 气候/海拔适应 | venue 元数据 |
| 35 | `[ ]` | T-1-15 | 国际足联/欧足联权威历史统计 | 独立数据源 |
| 36 | `[ ]` | T-4-13 | 5/10 期骨架自动评审 | ROADMAP P2 |
| 37 | `[ ]` | T-4-14 | 盘口漂移方向意义分析 | ROADMAP P2 |
| 38 | `[ ]` | T-4-17 | `require_fundamentals` 是否改回 true | **待用户确认** |

---

###### **P3 · 本期不做（⏸️ 不纳入活跃迭代）**

| ID | 说明 | 何时再议 |
|---|---|---|
| T-3-1 / T-3-2 | 历史 100 场回测 · 需赛前快照库 · 本届 WC 不适用 | 2026 赛后或下一届大赛前 |
| T-4-15 | xG / ELO / 自训 ML | PRD 非目标，明确不做 |

> P2 #38（T-4-17）若长期无结论，可下调为 P3；当前保留 P2 待用户确认。

---

###### **验收档 ↔ 优先级映射（摘要）**

| 档位 | 未满足项 | 关联 TODO（按优先级） |
|---|---|---|
| **E 档** | 目录隔离 · 八类必检 · promote · skill 约束 | P0 #1–#4 |
| **C 档** | 五类扫描 · Top6 · 主推 · 复盘 · 虚拟跟踪 | P0 #5–#8、#12；P1 #15–#17、#19 |
| **D 档** | hero/top6 · 三态 UI · reduced-motion · 移动 | P0 #9–#11；P1 #18、#24 |
| **A 档** | 权重调参 · 数据字段补全 | P0 #13–#14；P1 #23、#26–#28 |

---

##### **模块 0 · PM 编排（v1.4）**

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-0-1 | PM Agent skill（三阶段调度约定） | P0 | ✅ | `football-pm-orchestrator/SKILL.md` |
| T-0-2 | 阶段 1 输入门禁（odds + fundamentals） | P0 | ✅ | `workflow_lib.validate_inputs` + phase 1 |
| T-0-3 | 一键编排 CLI `run_workflow.py` | P0 | ✅ | 阶段 1→2→3 串联 |
| T-0-4 | `prefetch.sh workflow` 入口 | P1 | ✅ | `scripts/prefetch.sh workflow` |
| T-0-5 | 阶段 4 文档对账（PRD ↔ 代码） | P0 | ✅ | `.cursor/rules/football-prd-doc-parity.mdc` + PM skill 阶段 4 |

---

##### **模块 1 · 数据获取**

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-1-1 | 体彩官方赔率、让球、比分、总进球、**半全场**抓取 | P0 | ✅ | `fetch_odds.py`；含 24h 窗口 `odds_window_24h_*` + diff |
| T-1-2 | 国际盘对照（体彩 vs OddsPortal） | P1 | ✅ | `football-intl-comparator` skill；`compare_intl_*.html` |
| T-1-3 | 近 5 场球队状态（W/D/L） | P0 | ✅ | `fetch_fundamentals.py`（ESPN） |
| T-1-4 | 对战历史 H2H | P0 | ✅ | 2026-06-16 · `h2h_last_three` + `predict_lib` 时间衰减 |
| T-1-5 | 基本面 DB 累积与查询 | P1 | ✅ | `fundamentals_db.json` / `query_fundamentals.py` / `backfill_fundamentals.py` |
| T-1-6 | 近 10 场胜率 | P0 | ⚠️ | 2026-06-16 · `last_ten_games`（ESPN 5 场 + DB 合并，满 10 场才稳定） |
| T-1-7 | 近 5 场场均进球 / 失球 | P0 | ✅ | 2026-06-16 · `team_stats.avg_gf/avg_ga` in `fetch_fundamentals.py` |
| T-1-8 | 世界杯淘汰赛历史晋级率 | P2 | ❌ | 需历史赛事数据库 |
| T-1-9 | 本届主力阵型 | P1 | ❌ | 国家队场景 ESPN 无；俱乐部未测 |
| T-1-10 | 主力伤病名单 | P0 | ❌ | 国家队无覆盖；俱乐部待验证 |
| T-1-11 | 核心球员大赛进球 / 助攻效率 | P2 | ❌ | 需球员统计 API |
| T-1-12 | 球队红黄牌累计 | P2 | ❌ | 需赛事统计源 |
| T-1-13 | 小组赛出线形势 | P1 | ❌ | 需积分榜 / 赛程计算 |
| T-1-14 | 赛事举办地气候 / 海拔适应 | P2 | ❌ | 需 venue 元数据 + 历史表现 |
| T-1-15 | 国际足联 / 欧足联权威历史统计 | P2 | ❌ | 独立数据源，非 ESPN 替代 |
| T-1-16 | 赛前 24h 全量自动更新 | P0 | ✅ | 2026-06-16 · `scripts/prefetch.sh` + `com.football.prefetch.plist` + `SCHEDULE.md` |
| T-1-17 | 赛前 2h 伤病 / 阵容增量更新 | P0 | ⚠️ | 2026-06-16 · cron 可跑 `prefetch fundamentals`；伤停数据仍缺 |
| T-1-18 | H2H 时间衰减（5y/10y 分段权重） | P1 | ✅ | 2026-06-16 · `weights.yaml` + `predict_lib.score_h2h_dimension` |

---

##### **模块 2 · AI 决策（PRD 预测引擎）**

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-2-1 | 五维权重评分引擎 v1（30/25/20/15/10） | P0 | ✅ | 2026-06-16 · `predict_lib.py` |
| T-2-2 | 组合方案生成器（3–5 套：胜平负 + 总进球 + 比分） | P0 | ✅ | 2026-06-16 · `predict_lib.generate_schemes` |
| T-2-3 | 权重模型配置文件（可调维度权重） | P1 | ✅ | 2026-06-16 · `weights.yaml` |
| T-2-4 | 预测结果落盘（JSON + Markdown / HTML） | P1 | ✅ | 2026-06-16 · `predict_engine.py` → `prediction_*.{json,md,html}` |
| T-2-5 | 与现有 EV Agent 集成（预测层 + 资金层分离） | P1 | ⚠️ | 2026-06-16 · 文档约定见 `docs/【技术】预测引擎v1.md`；skill 未自动引用 |
| T-2-6 | 基本面信号评分（非 PRD 权重，对照用） | P1 | ⚠️ | `score_fundamentals.py` 保留；PRD 主路径已切到 `predict_lib` |
| T-2-7 | 组合方案逻辑说明自动生成 | P0 | ✅ | 2026-06-16 · 每套方案 `logic` 字段 |

---

##### **模块 3 · 测试与数据验证**

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-3-1 | 历史回测框架（100 场样本 → 准确率报告） | P0 | ⏸️ | 框架在 `backtest/run_backtest.py`；**本届 WC 不启用**（赛果已知=非盲测） |
| T-3-2 | 回测样本清单（100 场档案） | P0 | ⏸️ | 30 场种子仅作开发调试；**不扩为本届验收项** |
| T-3-3 | 2026 世界杯每日 forward 模拟 | P0 | ✅ | `daily_simulate.py` → `simulation/`（**赛前写、赛后结算**） |
| T-3-3b | 模拟赛后结算 + 命中统计 | P0 | ✅ | 2026-06-16 · `settle_simulation.py` → `simulation/prediction_tracking.md` |
| T-3-4 | 权重模型优化闭环（回测 / 模拟 → 调参） | P1 | ⚠️ | 框架就绪；待 ≥5 期样本后再调 `weights.yaml` |
| T-3-5 | 异常场景测试：核心球员赛前伤退 | P1 | ✅ | 2026-06-16 · `backtest/test_scenarios.py` |
| T-3-6 | 异常场景测试：球队生死战抢分 | P1 | ✅ | 2026-06-16 · `backtest/test_scenarios.py` |
| T-3-7 | 异常场景测试：历史交锋平局率高 | P1 | ✅ | 2026-06-16 · `backtest/test_scenarios.py` |
| T-3-8 | 投注追踪档案（手工期汇总） | P2 | ⚠️ | `tracking.md`；2 期 / 7 注，远未达 PRD 量级 |
| T-3-9 | `validation/` 目录规范 + README | P0 | ✅ | 2026-06-17 · `validation/README.md` + drafts/runs/latest |
| T-3-10 | `validate_gate.py` 八类必检项 | P0 | ⚠️ | 2026-06-17 · `validation_lib.py` + `validate_gate.py`；7 项 v1，EV 复算/决策自洽待补 |
| T-3-11 | promote 正式产物 + validation_run_id 追溯 | P0 | ✅ | 2026-06-17 · `--promote` / `--promote-prediction` · `promote.json` |
| T-3-12 | skill 发布流程嵌入门禁（先 validate 后 publish） | P0 | ✅ | SKILL 步骤 8 + STRATEGY validation 块 |

---

##### **模块 5 · 下注决策（6 进 1 · PRD 正式需求）**

> 模块 4 提供基础设施；本模块补齐 PRD **「Top 6 → 二次评估 → 推荐 1 套」** 的正式闭环。

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-5-1 | 玩法全量扫描器（**六类**玩法 × 当期场次 → 候选池） | P0 | ✅ | `scan_candidates.py` + lib |
| T-5-2 | Top 6 入围排序（EV 降序 + tie-break 规则） | P0 | ✅ | `rank_top6()` |
| T-5-3 | 二次评估打分（EV 40% + 引擎 25% + 基本面 20% + 独立性 15%） | P0 | ✅ | `rank_top6()` dims |
| T-5-4 | 最终推荐 1 套输出（主推区块 + 金额 + 理由） | P0 | ✅ | `generate_decision_draft.py` + `decision_*_FUNNEL_REGEN.*` |
| T-5-5 | Top6 / 主推 / 被砍注 虚拟跟踪 | P1 | ✅ | `virtual_tracking.py` + `tracking.md` 虚拟段 |
| T-5-6 | 预测引擎强制引用（`prediction_*.json` → 一致度分） | P1 | ⚠️ | 同 T-2-5；引擎已有，skill 未接 |
| T-5-7 | Top3 赢利方案输出（命中毛奖金排序 + 方案 A/B/C 卡片） | P0 | ✅ | `rank_top3_picks` + decision 草案 Top3 表 |
| T-5-8 | 单关组合单生成（3–4 注 · 金额分配 · 互斥提示） | P0 | ✅ | `portfolio_lib.build_defensive_portfolio` |
| T-5-9 | 防御/进攻双方案 + EV 加权分配 + **自动择优** | P0 | ✅ | `portfolio_lib.select_portfolio_plan` · v2.2 决策卡 |

**当前差距（2026-06-18 更新）**：

| 能力 | 目标 | 现状 |
|---|---|---|
| PM 编排 | 三阶段顺序 + 阶段门禁 | ✅ `run_workflow.py` + `football-pm-orchestrator` skill |
| 输出形态 | Top3 + **主推组合单**（非串关） | ✅ MD `#portfolio-ticket` + 行动卡 B1–B4 |
| 资金策略 | 单下或组合 · 200 元满预算 · 自动稳/攻 | ✅ T-5-9；IMP-006 缩量 **已驳回** |
| 入围数量 | Top **6** | EV 闸后常剩 **4** 注 |

---

##### **模块 6 · 交互设计**

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-6-1 | 决策 HTML v2.0：`.hero-pick` 主推英雄区 | P0 | ✅ | `DECISION_HTML_TEMPLATE.html` v2.0 |
| T-6-2 | 决策 HTML v2.0：`.top6` 表 + 行联动高亮 | P0 | ✅ | 模板 + 内联 script；draft `decision_260616_v2_FROM_TEMPLATE.html` |
| T-6-3 | 区块顺序升级（DECISION_HTML_GUIDE v2.0） | P0 | ✅ | GUIDE v2.0 + SKILL 步骤 7 更新 |
| T-6-4 | 空单 / 缩量 / 赛后 三态 UI | P1 | ⚠️ | 赛后色变 ✅（T-4-9）；空单/缩量部分有 |
| T-6-5 | `prefers-reduced-motion` 全局降级 | P1 | ⚠️ | 模板已含；预测 HTML 待补 |
| T-6-6 | 预测 HTML 方案卡 Top1 高亮 | P2 | ❌ | `prediction_*.html` |
| T-6-7 | 决策 HTML `.top3-picks` 三卡并列（赢利 Top3 供选） | P0 | ✅ | `DECISION_HTML_TEMPLATE` v2.1 + `generate_decision_draft` |
| T-6-8 | 决策 HTML `#portfolio-ticket` 主推组合单表 | P0 | ✅ | `generate_decision_draft.render_portfolio_html` |

**已有资产（v2.0）**：hero-pick 金边区、Top6 漏斗表 + hover 联动、KPI 四卡动效、对阵 bar、**主推组合单区块**、主推结局条、`prefers-reduced-motion` 降级、`.num` 等宽数字。

---

##### **模块 4 · 现有工具链（EV Agent 基础设施，支撑模块 5）**

> 以下能力已落地，作为模块 5 的实现基础；模块 5 补齐「6 进 1」正式 PRD 闭环。

| ID | 任务 | 优先级 | 状态 | 产物 / 备注 |
|---|---|---|---|---|
| T-4-1 | 盘口 V2 分析报告 Agent | — | ✅ | `football-odds-analyst` skill |
| T-4-2 | 投注决策 Agent（EV 闸 + 资金分配） | — | ✅ | `football-betting-strategist` skill |
| T-4-3 | 决策 HTML 可视化 | — | ✅ | `decision_*_<时间>.html` |
| T-4-4 | 策略骨架 PLAYBOOK（A/B/C/D/E） | — | ✅ | `PLAYBOOK.md` + `STRATEGY_DEFAULT.yaml` |
| T-4-5 | 盘口漂移 diff 落盘 | — | ✅ | `diffs/diff_*.json` |
| T-4-6 | 基本面快照 Markdown（贴 V2 第 8 节） | — | ✅ | `fundamentals_*.md` |
| T-4-7 | 基本面信号 HTML 可视化 | — | ✅ | `scores_*.html` |
| T-4-8 | 国际盘双源加权（CN×0.4 + INTL×0.6） | — | ✅ | intl-comparator 报表内 |
| T-4-9 | 赛后复盘自动化（找 decision → 算盈亏 → 更新 tracking） | P0 | ✅ | `replay_decision.py` + `【技术】复盘自动化v1.md` |
| T-4-10 | 用户外部方案评估模式 | P1 | ❌ | ROADMAP P0-3 |
| T-4-11 | 被砍注虚拟跟踪列 | P1 | ✅ | 并入 T-5-5 `被砍样本` 类 |
| T-4-12 | 跨市场矛盾自动检测 | P1 | ❌ | ROADMAP P1-2 |
| T-4-13 | 5/10 期骨架自动评审 | P2 | ❌ | ROADMAP P2-1 |
| T-4-14 | 盘口漂移方向意义分析 | P2 | ❌ | ROADMAP P2-2 |
| T-4-15 | xG / ELO / 自训 ML 模型 | — | ⏸️ | ROADMAP P3-1，明确不做 |
| T-4-16 | odds-analyst 自动调用 score_fundamentals | P1 | ❌ | ROADMAP P0-2 v0.4 待决 |
| T-4-17 | `require_fundamentals` 是否改回 true | P2 | ❌ | ROADMAP 待用户确认 |

---

##### **里程碑与验收对照**

| 里程碑 | 包含任务 | 目标日期 | 状态 |
|---|---|---|---|
| **M1 · 数据基座** | T-1-1 ~ T-1-7/16/18 | — | ✅ 基本完成（T-1-6/17 部分） |
| **M2 · 预测引擎 v1** | T-2-1 → T-2-2 → T-2-4 | — | ✅ 已完成 |
| **M3 · 回测验收** | T-3-1/3-2 | — | ⏸️ **延后**（无赛前档案，不宜用已知赛果验收） |
| **M3b · 数据验证门禁** | T-3-9 → T-3-12 | — | ✅ **完成**（VAL-3/4 扩展待做） |
| **M4 · 世界杯实战** | T-3-3 + T-3-3b | 2026 世界杯 | ✅ **可闭环**（赛前 sim → 赛后 settle） |
| **M5 · 异常场景** | T-3-5 ~ T-3-7 | — | ✅ 已完成 |
| **M6 · 下注决策 6 进 1** | T-5-1 → T-5-4 | — | ✅ **闭环**（260616 正式报告已 promote） |
| **M7 · 交互体验 v2.0** | T-6-1 → T-6-3 | — | ✅ **模板完成**（260616 FUNNEL 正式报告已 promote + 复盘演示） |

---

##### **推荐开发顺序（下一迭代）**

> 与 **TODO P0 #1–#14** 一致；P1 见 #15 起；**P3 不做**。

```
【当前起点】P1 #15  T-2-5 / T-5-6  预测引擎 skill 强制引用 · 或 P0 #13 近 10 场胜率

P0 泳道 A · E 档门禁     #1 ✅ #2 ⚠️ #3 ✅ → #4
P0 泳道 B · C 档 6 进 1   #5 → #6 → #7 → #8        （#4 PASS 后再 promote 正式报告）
P0 泳道 C · D 档交互 v2   #9 ∥ #6 ；#10 → #11      （依赖 #8）
P0 泳道 D · 复盘/数据     #12 ∥ ；#13–#14 可穿插

──────── P0 核心闭环（#1–#11）完成后 ────────

P1 首批                 #15–#16 预测引擎接入 → #17+#19 虚拟跟踪 → #18+#24 三态/reduced-motion
P2 / P3                 #29 起 · 有余力再做 · P3 本期跳过
```

---

##### **变更日志**

| 日期 | 变更 |
|---|---|
| 2026-06-16 | 初版：基于 PRD 与项目现状差距分析，拆分 32 项 PRD 核心任务 + 16 项 EV Agent 并行任务 |
| 2026-06-16 | **v1 落地**：predict_lib / predict_engine / weights.yaml / backtest / daily_simulate / prefetch 调度；PRD 核心 17 项 ✅ |
| 2026-06-16 | **验收策略修订**：本届 WC 样本少且赛果已知 → 改 A 档 forward 模拟为主路径；历史 100 场回测 ⏸️ 延后 |
| 2026-06-16 | **T-3-3b 落地**：`settle_simulation.py` + `simulation/prediction_tracking.md` |
| 2026-06-17 | **下注决策模块纳入 PRD**：新增模块 4（功能描述）、C 档验收、模块 5 任务 T-5-1~6；明确「全玩法扫描 → Top 6 → 二次评估 → 推荐 1 套」漏斗；模块 4 重定位为 EV Agent 基础设施 |
| 2026-06-17 | **交互设计规范纳入 PRD**：新增第四节 + D 档验收 + 模块 6 任务 T-6-1~6；定义 `.hero-pick` / `.top6` v2.0 决策卡标准 |
| 2026-06-17 | **PRD v1.2 结构整理**：§0 文档元数据 · 非目标 · 用户场景 · 量化公式 · 章节重排（三四互换） |
| 2026-06-17 | **移除 PRD 内评审章节**；需求追溯与风险表并入 §五 |
| 2026-06-17 | **TODO 活跃清单**：§五 新增 #1–34 未完成项 + 验收档映射；修正模块 5/6 进度计数 |
| 2026-06-17 | **v1.3 数据验证门禁**：§2 模块 3 拆为效果验证 + 门禁；新增 E 档验收 + T-3-9~12；`validation/` 与正式报告目录隔离；发布顺序「先 PASS 后 promote」 |
| 2026-06-17 | **v1.3.1 TODO 重排**：活跃清单统一 P0→P3 四级；全局序号 #1–#38；P3 明确本期不做；与模块任务表优先级对齐 |
| 2026-06-17 | **T-3-9/10 落地**：`validation/` · `validate_gate.py` · `validation_lib.py` · 自测通过；TODO #1 ✅ #2 部分 |
| 2026-06-17 | **T-3-11 落地**：`--promote` / `--promote-prediction` · `promote.json` · 正式产物写入 validation_run_id；TODO #3 ✅ |
| 2026-06-17 | **T-6-1~3 落地**：`DECISION_HTML_TEMPLATE` v2.0（hero + top6 + script）· `DECISION_HTML_GUIDE` v2.0 · draft `validation/drafts/decision_260616_v2_FROM_TEMPLATE.html`；TODO #9–#11 ✅ |
| 2026-06-17 | **T-3-12 落地**：SKILL 步骤 8 门禁 + `drafts_dir` · `validation.require_gate_before_publish`；TODO #4 ✅ |
| 2026-06-17 | **T-5-1~3 落地**：`scan_candidates.py` · 260616 演示 231 候选五类全覆盖 · `【技术】玩法扫描与6进1漏斗v1.md`；TODO #5–#7 ✅ |
| 2026-06-17 | **T-5-4 落地**：`generate_decision_draft.py` · 正式 `decision_260616_match017_FUNNEL_REGEN.{md,html}` · run_id=20260617-202739；TODO #8 ✅ |
| 2026-06-17 | **T-5-5 / T-4-11 落地**：`virtual_tracking.py` · 260614 演示（被砍总进球6球虚拟+1400）· `tracking.md` 虚拟段；TODO #17 #19 ✅ |
| 2026-06-17 | **v1.4 PM 编排工作流**：新增 §2 模块 0（三阶段 PM 调度 + 阶段门禁）；下注层由「6 进 1」扩展为 **Top3 赢利方案供选**；任务 T-0-1~4 · T-5-7 |
| 2026-06-18 | **v1.5 文档对账**：PM 阶段 4 · Rule `football-prd-doc-parity` · 24h `odds_window_24h` · 半全场扫描 · F 档复盘约定 · PRD 进度/差距表与实现对齐 |
| 2026-06-18 | **复盘 Agent 独立落地**：`.cursor/skills/football-replay-analyst`（L2 评分 + backlog；**不挂** PM 编排）· `【技术】复盘Agent v1.md` |
| 2026-06-18 | **T-5-8/9 落地**：`portfolio_lib.py` · 防御/进攻双方案 · EV 加权分配 · 自动择优 · 决策卡 `#portfolio-ticket` + 行动卡 B1–B4 |
| 2026-06-18 | **策略闸 IMP-006 驳回**：用户接受满预算 200 · `catastrophic_shrink_factor=1.0` · backlog 更新 |
| 2026-06-18 | **v1.6 文档对账**：PRD · `【产品】Agent工作流总览` · `【技术】玩法扫描` · PM/strategist skill 同步 |

---

##### **需求追溯矩阵（摘要）**

| 业务需求 | 验收档 | 任务 | 里程碑 |
|---|---|---|---|
| 数据基座 | A/E 档前提 | T-1-* | M1 ✅ |
| 数据可复算 / 防幻觉 | E 档 | T-3-9~12 | M3b |
| 预测 3–5 套组合 | A 档 | T-2-1~2-4 | M2 ✅ |
| 全玩法 → Top 6 | C 档-1/2 | T-5-1, T-5-2 | M6 |
| 6 进 1 主推 | C 档-3 | T-5-3, T-5-4 | M6 |
| 单关组合单 + 自动择优 | C 档-3c | T-5-8, T-5-9 | M6 |
| Top3 供选 | C 档-3b | T-5-7, T-0-3 | M6 |
| PM 三阶段编排 | E 档前提 | T-0-1~3 | M6 |
| 3s 见主推 | D 档-1, UX-1 | T-6-1 | M7 |
| Top6 可视化 | D 档-2, UX-2 | T-6-2 | M7 |
| 合法空单 | C 档-4, UX-3 | T-5-4, T-6-4 | M6/M7 |
| 赛后复盘 | C 档-5 | T-4-9, T-5-5, **football-replay-analyst** | M6 |

##### **风险与假设**

| 类型 | 内容 | 缓解 |
|---|---|---|
| **假设** | 体彩赔率 API 持续可用 | `fetch_odds.py` + diff 监控 |
| **假设** | 国家队伤停短期无稳定源 | 标记缺失 + 半权重，不阻塞 A 档 |
| **风险** | Agent 叙述与源 JSON 不一致（幻觉） | E 档门禁 T-3-10；FAIL 不 promote |
| **风险** | 验证产物与正式报告混放导致误读 | `validation/` 目录隔离 + VAL-1 |
| **风险** | 样本 <20 无法验 ROI | C 档不做 ROI 硬门槛；虚拟跟踪 T-5-5 |
| **风险** | Top6 常不足 6（EV 闸） | 如实输出 + 被砍统计；不凑数 |
| **风险** | 预测层与下注层结论冲突 | 二次评估 Engine_align 25% 权重；文档说明双轨 |
| **依赖** | `STRATEGY_DEFAULT.yaml` 阈值 | PRD 阈值表与 yaml 同步变更 |