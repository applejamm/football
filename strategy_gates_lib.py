"""复盘 backlog 策略闸（IMP-006 catastrophic 缩量 · IMP-007 低赔稳档 · IMP-008 平概率披露）。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json

try:
    import yaml
except ImportError:
    yaml = None  # type: type[None]

ROOT = Path(__file__).resolve().parent
DEFAULT_STRATEGY = (
    ROOT.parent / ".cursor/skills/football-betting-strategist/STRATEGY_DEFAULT.yaml"
)
DEFAULT_TRACKING = ROOT / "tracking.md"

# IMP-007 默认：主胜/客胜碾压盘低赔 + 平赔有缓冲
LOW_ODDS_WIN_MAX = 1.20
LOW_ODDS_DRAW_MIN = 3.5
LOW_ODDS_STABLE_CAP = 25

# IMP-008 默认：引擎平概率披露线
DRAW_RISK_THRESHOLD = 0.15


@dataclass
class BudgetResolution:
    requested: int
    effective: int
    max_loss_per_round: int
    catastrophic_active: bool
    shrink_applied: bool
    override_used: bool
    last_issue: str | None
    last_period_loss: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LowOddsTrap:
    match_no: str
    home_team: str
    away_team: str
    favorite_side: str  # 胜 | 负
    win_odds: float
    draw_odds: float
    max_stable_stake: int
    action: str  # cap | hedge_evaluate

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DrawRiskAlert:
    match_no: str
    home_cn: str
    away_cn: str
    draw_prob: float
    engine_top1: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyGates:
    budget: BudgetResolution | None = None
    low_odds_traps: list[LowOddsTrap] = field(default_factory=list)
    draw_risk_alerts: list[DrawRiskAlert] = field(default_factory=list)
    imp_ids: list[str] = field(default_factory=lambda: ["IMP-006", "IMP-007", "IMP-008"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "imp_ids": self.imp_ids,
            "budget": self.budget.to_dict() if self.budget else None,
            "low_odds_traps": [t.to_dict() for t in self.low_odds_traps],
            "draw_risk_alerts": [a.to_dict() for a in self.draw_risk_alerts],
        }


def _parse_yaml_scalar(block: str, key: str, default: Any) -> Any:
    pat = re.compile(rf"^\s*{re.escape(key)}:\s*(.+?)\s*(?:#.*)?$", re.M)
    m = pat.search(block)
    if not m:
        return default
    raw = m.group(1).strip().strip('"').strip("'")
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_strategy_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_STRATEGY
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    if yaml is not None and text:
        try:
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                budget = data.get("budget") or {}
                stop = data.get("stop_loss") or {}
                replay = data.get("replay_gates") or {}
                return {
                    "max_loss_per_round": int(budget.get("max_loss_per_round", 200)),
                    "recommended_per_round": int(budget.get("recommended_per_round", 200)),
                    "min_unit": int(budget.get("min_unit", 2)),
                    "catastrophic_threshold": float(stop.get("catastrophic_threshold", 0.8)),
                    "catastrophic_shrink_factor": float(
                        replay.get("catastrophic_shrink_factor", 0.5)
                    ),
                    "allow_full_budget_override": bool(
                        replay.get("allow_full_budget_override", False)
                    ),
                    "low_odds_win_max": float(replay.get("low_odds_win_max", LOW_ODDS_WIN_MAX)),
                    "low_odds_draw_min": float(replay.get("low_odds_draw_min", LOW_ODDS_DRAW_MIN)),
                    "low_odds_stable_cap": int(
                        replay.get("low_odds_stable_cap", LOW_ODDS_STABLE_CAP)
                    ),
                    "draw_risk_threshold": float(
                        replay.get("draw_risk_threshold", DRAW_RISK_THRESHOLD)
                    ),
                }
        except Exception:
            pass
    # 无 PyYAML 时的块级 fallback
    budget_block = ""
    stop_block = ""
    replay_block = ""
    section = None
    for line in text.splitlines():
        if line.strip().startswith("budget:"):
            section = "budget"
            continue
        if line.strip().startswith("stop_loss:"):
            section = "stop"
            continue
        if line.strip().startswith("replay_gates:"):
            section = "replay"
            continue
        if section and re.match(r"^\S", line) and not line.startswith(" "):
            section = None
        if section == "budget":
            budget_block += line + "\n"
        elif section == "stop":
            stop_block += line + "\n"
        elif section == "replay":
            replay_block += line + "\n"
    return {
        "max_loss_per_round": int(_parse_yaml_scalar(budget_block, "max_loss_per_round", 200)),
        "recommended_per_round": int(_parse_yaml_scalar(budget_block, "recommended_per_round", 200)),
        "min_unit": int(_parse_yaml_scalar(budget_block, "min_unit", 2)),
        "catastrophic_threshold": float(
            _parse_yaml_scalar(stop_block, "catastrophic_threshold", 0.8)
        ),
        "catastrophic_shrink_factor": float(
            _parse_yaml_scalar(replay_block, "catastrophic_shrink_factor", 0.5)
        ),
        "allow_full_budget_override": bool(
            _parse_yaml_scalar(replay_block, "allow_full_budget_override", False)
        ),
        "low_odds_win_max": float(_parse_yaml_scalar(replay_block, "low_odds_win_max", LOW_ODDS_WIN_MAX)),
        "low_odds_draw_min": float(
            _parse_yaml_scalar(replay_block, "low_odds_draw_min", LOW_ODDS_DRAW_MIN)
        ),
        "low_odds_stable_cap": int(
            _parse_yaml_scalar(replay_block, "low_odds_stable_cap", LOW_ODDS_STABLE_CAP)
        ),
        "draw_risk_threshold": float(
            _parse_yaml_scalar(replay_block, "draw_risk_threshold", DRAW_RISK_THRESHOLD)
        ),
    }


def _parse_money_cell(cell: str) -> float | None:
    s = cell.strip().replace("**", "").replace("−", "-").replace("–", "-")
    s = s.replace("元", "").replace(",", "").strip()
    if not s or s in ("—", "-", "待结算"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_catastrophic_flag(tracking_text: str) -> bool:
    """读取 tracking 累计段「是否触发 catastrophic」。"""
    if "是否触发 catastrophic" not in tracking_text:
        return False
    for line in tracking_text.splitlines():
        if "是否触发 catastrophic" in line:
            return "**是" in line or "是 ⚠️" in line or "| 是" in line
    return False


def parse_last_period_summary(tracking_text: str) -> tuple[str | None, float | None]:
    """从 tracking.md 期汇总表取最近一期已结算的期号与总收益（负=亏损）。"""
    if "## 期汇总" not in tracking_text:
        return None, None
    section = tracking_text.split("## 期汇总", 1)[1]
    # 止于下一章节（勿用 "---"：会与 markdown 表格分隔符冲突）
    if "\n## " in section:
        section = section.split("\n## ", 1)[0]
    rows: list[tuple[str, float]] = []
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line or "期号" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        issue, pnl = cols[0], _parse_money_cell(cols[6])
        if issue and pnl is not None:
            rows.append((issue, pnl))
    if not rows:
        return None, None
    issue, pnl = rows[-1]
    return issue, pnl


def is_catastrophic_triggered(
    last_loss: float | None,
    max_loss_per_round: int,
    threshold: float,
) -> bool:
    if last_loss is None:
        return False
    return abs(min(0.0, last_loss)) >= max_loss_per_round * threshold


def resolve_effective_budget(
    requested: int,
    strategy: dict[str, Any] | None = None,
    tracking_path: Path | None = None,
    allow_full_budget_override: bool = False,
) -> BudgetResolution:
    """IMP-006：catastrophic 触发时默认缩量；满预算须显式 --allow-full-budget。"""
    cfg = strategy or load_strategy_config()
    max_loss = int(cfg["max_loss_per_round"])
    threshold = float(cfg["catastrophic_threshold"])
    shrink = float(cfg["catastrophic_shrink_factor"])
    min_unit = int(cfg.get("min_unit", 2))
    yaml_allows_override = bool(cfg.get("allow_full_budget_override", False))

    if shrink >= 1.0:
        return BudgetResolution(
            requested=requested,
            effective=min(requested, max_loss),
            max_loss_per_round=max_loss,
            catastrophic_active=False,
            shrink_applied=False,
            override_used=False,
            last_issue=None,
            last_period_loss=None,
            reason="catastrophic 自动缩量已关闭（shrink_factor≥1，用户策略偏好）",
        )

    tracking = tracking_path if tracking_path is not None else DEFAULT_TRACKING
    tracking_text = tracking.read_text(encoding="utf-8") if tracking.is_file() else ""
    last_issue, last_loss = parse_last_period_summary(tracking_text)
    cat_from_loss = is_catastrophic_triggered(last_loss, max_loss, threshold)
    cat_from_flag = parse_catastrophic_flag(tracking_text)
    cat_active = cat_from_loss or cat_from_flag

    shrunk = max(min_unit, int(max_loss * shrink))
    shrunk -= shrunk % min_unit

    if not cat_active:
        return BudgetResolution(
            requested=requested,
            effective=min(requested, max_loss),
            max_loss_per_round=max_loss,
            catastrophic_active=False,
            shrink_applied=False,
            override_used=False,
            last_issue=last_issue,
            last_period_loss=last_loss,
            reason="未触发 catastrophic，使用请求预算（不超过 max_loss_per_round）",
        )

    can_override = allow_full_budget_override and yaml_allows_override
    if requested <= shrunk:
        return BudgetResolution(
            requested=requested,
            effective=requested,
            max_loss_per_round=max_loss,
            catastrophic_active=True,
            shrink_applied=True,
            override_used=False,
            last_issue=last_issue,
            last_period_loss=last_loss,
            reason=f"catastrophic 已触发（上期 {last_issue} 亏 {last_loss} 元），请求预算已在缩量线内",
        )

    if can_override:
        return BudgetResolution(
            requested=requested,
            effective=min(requested, max_loss),
            max_loss_per_round=max_loss,
            catastrophic_active=True,
            shrink_applied=False,
            override_used=True,
            last_issue=last_issue,
            last_period_loss=last_loss,
            reason=(
                f"⚠️ 用户显式 --allow-full-budget 覆盖 catastrophic 缩量"
                f"（上期 {last_issue} 亏 {abs(last_loss or 0):.0f} 元）"
            ),
        )

    return BudgetResolution(
        requested=requested,
        effective=shrunk,
        max_loss_per_round=max_loss,
        catastrophic_active=True,
        shrink_applied=True,
        override_used=False,
        last_issue=last_issue,
        last_period_loss=last_loss,
        reason=(
            f"catastrophic 缩量：上期 {last_issue} 亏损 {last_loss} 元 ≥ "
            f"{max_loss}×{threshold:.0%}={max_loss * threshold:.0f} → 预算 {requested}→{shrunk} 元"
            f"（满预算须 CLI --allow-full-budget）"
        ),
    )


def detect_low_odds_traps(
    odds: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> list[LowOddsTrap]:
    """IMP-007：主/客胜赔 < low_odds_win_max 且平赔 > low_odds_draw_min → 稳档封顶。"""
    cfg = config or load_strategy_config()
    win_max = float(cfg.get("low_odds_win_max", LOW_ODDS_WIN_MAX))
    draw_min = float(cfg.get("low_odds_draw_min", LOW_ODDS_DRAW_MIN))
    cap = int(cfg.get("low_odds_stable_cap", LOW_ODDS_STABLE_CAP))
    traps: list[LowOddsTrap] = []

    for match in odds.get("matches") or []:
        match_no = match.get("match_no", "")
        home = match.get("home_team", "")
        away = match.get("away_team", "")
        for market in match.get("markets") or []:
            if market.get("type") != "胜平负":
                continue
            omap = market.get("odds") or {}
            draw_odds = float(omap.get("平") or 0)
            if draw_odds <= draw_min:
                continue
            for side, label in (("胜", "主胜"), ("负", "客胜")):
                win_odds = float(omap.get(side) or 0)
                if win_odds <= 0 or win_odds >= win_max:
                    continue
                traps.append(
                    LowOddsTrap(
                        match_no=match_no,
                        home_team=home,
                        away_team=away,
                        favorite_side=side,
                        win_odds=win_odds,
                        draw_odds=draw_odds,
                        max_stable_stake=cap,
                        action="cap_and_evaluate_draw_hedge",
                    )
                )
    return traps


def _trap_index(traps: list[LowOddsTrap]) -> dict[str, LowOddsTrap]:
    return {t.match_no: t for t in traps}


def apply_low_odds_flags_to_candidates(
    candidates: list[dict[str, Any]],
    traps: list[LowOddsTrap],
) -> None:
    """为低赔陷阱场次的 WDL 胜/负候选打标 max_stake_cap。"""
    idx = _trap_index(traps)
    for row in candidates:
        mn = row.get("match_no", "").split("+")[0]
        trap = idx.get(mn)
        if not trap:
            continue
        if row.get("play_type") != "wdl":
            continue
        if row.get("pick") != trap.favorite_side:
            continue
        flags = row.setdefault("strategy_flags", {})
        flags["low_odds_trap"] = True
        flags["max_stake_cap"] = trap.max_stable_stake
        flags["draw_odds"] = trap.draw_odds
        flags["action"] = trap.action


def collect_draw_risk_alerts(
    prediction: dict[str, Any] | None,
    match_nos: set[str] | list[str],
    config: dict[str, Any] | None = None,
) -> list[DrawRiskAlert]:
    """IMP-008：引擎平概率 > 阈值 → 决策卡须披露防平评估。"""
    if not prediction:
        return []
    cfg = config or load_strategy_config()
    threshold = float(cfg.get("draw_risk_threshold", DRAW_RISK_THRESHOLD))
    wanted = set(match_nos)
    alerts: list[DrawRiskAlert] = []

    for row in prediction.get("predictions") or []:
        mn = row.get("match_no", "")
        if mn not in wanted:
            continue
        pred = row.get("prediction") or {}
        op = pred.get("outcome_probs") or {}
        draw_p = float(op.get("平") or 0)
        if draw_p <= threshold:
            continue
        top1 = max(op, key=lambda k: op[k]) if op else "?"
        rec = "稳档减半或评估防平/比分平局备份；勿重仓低赔主胜"
        if draw_p >= 0.18:
            rec = "平概率偏高 → 优先减仓低赔胜选项，显式列出防平备选"
        alerts.append(
            DrawRiskAlert(
                match_no=mn,
                home_cn=row.get("home_cn", ""),
                away_cn=row.get("away_cn", ""),
                draw_prob=round(draw_p, 4),
                engine_top1=top1,
                recommendation=rec,
            )
        )
    return alerts


def stake_with_caps(base_stake: int, candidate: dict[str, Any] | None, min_unit: int = 2) -> int:
    """按 strategy_flags.max_stake_cap 截断注额（cap 向下取 min_unit 整数倍）。"""
    if not candidate:
        return base_stake
    cap = (candidate.get("strategy_flags") or {}).get("max_stake_cap")
    if cap is None:
        return base_stake
    cap_aligned = int(cap) - (int(cap) % min_unit)
    capped = min(base_stake, max(min_unit, cap_aligned))
    capped -= capped % min_unit
    return max(min_unit, capped)


def build_strategy_gates(
    odds: dict[str, Any],
    prediction: dict[str, Any] | None,
    budget_resolution: BudgetResolution | None = None,
    funnel: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> StrategyGates:
    cfg = config or load_strategy_config()
    traps = detect_low_odds_traps(odds, cfg)
    match_nos: set[str] = set()
    if funnel:
        for key in ("hero", "top6", "top3"):
            block = funnel.get(key)
            if isinstance(block, dict):
                mn = block.get("match_no", "")
                if mn:
                    match_nos.add(mn.split("+")[0])
            elif isinstance(block, list):
                for item in block:
                    mn = item.get("match_no", "")
                    if mn:
                        match_nos.add(mn.split("+")[0])
    alerts = collect_draw_risk_alerts(prediction, match_nos, cfg)
    return StrategyGates(
        budget=budget_resolution,
        low_odds_traps=traps,
        draw_risk_alerts=alerts,
    )


def enrich_scan_payload(
    payload: dict[str, Any],
    odds: dict[str, Any],
    prediction: dict[str, Any] | None = None,
    budget_resolution: BudgetResolution | None = None,
    strategy_path: Path | None = None,
) -> dict[str, Any]:
    """写入 scan JSON 的 strategy_gates 并标注 candidates。"""
    cfg = load_strategy_config(strategy_path)
    traps = detect_low_odds_traps(odds, cfg)
    apply_low_odds_flags_to_candidates(payload.get("candidates") or [], traps)
    gates = build_strategy_gates(
        odds,
        prediction,
        budget_resolution=budget_resolution,
        funnel=payload.get("funnel"),
        config=cfg,
    )
    payload["strategy_gates"] = gates.to_dict()
    return payload
