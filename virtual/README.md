# 虚拟跟踪 · `virtual/`

> **T-5-5 / T-4-11** — 追踪「主推 vs Top6 其余 vs 被砍注」的**虚拟收益**，与真实下注对照。  
> 样本 < 20 期不做 ROI 硬门槛，只做过程监控（PRD C 档-5）。

## 为什么需要

| 问题 | 虚拟跟踪回答 |
|---|---|
| EV 闸救了你还是害了你？ | 被砍样本若虚拟命中，记入「单期翻盘 ≠ 方法论错」 |
| 6 进 1 主推是否优于 Top6 其余？ | 同口径虚拟投注对比 |
| 主推是否优于旧版多注？ | 与 `tracking.md` 注级明细对照 |

## 工作流

```
1. scan_candidates.py → scan_<code>.json
2. 赛后录入比分
3. virtual_tracking.py --scan ... --scores "场次:比分" --update-tracking
4. 读 tracking.md「虚拟跟踪」段 + virtual/runs/*.json
```

## 命令示例

```bash
cd /Users/CursorProject/football

# 260614 已结算演示（010 荷兰2:2 · 012 瑞典5:1）
python3 scan_candidates.py \\
  --odds odds_260614_20260614-223405.json \\
  --prediction prediction_260614_20260616-001842.json \\
  --out validation/drafts/scan_260614.json

python3 virtual_tracking.py \\
  --scan validation/drafts/scan_260614.json \\
  --scores "周日010:2:2,周日012:5:1" \\
  --virtual-stake 50 \\
  --update-tracking
```

## 目录

```
virtual/
├── README.md
└── runs/
    └── <issue_no>_<timestamp>.json   # 结算归档（可 gitignore）
```

## 虚拟口径

- **主推**：`funnel.hero` 1 条
- **Top6入围**：rank 2–6
- **被砍样本**：reject_below 下 EV 最高的 N 条（默认 10）
- 统一 **虚拟投注** 默认 50 元/条（`--virtual-stake` 可调）

## 关联任务

| ID | 状态 |
|---|---|
| T-5-5 | ✅ virtual_tracking.py |
| T-4-11 | ✅ 合并入 T-5-5 被砍列 |
