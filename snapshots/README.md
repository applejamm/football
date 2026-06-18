# snapshots/ — 过程快照目录

采集与预测流水线写入的 **JSON 快照**统一放在此目录；人类可读报告见 `reports/`。

## 目录结构

```
snapshots/
├── odds/           # odds_*.json · odds_window_24h_*.json
├── prediction/     # prediction_*.json
├── fundamentals/   # fundamentals_*.json · *-merged.json · fundamentals_db.json · teams/
├── diffs/          # diff_*.json（赔率漂移）
└── raw/            # API 原始响应（--save-raw）
```

## 写入方

| 脚本 | 输出子目录 |
|------|-----------|
| `fetch_odds.py` | `odds/` · `diffs/` · `raw/` |
| `predict_engine.py` | `prediction/` |
| `fetch_fundamentals.py` | `fundamentals/` |

## 引用约定

- `prediction.meta.odds_source` 存 **相对项目根** 路径，如 `snapshots/odds/odds_260619_….json`
- 工作流 `latest_*` 优先查 `snapshots/`，仍兼容根目录遗留文件

## 与正式交付的区别

| 类型 | 目录 | 用途 |
|------|------|------|
| 快照 | `snapshots/` | 可重复采集、可 diff、供门禁校验 |
| 报告 | `reports/` | promote 后唯一 HTML + 复盘 MD |
