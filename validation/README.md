# 数据验证门禁 · `validation/`

> **E 档专用目录** — 与根目录正式 `prediction_*` / `decision_*` **严格隔离**。  
> 权威需求：`docs/prd.md` §2.3.2 · §三 E 档 · 任务 T-3-9~12。

## 为什么单独建目录

| 问题 | 门禁如何解决 |
|---|---|
| Agent 编造赔率 / 队名 | 草案与 `odds_*.json` 逐字段比对 |
| EV / p_true 算错 | 从源赔率复算，容差内才 PASS |
| 调试文件被当成正式报告 | FAIL 只落盘 `validation/runs/`，不 promote |
| 事后无法追溯 | 每次 run 有 `manifest.json` + sha256 |

## 目录结构

```
validation/
├── README.md           ← 本文件
├── .gitignore          ← runs/drafts 内容不入库
├── drafts/             ← 脚本写入的 **草案**（decision_*.json + .html），HTML 从 JSON 派生
│   ├── decision_260616_v2_MOCK.html          ← 交互金样例（非正式）
│   └── decision_260616_v2_FROM_TEMPLATE.html ← 官方模板 v2.0 预览（非正式）
├── runs/
│   └── <run_id>/       ← 单次门禁运行（run_id = YYYYMMDD-HHMMSS）
│       ├── manifest.json
│       └── checks.json
└── latest/             ← 指向最近一次 run（symlink，本地生成）
```

### 与项目其他测试目录的区别

| 目录 | 验证什么 | 是否阻塞正式报告 |
|---|---|---|
| `validation/` | 数据真实性与决策自洽（E 档） | **是** — FAIL 不得 promote |
| `simulation/` | 预测效果 forward（A 档） | 否 |
| `backtest/` | 历史管道 / 场景（B 档延后） | 否 |
| `tests/` | 单元测试 | 否 |

## 工作流

```
1. 采集          fetch_odds / predict_engine → 根目录或指定快照
2. 写草案        generate_decision_draft → validation/drafts/decision_*.json → .html
3. 跑门禁        validate_gate.py（见下方命令）
4. PASS          `--promote` → **`reports/report_*.html`**（预测+决策合并）+ `reports/decision_*.md`
5. FAIL          只读 validation/runs/<run_id>/checks.json 调试，**不要**改根目录正式文件
```

### PASS 后 promote 到正式目录（T-3-11）

```bash
# 草案在 drafts/ → 复制到根目录并写入 validation_run_id
python3 validate_gate.py \
  --odds odds_260616_20260616-212759.json \
  --prediction prediction_260616_20260616-214115.json \
  --draft-json validation/drafts/decision_260616_draft.json \
  --promote

# 同时把 run_id 写入 prediction JSON（原地更新，建议先备份）
python3 validate_gate.py ... --promote --promote-prediction --force

# 仅预览不写盘
python3 validate_gate.py ... --promote --dry-run
```

promote 后在 `validation/runs/<run_id>/promote.json` 记录正式产物路径；  
正式 MD 含 `> 数据验证：validation_run_id=...`；合并报告 HTML 含 `<!-- validation_run_id: ... -->`。

**规则**：仅 PASS 可 promote；目标必须在项目根目录（**不可**写入 `validation/`）；已存在须 `--force`。

## 命令

```bash
cd /Users/CursorProject/football

python3 validate_gate.py \
  --odds odds_260616_20260616-212759.json \
  --prediction prediction_260616_20260616-214115.json \
  --fundamentals fundamentals_fifa.world_20260616-merged.json
```

### 校验 decision 草案（推荐：草案放 drafts/）

```bash
python3 validate_gate.py \
  --odds odds_260616_20260616-212759.json \
  --prediction prediction_260616_20260616-214115.json \
  --fundamentals fundamentals_fifa.world_20260616-merged.json \
  --draft-json validation/drafts/decision_260616_draft.json
```

### 查看最近一次结果

```bash
cat validation/latest/checks.json | python3 -m json.tool
```

退出码：`0` = 全部必检 PASS；`1` = 存在 FAIL（整期 BLOCK）。

## 必检项（checks.json 字段）

| check_id | 说明 | 状态 |
|---|---|---|
| `inputs_present` | 声明的输入文件均存在 | ✅ v1 |
| `reference_chain` | prediction 引用的 odds 与传入一致 | ✅ v1 |
| `entity_anchor` | prediction 场次 ⊆ odds.matches | ✅ v1 |
| `team_names_anchor` | 主客队中文名与 odds 一致 | ✅ v1 |
| `strategy_config` | STRATEGY_DEFAULT.yaml 可读且含 EV 阈值 | ✅ v1 |
| `draft_odds_mention` | 草案中出现的 `@x.xx` 赔率 ∈ odds（容差 0） | ✅ v1（有草案时） |
| `odds_recomputable` | p_true / EV 复算 | 🔜 T-3-10 扩展 |
| `decision_coherence` | Top6#1 = hero-pick；空单逻辑 | 🔜 依赖 6 进 1 |
| `stake_bounds` | 金额 ∈ 策略预算 | 🔜 T-3-10 扩展 |

## 禁止事项

- ❌ 在 `validation/runs/` 或 `validation/drafts/` 外以 `decision_*` / `prediction_*` 命名调试文件并当正式交付  
- ❌ 门禁 FAIL 仍覆盖根目录已有正式报告  
- ❌ 跳过 `validate_gate.py` 直接由 skill 写根目录（T-3-12 已在 SKILL 步骤 8 强制）

## 关联任务

| ID | 内容 | 状态 |
|---|---|---|
| T-3-9 | 本目录 + README | ✅ |
| T-3-10 | `validate_gate.py` 八类必检 | ⚠️ 部分 |
| T-3-11 | `--promote` 正式产物 + run_id | ✅ |
| T-3-12 | skill 强制先 validate 后 publish | ✅ |

技术细节：`docs/【技术】数据验证门禁v1.md`
