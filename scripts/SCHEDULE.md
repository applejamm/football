# 赛前自动更新调度（T-1-16）

## macOS launchd（推荐）

```bash
# 安装：赛前每 6 小时全量更新
cp football/scripts/com.football.prefetch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.football.prefetch.plist
```

## cron 替代

```cron
# 每 6 小时全量（约覆盖 PRD「赛前 24h」）
0 */6 * * * cd /Users/CursorProject/football && ./scripts/prefetch.sh full >> logs/prefetch.log 2>&1

# 赛前 2h 增量：世界杯期间可改为每小时
0 * * * * cd /Users/CursorProject/football && ./scripts/prefetch.sh fundamentals >> logs/prefetch.log 2>&1
```

## 命令

| 命令 | 说明 |
|---|---|
| `./scripts/prefetch.sh full` | 赔率 diff + 基本面 |
| `./scripts/prefetch.sh predict 260614` | 抓取 + 出预测 |
