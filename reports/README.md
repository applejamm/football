# 报告目录 · `reports/`

> 人类可读报告的**统一落盘目录**。过程 JSON 在 `snapshots/`；本目录只放「给人看」的交付物。

## 目录结构

```
reports/
├── README.md
├── report_*.html              ← 工作流 promote：预测 + 决策合并报告
├── decision_*.md              ← 复盘用决策 MD（promote 从 JSON 派生）
└── backtest/
    └── backtest_*.json        ← 历史回测报告（run_backtest.py）
```

## 与其它目录的区别

| 目录 | 内容 | 读者 |
|---|---|---|
| **`reports/`** | HTML / MD 正式报告 | 人类 |
| **`snapshots/`** | `odds/` · `prediction/` · `fundamentals/` 等过程快照 | Agent / 脚本 |
| `validation/drafts/` | 门禁前草案 JSON/HTML | 工程调试 |
| `replay/` | 复盘评分报告 · 结算归档 JSON | 复盘 Agent |

## 生成方式

| 文件 | 命令 |
|---|---|
| `report_*.html` | `python3 run_workflow.py --day 260619 --promote` |
| `decision_*.md` | 同上（promote 自动生成） |
| `backtest/backtest_*.json` | `python3 backtest/run_backtest.py` |

配置常量：`artifact_lib.REPORTS_DIR` · `artifact_lib.BACKTEST_REPORTS_DIR`
