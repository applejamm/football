# Agent 演进路线图

> 沉淀 2026-06-14 一晚关于 `football-odds-analyst` + `football-betting-strategist` 两个 agent 的关键结论与后续工作。
> **新增工作前必须先看这份文档**，避免重复劳动 / 推翻已达成的边界认知。

---

## 一、核心认知（不要再讨论的事实）

### 1.1 Agent 的真实定位

**当前 agent = 资金效率优化器，不是胜率提升器。**

- 它在"市场赔率 ≈ 真实概率"的前提下做资金分配
- 它不看球（伤停 / 首发 / 战术 / 状态）
- 它砍水深的注、保留水浅的注，但不挑战市场判断本身

### 1.2 体彩竞彩的数学命运（不会变的事实）

| 市场 | 抽水率 | 平均 EV | 含义 |
|---|---|---|---|
| 让球 / 胜平负 | 11.4% | **−11.5%** | 浅水 |
| 总进球数 | 20.3% | **−20%** | 中水 |
| 比分单关 | 29% | **−29%** | 深水 |
| 比分 2 串 1 | 49% | **−50%** | 极深水 |

**结论**：体彩**所有注都是负 EV**。任何工具的目标只能是"少亏"，不可能是"赚"。

### 1.3 Agent 能力边界

| 能 ✅ | 不能 ❌ |
|---|---|
| 去水概率换算 | 估计真实概率（依赖市场） |
| EV 计算 + 闸过滤 | 基本面分析 |
| 相关性聚合（独立判断单元数） | 战术匹配 / 主客场调整 |
| 资金分配（A/B/C/D/E 五骨架） | 球员能力建模 |
| 三档情境（最坏 / 中性 / 最好） | xG / ELO / ML 预测 |
| HTML 决策卡可视化（对阵对比 + 注单胜率 bar + 结局条） | 实时盘口异动告警 |

---

## 二、已建成的产物（截至 2026-06-14）

```
.cursor/skills/
├── football-pm-orchestrator/      PM：三阶段编排（数据→分析→Top3决策）
│   └── SKILL.md                   调度 fetch / predict / scan / validate
├── football-odds-analyst/         分析师：盘口 → V2 报告
│   ├── SKILL.md                   （含步骤 1.5 / 3.4 国际盘对照引用）
│   └── V2_TEMPLATE.md            
├── football-betting-strategist/   策略师：V2 + YAML → 决策（含 HTML v2.1 Top3）
│   ├── SKILL.md                   步骤 7 强制读 HTML 模板 + 指南
│   ├── STRATEGY_DEFAULT.yaml      用户偏好
│   ├── DECISION_TEMPLATE.md       Markdown 决策（含 §4 对阵基本面表）
│   ├── DECISION_HTML_TEMPLATE.html  HTML CSS/结构权威源（v2.1 hero + top3 + top6）
│   ├── DECISION_HTML_GUIDE.md     区块顺序、bar 算法、自检清单
│   └── PLAYBOOK.md                5 种骨架细节
├── football-intl-comparator/      国际盘对照：体彩 vs OddsPortal 多家最高赔率
│   ├── SKILL.md                   （浏览器 MCP 抓取 + 双源去水 + HTML 报表）
│   ├── HTML_TEMPLATE.md           对照报表 HTML 骨架与占位符规则
│   └── TEAM_MAPPING.md            中文 ↔ OddsPortal 英文队名映射表
└── openclaw-skills-football-data/ 第三方 lobehub skill（已装但未启用）
    └── SKILL.md                   备用：俱乐部赛事场景下能拉首发/伤停/xG

football/
├── run_workflow.py                PM 一键编排 CLI（T-0-3）
├── workflow_lib.py                三阶段共享逻辑 + Top3 状态
├── validation/workflow/           每期 workflow 状态 JSON
├── analysis_*_v2.md               历史 V2 报告
├── decision_*_<时间>.md/.html     历史决策（事前快照）
├── fetch_odds.py                  盘口抓取
├── fetch_fundamentals.py          v0.2 基本面拉取（ESPN + 自动 upsert 到 DB）
├── backfill_fundamentals.py       从 fundamentals_*.json 重建 DB（幂等）
├── query_fundamentals.py          按球队 / 比赛查 DB
├── score_fundamentals.py          B 路信号评分 + 与市场盘对照（HTML 可视化）
├── fundamentals_*_<时间>.json/.md 基本面快照（同 fetch_odds 风格命名，事实证据）
├── fundamentals_db.json           累积索引：snapshots / matches / teams
├── fundamentals/teams/<name>.json 单队历史（按抓取时间累积，幂等 upsert）
├── scores_*_<日期>_<时间>.json    基本面信号评分（衍生分析，不进 DB）
├── scores_*_<日期>_<时间>.html    可视化对比页（自包含、可离线打开）
├── compare_intl_<code>_<时间>.html  体彩 vs 国际盘对照报表（OddsPortal 数据源）
└── AGENT_ROADMAP.md               本文档
```

**默认策略**：A 骨架 / 200 元上限 / require_fundamentals=false / auto_invoke_analyst=true。

---

## 三、第一次实战回测（260613 周六 006）

| 项 | 值 |
|---|---|
| 比赛 | 巴西 vs 摩洛哥 |
| Agent 决策 | S1 巴西胜 100 / M1 让−1 平 50 / M2 让−1 胜 50（共 200） |
| 实际比分 | **1:1** |
| 实际收益 | **−200**（落入"平局 24.6%" 概率档） |
| 用户原方案 | 100 元巴西胜单关 → **−100** |

**关键发现**：
1. Agent 比用户原方案多亏 100 元（A 骨架放大单期亏损是已知代价）
2. 被 agent 砍掉的注里有赢家：比分 1:1（赔 6.05）实际命中
3. 这**不证明 EV 闸错**——单期翻盘 ≠ 方法论错；要看 5~10 期累计
4. Agent 事前已经预警了 40.6% 全输概率，结果落入这一档不奇怪

---

## 四、待办路线图（按优先级）

### 🥇 P0 · 必做（短期内）

#### P0-1 · 复盘 agent（工作流闭环）· **✅ 2026-06-18 skill 已建**

**问题**：agent 工作流「上半场（事前）」完整，「下半场（事后）」缺独立评分 Agent。

**做法（已落地）**：
- ✅ 新建 **独立** skill：`.cursor/skills/football-replay-analyst/SKILL.md`（**不挂** `football-pm-orchestrator`）
- ✅ L1：`replay_decision.py` 记账（tracking / decision 赛后态）
- ✅ L2：双 Agent 评分 + `replay/replay_report_*.md` + `improvements_backlog.md`
- ✅ 技术 doc：`docs/【技术】复盘Agent v1.md`
- 入口：「复盘 260616」「@football-replay-analyst」、loop 赛后触发
- `football-betting-strategist` 步骤 10 委托本 Agent

#### P0-2 · 基本面自动采集（提胜率 = 少亏）· **v0.1 已落地**

**v0.1 状态（2026-06-14 22:30 实测）**：
- ✅ 写了 `football/fetch_fundamentals.py`（0 依赖，ESPN 公开 API）
- ✅ 跑通今晚 009/010 国家队场景
- ⚠️ **国家队覆盖度有限**：5 项里只稳定拉到 1 项（近 5 场）+ 3 项辅助（共识赔率 / H2H / 赛前新闻）
- ❌ 国家队场景下 ESPN 不返回 rosters / 伤停 / 首发 / 天气
- ❓ 俱乐部赛事场景未测（预期 4-5 项可拉，下次出现五大联赛比赛时打样）
- ❌ 暂未集成到 odds-analyst：本期工作只拉信息，不做胜负平推断（用户明确指示）

**v0.1 实测发现（值得保留的信号）**：
- 日本对荷兰 H2H 4 战 3胜1平（最近 2013 年 2-2）+ 日本本身 5 连胜含击败英格兰苏格兰 → 与市场"日本胜 = 平局 = 26.2%"定价对照，**日本胜是潜在被低估方向**
- 德国 5 连胜 vs 库拉索连输 4-1/5-1/4-1 → 验证市场"德国净胜≥4 球 52.1%"判断
- DraftKings 让球比体彩深（GER -3.5 vs 体彩 GER -3；NED -0.5 vs 体彩 NED -1）→ 海外大盘对客队负面更激进，但信号偏弱

**v0.2 状态（2026-06-14 22:38 落盘升级）**：
- ✅ `fundamentals_db.json` 累积索引（snapshots / matches / teams 三张表）
- ✅ `fundamentals/teams/<name>.json` 单队历史（每次抓取一条记录，按时间升序）
- ✅ `fetch_fundamentals.py` 跑完自动 upsert（`--no-db` 可禁）
- ✅ `backfill_fundamentals.py` 一键从快照重建 DB（`--rebuild` 强制重建）
- ✅ `query_fundamentals.py` 查询：`--list` / `--team <name>` / `--match <event_id>` / `--json`
- ✅ Upsert 幂等性已验证：(snapshot_at, match_id) 主键重复时跳过追加
- ✅ ASCII 文件名转换：`Curaçao` → `Curacao.json`，跨平台稳定
- ✅ 实测样本：2 个快照 / 6 场比赛 / 12 支球队（260614 + 260615 国家队场景）

**v0.3 状态（2026-06-14 23:25 信号评分 + 可视化）**：
- ✅ `score_fundamentals.py` 选 B 路：**只出信号分，不出概率数字**
- ✅ 算法：form_score（5 场 W·3+D·1）+ h2h_advantage（home 视角胜负差） + DraftKings 反算市场 implied prob 去 vig
- ✅ 差异告警：composite ≥ ±20 且对应方市场 implied prob < 35% → 反向告警
- ✅ HTML 可视化：自包含、暗色主题、SVG 条形图、市场 vs 基本面双面板对比
- ✅ 落盘：scores_<league>_<日期>_<时间>.json + .html，与 DB 解耦（衍生物不污染事实层）

**v0.3 实测发现（保留警示）**：
- **009 德国 vs 库拉索**：composite +73，市场也定主队 90.9% → 一致 ✅（无信号）
- **010 荷兰 vs 日本**：composite **+21**（擦边阈值），市场定主队 45.7% → "一致看好主队"
  - **但日本 form 100 vs 荷兰 67，被 H2H 历史 +75（最近 2013 年）抵消**
  - 这暴露算法第一版的局限：H2H 等权问题，远期 H2H 不该跟"近 5 场"等权
  - **结论**：第一版对 010 的"看好主队" 比"基本面看好日本" 更可信吗？**不一定**——值得用户警觉

**P0-2 v0.4 待办**：
- ⚠️ H2H 时间衰减（最近 5 年权重 1.0，5-10 年 0.5，> 10 年 0.2）
- ⚠️ 主客场 buff（友谊赛默认中立，俱乐部场景启用 ±5）
- 等出现五大联赛比赛 → 装 sports-skills CLI → 验证国家队 vs 俱乐部覆盖度差异
- 决定要不要让 odds-analyst 步骤 3"跨市场叙事一致性" 自动调用 score_fundamentals 输出
- 决定要不要把 yaml `require_fundamentals` 改回 true
- DB 长大后（> 50 比赛）评估是否需要切到 SQLite

**预期效果（不变）**：长期亏损从 −23 元/期 → −12~15 元/期。**仍不能赚钱**。

#### P0-3 · 评估外部方案的能力
**问题**：用户经常截图自己组的方案问 "看一下这个策略如何"，agent 没有标准化的响应。
**做法**：
- 加一个新 skill 或在策略师里加"评估模式"
- 输入：用户方案描述（投注组合 + 金额 + 玩法）
- 输出：EV 评分表 + 闸过滤结果 + 优劣排序

### 🥈 P1 · 数据累积到 3~5 期后做

#### P1-1 · tracking.md 加"被砍注虚拟跟踪"列 ✅ 2026-06-17
**问题**：现在不知道 EV 闸到底救了你 vs 害了你。
**做法**：`virtual_tracking.py` — 主推 / Top6 / 被砍样本统一虚拟投注结算，写入 `tracking.md`。
**关键指标**：累计 N 期后，"被砍注虚拟收益 vs 实际下注收益" 的对比。

#### P1-2 · 跨市场矛盾检测
**问题**：当前 V2 第 3 节"跨市场叙事一致性" 是手写描述，没自动检测。
**做法**：自动算"让球预测的胜率 vs 比分加总的胜率 vs 总进球暗示的胜率"，标出偏差最大的方向。这种偏差可能是错价机会。

### 🥉 P2 · 数据累积到 5~10 期后做

#### P2-1 · 5/10 期自动骨架评审
**做法**：tracking 满 N 期触发"如果用 B/C/D/E 骨架会怎样"对照报告。

#### P2-2 · 盘口漂移深度分析
**问题**：当前 fetch_odds.py 已有 diff 数据，但 agent 只看变化幅度，没分析方向意义。
**做法**：把"被压热方向 vs agent 判断方向" 写进 V2 报告。

### ❌ P3 · 大概率不做

#### P3-1 · xG / ELO / 自训 ML 模型
**理由**：
- 数据源成本高（需付费 API 或长期爬虫）
- 工程量大（≥ 1 周）
- 即便做出来，预期 EV 提升 5~10pp 仍不足以转正
- 和"娱乐性消费"的核心定位不符

---

## 五、关键决策日志

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-06-14 | 默认骨架 E → **改 A** | E 骨架在体彩负 EV 全市场下永远输出 12 元小额，与用户 200 预算不匹配 |
| 2026-06-14 | `require_fundamentals: true → false` | 用户当前不熟悉伤停查询，闸太严会变成永远空单 |
| 2026-06-14 | `max_loss_per_round: 150 → 200` | 用户实际预算 |
| 2026-06-14 | `reject_below: -0.20`（保持） | 切割阈值，刚好把比分单关砍掉 |
| 2026-06-14 | HTML 决策卡作为工作流强制最后一步 | 用户要求可视化 |
| 2026-06-14 | **不**因为单期回测翻车调参 | 1 期样本 = 0 信息量，至少 5 期再评 |
| 2026-06-14 | 新建 `football-intl-comparator` 子 skill（**不**改 fetch_odds.py） | OddsPortal 无 API，浏览器抓取耗时 10x+；保持体彩主流程 < 2 秒，国际盘按需触发 |
| 2026-06-14 | 国际盘对照=**推荐但非强制** | 抓取可能失败（Cloudflare / 队名不匹配），不应阻塞 V2 报告；< 12 小时内的对照可复用 |
| 2026-06-14 | 双源加权= **CN×0.4 + INTL×0.6** | 国际锐盘水更浅（≈2~3% vs 体彩 11.5%），权重应高于体彩 |
| 2026-06-17 | **T-6-7 落地**：决策 HTML v2.1 `.top3-picks` 三卡并列 · 点击联动 Top6/hero |
| 2026-06-16 | **HTML 决策卡 v1.1**：对阵基本面对比 + 注单胜率 bar + 10 区块顺序固化 | 用户要求与 214200 金样例一致，写入 DECISION_HTML_* + SKILL 步骤 7 |

---

## 六、不要做的事（避免反复踩坑）

1. **不要因为单期输赢调骨架/参数**——至少 5 期才有信号。
2. **不要把"被砍的注这次中了" 当 EV 闸错的证据**——这是事后归因。
3. **不要承诺"提胜率 = 赚钱"**——基本面只能减半亏损，不能转正 EV。
4. **不要在金额建议里用情绪性表述**（"撑赔率""加重""搏一搏"）。
5. **不要简单按"N 注分散" 安抚自己**——按相关性聚合算"独立判断单元数"。
6. **不要把空单当失败**——E 骨架的空单是合法决策。
7. **不要绕过 reject_below 红线**——除非用户在 yaml 显式调高。

---

## 七、下次开工时的 onboarding（给未来的 agent / 我自己）

1. 看本文档 + tracking.md 的累计统计
2. 决定要做 P0 / P1 / P2 哪一项
3. 不要重新讨论"agent 能不能让你赚钱"——结论已定（不能，只能少亏）
4. 改任何 yaml 参数前看第五节"决策日志"，避免推翻已达成的判断
5. 任何新加的 skill / 步骤都要更新本文档第二节（已建成的产物）

---

> 维护者：用户 + agent 共同维护
> 上次更新：2026-06-16（HTML 决策卡 v1.1 · 对阵对比块固化到 betting-strategist skill）
