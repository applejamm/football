#!/usr/bin/env bash
# 赛前数据自动抓取（T-1-16 / T-1-17）
# 用法：
#   ./scripts/prefetch.sh full          # 全量：赔率 + 基本面
#   ./scripts/prefetch.sh odds          # 仅赔率
#   ./scripts/prefetch.sh fundamentals  # 仅基本面
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-full}"
DAY="${2:-}"

odds_args=()
fund_args=()
if [[ -n "$DAY" ]]; then
  odds_args=(--day "$DAY")
  fund_args=(--date "$DAY")
fi

case "$MODE" in
  full)
    python3 fetch_odds.py "${odds_args[@]}" --diff-min-pct 1
    python3 fetch_fundamentals.py "${fund_args[@]}"
    ;;
  odds)
    python3 fetch_odds.py "${odds_args[@]}" --diff-min-pct 1
    ;;
  fundamentals)
    python3 fetch_fundamentals.py "${fund_args[@]}"
    ;;
  predict)
    python3 fetch_odds.py "${odds_args[@]}"
    python3 fetch_fundamentals.py "${fund_args[@]}"
    python3 predict_engine.py ${DAY:+--day "$DAY"}
    ;;
  workflow)
    if [[ -z "$DAY" ]]; then
      echo "用法: $0 workflow <day_code> [budget] [--promote]" >&2
      exit 1
    fi
    BUDGET=200
    PROMOTE=""
    for arg in "${@:3}"; do
      if [[ "$arg" == "--promote" ]]; then
        PROMOTE="--promote"
      elif [[ "$arg" =~ ^[0-9]+$ ]]; then
        BUDGET="$arg"
      fi
    done
    python3 run_workflow.py --day "$DAY" --budget "$BUDGET" $PROMOTE
    ;;
  *)
    echo "用法: $0 {full|odds|fundamentals|predict|workflow} [day_code] [budget]" >&2
    exit 1
    ;;
esac

echo "[prefetch] done mode=$MODE day=${DAY:-auto} at $(date -Iseconds)"
