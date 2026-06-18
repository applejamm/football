"""T-5-8/9 · 单关资金分配：防御/进攻双方案 + EV 底层 + 自动择优。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scan_candidates_lib import (
    PLAY_HCAP,
    PLAY_WDL,
    WEIGHT_ENGINE,
    WEIGHT_EV,
    WEIGHT_FUNDAMENTALS,
    WEIGHT_INDEPENDENCE,
    Candidate,
    engine_align_score,
    fundamentals_score,
    independence_score,
)

MODE_DEFENSIVE = "defensive"
MODE_OFFENSIVE = "offensive"

MODE_LABELS = {
    MODE_DEFENSIVE: "防御型（覆盖 · 3–4 注）",
    MODE_OFFENSIVE: "进攻型（爆发 · 1–2 注）",
}


def _prediction_index(prediction: dict[str, Any] | None) -> dict[str, dict]:
    if not prediction:
        return {}
    return {r["match_no"]: r for r in prediction.get("predictions") or []}


def score_eligible_singles(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """为全部过闸单关（胜平负/让球）计算综合分。"""
    pred_idx = _prediction_index(prediction)
    eligible: list[Candidate] = []
    for row in scan_result.get("candidates") or []:
        if row.get("status") != "eligible":
            continue
        if row.get("play_type") not in (PLAY_WDL, PLAY_HCAP):
            continue
        eligible.append(
            Candidate(**{k: v for k, v in row.items() if k in Candidate.__dataclass_fields__})
        )
    if not eligible:
        return []

    units = [c.correlation_unit for c in eligible]
    ev_vals = [c.ev for c in eligible]
    ev_min, ev_max = min(ev_vals), max(ev_vals)
    scored: list[dict[str, Any]] = []

    for c in eligible:
        pred_row = pred_idx.get(c.match_no)
        ev_norm = (
            100.0
            if ev_max == ev_min
            else round((c.ev - ev_min) / (ev_max - ev_min) * 100, 1)
        )
        eng = engine_align_score(c, pred_row)
        fund = fundamentals_score(pred_row)
        indep = independence_score(c.correlation_unit, units)
        composite = round(
            ev_norm * WEIGHT_EV
            + eng * WEIGHT_ENGINE
            + fund * WEIGHT_FUNDAMENTALS
            + indep * WEIGHT_INDEPENDENCE,
            1,
        )
        scored.append(
            {
                **c.to_dict(),
                "composite_score": composite,
                "dims": {
                    "ev_norm": ev_norm,
                    "engine": eng,
                    "fundamentals": fund,
                    "independence": indep,
                },
            }
        )
    scored.sort(key=lambda x: (x["composite_score"], x["ev"], x["p_true"]), reverse=True)
    return scored


def _same_bet(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a["match_no"] == b["match_no"]
        and a["play_type"] == b["play_type"]
        and a["pick"] == b["pick"]
        and a.get("handicap") == b.get("handicap")
    )


def _pick_hedge(
    primary: dict[str, Any],
    picks_in_match: list[dict[str, Any]],
    pred_row: dict | None,
) -> dict[str, Any] | None:
    op = ((pred_row or {}).get("prediction") or {}).get("outcome_probs") or {}
    draw_p = float(op.get("平") or 0)
    hedges = [p for p in picks_in_match if not _same_bet(p, primary)]
    if not hedges:
        return None
    if draw_p >= 0.15:
        for p in sorted(hedges, key=lambda x: -x["composite_score"]):
            if p["pick"] == "平":
                return p
    return max(hedges, key=lambda x: (x["composite_score"], x["ev"]))


def _align_stake(raw: int, min_unit: int) -> int:
    raw = max(min_unit, raw)
    return raw - (raw % min_unit)


def _ev_weight(leg: dict[str, Any]) -> float:
    """加权期望权重：EV 越高 + 综合分越高 → 分配越多预算。"""
    ev_factor = max(0.05, 1.0 + float(leg["ev"]))
    comp = float(leg.get("composite_score") or 50.0) / 100.0
    return ev_factor * max(0.3, comp)


def _normalize_stakes_to_budget(
    legs: list[dict[str, Any]],
    stakes_by_id: dict[str, int],
    budget: int,
    min_unit: int,
    cap: int,
) -> None:
    total = sum(stakes_by_id.values())
    if total != budget and legs:
        diff = budget - total
        first = legs[0]["id"]
        stakes_by_id[first] = _align_stake(
            min(cap, max(min_unit, stakes_by_id[first] + diff)), min_unit
        )
    total = sum(stakes_by_id.values())
    idx = 0
    guard = 0
    ids = [l["id"] for l in legs]
    while total != budget and guard < 1000:
        leg_id = ids[idx % len(ids)]
        step = min_unit if budget > total else -min_unit
        nxt = stakes_by_id[leg_id] + step
        if min_unit <= nxt <= cap:
            stakes_by_id[leg_id] = nxt
            total = sum(stakes_by_id.values())
        idx += 1
        guard += 1


def _assign_leg_ids_and_wins(legs: list[dict[str, Any]], stakes_by_id: dict[str, int]) -> None:
    for i, leg in enumerate(legs, 1):
        leg["leg_id"] = f"B{i}"
        leg["stake"] = stakes_by_id.get(leg["id"], 2)
        leg["win_gross"] = round(leg["stake"] * float(leg["odds"]), 2)


def _allocate_stakes_ev_weighted(
    legs: list[dict[str, Any]],
    budget: int,
    min_unit: int = 2,
    max_share_per_unit: float = 0.5,
) -> None:
    """按 EV×综合分 权重分配预算（底层 C：加权期望）。"""
    if not legs:
        return
    cap = _align_stake(int(budget * max_share_per_unit), min_unit)
    if len(legs) == 1:
        stakes_by_id = {legs[0]["id"]: _align_stake(min(budget, cap), min_unit)}
        _normalize_stakes_to_budget(legs, stakes_by_id, budget, min_unit, budget)
        _assign_leg_ids_and_wins(legs, stakes_by_id)
        return

    weights = [_ev_weight(leg) for leg in legs]
    w_sum = sum(weights)
    stakes_by_id: dict[str, int] = {}
    for leg, w in zip(legs, weights):
        raw = _align_stake(int(budget * w / w_sum), min_unit)
        stakes_by_id[leg["id"]] = min(raw, cap)
    _normalize_stakes_to_budget(legs, stakes_by_id, budget, min_unit, cap)
    _assign_leg_ids_and_wins(legs, stakes_by_id)


def _allocate_stakes_defensive(
    legs: list[dict[str, Any]],
    budget: int,
    min_unit: int = 2,
    max_share_per_unit: float = 0.5,
) -> None:
    """防御型：按场次平分，场内主攻 65% / 防冷 35%。"""
    if not legs:
        return
    cap = _align_stake(int(budget * max_share_per_unit), min_unit)
    match_order: list[str] = []
    for leg in legs:
        if leg["match_no"] not in match_order:
            match_order.append(leg["match_no"])

    n = len(match_order)
    base_per_match = _align_stake(budget // n, min_unit)
    stakes_by_id: dict[str, int] = {}

    for match_no in match_order:
        match_legs = [l for l in legs if l["match_no"] == match_no]
        prim = [l for l in match_legs if l.get("role") == "primary"]
        others = [l for l in match_legs if l.get("role") != "primary"]
        ordered = prim + others
        weights = [0.65, 0.35] if len(ordered) > 1 else [1.0]
        for i, leg in enumerate(ordered):
            w = weights[min(i, len(weights) - 1)]
            raw = _align_stake(int(base_per_match * w), min_unit)
            stakes_by_id[leg["id"]] = min(raw, cap)

    _normalize_stakes_to_budget(legs, stakes_by_id, budget, min_unit, cap)
    _assign_leg_ids_and_wins(legs, stakes_by_id)


def _mutex_groups(legs: list[dict[str, Any]], match_order: list[str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for match_no in match_order:
        ids = [l["leg_id"] for l in legs if l["match_no"] == match_no]
        if len(ids) >= 2:
            groups.append({"match_no": match_no, "leg_ids": ids})
    return groups


def _wrap_portfolio(
    legs: list[dict[str, Any]],
    budget: int,
    mode: str,
    match_order: list[str],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "legs": legs,
        "total_stake": sum(int(l["stake"]) for l in legs),
        "budget": budget,
        "leg_count": len(legs),
        "mutex_groups": _mutex_groups(legs, match_order),
        "match_count": len({l["match_no"] for l in legs}),
    }


def build_defensive_portfolio(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None,
    budget: int,
    min_legs: int = 3,
    max_legs: int = 4,
    min_unit: int = 2,
    max_share_per_unit: float = 0.5,
) -> dict[str, Any] | None:
    """防御型：2 场 × 主攻+防冷，提高覆盖与回血。"""
    scored = score_eligible_singles(scan_result, prediction)
    if len(scored) < min_legs:
        return None

    pred_idx = _prediction_index(prediction)
    by_match: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        by_match[row["match_no"]].append(row)
    for picks in by_match.values():
        picks.sort(key=lambda x: (-x["composite_score"], -x["ev"]))

    match_order = sorted(
        by_match.keys(),
        key=lambda m: by_match[m][0]["composite_score"],
        reverse=True,
    )

    target = max_legs if budget >= 100 else min_legs
    target = max(min_legs, min(max_legs, target))

    legs: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for match_no in match_order:
        if len(legs) >= target:
            break
        picks = by_match[match_no]
        primary = dict(picks[0])
        primary["role"] = "primary"
        legs.append(primary)
        used_ids.add(primary["id"])

        if len(legs) >= target:
            break
        hedge = _pick_hedge(primary, picks, pred_idx.get(match_no))
        if hedge and hedge["id"] not in used_ids:
            h = dict(hedge)
            h["role"] = "hedge"
            legs.append(h)
            used_ids.add(h["id"])

    for row in scored:
        if len(legs) >= target:
            break
        if row["id"] in used_ids:
            continue
        fill = dict(row)
        fill["role"] = "fill"
        legs.append(fill)
        used_ids.add(fill["id"])

    if len(legs) < min_legs:
        return None
    legs = legs[:target]
    _allocate_stakes_defensive(legs, budget, min_unit=min_unit, max_share_per_unit=max_share_per_unit)
    used_matches = [m for m in match_order if any(l["match_no"] == m for l in legs)]
    return _wrap_portfolio(legs, budget, MODE_DEFENSIVE, used_matches)


def build_offensive_portfolio(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None,
    budget: int,
    min_unit: int = 2,
    max_share_per_unit: float = 0.5,
) -> dict[str, Any] | None:
    """进攻型：1–2 笔重注，追求命中爆发。"""
    scored = score_eligible_singles(scan_result, prediction)
    if not scored:
        return None

    top = scored[0]
    legs: list[dict[str, Any]] = [dict(top, role="strike")]
    match_order = [top["match_no"]]

    if budget >= 80:
        second = None
        for row in scored[1:]:
            if row["match_no"] != top["match_no"]:
                second = row
                break
        if second:
            legs.append(dict(second, role="strike"))
            match_order.append(second["match_no"])

    _allocate_stakes_ev_weighted(legs, budget, min_unit=min_unit, max_share_per_unit=max_share_per_unit)
    return _wrap_portfolio(legs, budget, MODE_OFFENSIVE, match_order)


def portfolio_weighted_ev(portfolio: dict[str, Any] | None) -> float:
    """组合加权期望得分 ≈ Σ(注额 × EV)。"""
    if not portfolio:
        return float("-inf")
    return round(sum(int(l["stake"]) * float(l["ev"]) for l in portfolio["legs"]), 4)


def _uncertainty_score(
    scored: list[dict[str, Any]],
    prediction: dict[str, Any] | None,
    strategy_gates: dict[str, Any] | None,
) -> float:
    """0=清晰热门 · 1=高度不确定（宜防御）。"""
    pred_idx = _prediction_index(prediction)
    draw_probs: list[float] = []
    for row in scored[:6]:
        pred_row = pred_idx.get(row["match_no"])
        op = ((pred_row or {}).get("prediction") or {}).get("outcome_probs") or {}
        draw_probs.append(float(op.get("平") or 0))
    for alert in (strategy_gates or {}).get("draw_risk_alerts") or []:
        draw_probs.append(float(alert.get("draw_prob") or 0))

    max_draw = max(draw_probs) if draw_probs else 0.0
    spread = 0.0
    if len(scored) >= 2:
        spread = float(scored[0]["composite_score"]) - float(scored[1]["composite_score"])

    score = max_draw * 2.0
    if spread < 12:
        score += 0.15
    if max_draw >= 0.20:
        score += 0.10
    return min(1.0, score)


def select_portfolio_plan(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None,
    budget: int,
    strategy_gates: dict[str, Any] | None = None,
    min_unit: int = 2,
    max_share_per_unit: float = 0.5,
) -> dict[str, Any] | None:
    """生成防御/进攻双方案，按加权 EV + 不确定性自动择优。"""
    defensive = build_defensive_portfolio(
        scan_result, prediction, budget, min_unit=min_unit, max_share_per_unit=max_share_per_unit
    )
    offensive = build_offensive_portfolio(
        scan_result, prediction, budget, min_unit=min_unit, max_share_per_unit=max_share_per_unit
    )
    if not defensive and not offensive:
        return None
    if not defensive:
        return {
            "mode": MODE_OFFENSIVE,
            "primary": offensive,
            "alternate": None,
            "selection_reason": "过闸候选不足以组成防御型组合，锁定进攻型。",
            "scores": {"defensive": None, "offensive": portfolio_weighted_ev(offensive)},
        }
    if not offensive:
        return {
            "mode": MODE_DEFENSIVE,
            "primary": defensive,
            "alternate": None,
            "selection_reason": "仅防御型组合可行，锁定防御型。",
            "scores": {"defensive": portfolio_weighted_ev(defensive), "offensive": None},
        }

    scored = score_eligible_singles(scan_result, prediction)
    unc = _uncertainty_score(scored, prediction, strategy_gates)
    def_ev = portfolio_weighted_ev(defensive)
    off_ev = portfolio_weighted_ev(offensive)

    def_score = def_ev + unc * 8.0
    off_score = off_ev + (1.0 - unc) * 8.0

    spread = (
        float(scored[0]["composite_score"]) - float(scored[1]["composite_score"])
        if len(scored) >= 2
        else 99.0
    )
    if spread >= 18:
        off_score += 4.0

    if def_score >= off_score:
        mode = MODE_DEFENSIVE
        reason = (
            f"自动锁定防御型：不确定性 {unc:.0%}，加权 EV 防御 {def_ev:.1f} ≥ 进攻 {off_ev:.1f}（含覆盖加成）。"
        )
        primary, alternate = defensive, offensive
    else:
        mode = MODE_OFFENSIVE
        reason = (
            f"自动锁定进攻型：Top 场次信号清晰（综合分差 {spread:.0f}），加权 EV 进攻 {off_ev:.1f} > 防御 {def_ev:.1f}。"
        )
        primary, alternate = offensive, defensive

    return {
        "mode": mode,
        "primary": primary,
        "alternate": alternate,
        "selection_reason": reason,
        "scores": {
            "defensive": def_ev,
            "offensive": off_ev,
            "uncertainty": round(unc, 3),
            "defensive_adj": round(def_score, 2),
            "offensive_adj": round(off_score, 2),
        },
    }


def build_portfolio(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None,
    budget: int,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """兼容旧接口：返回自动择优后的主推组合。"""
    plan = select_portfolio_plan(scan_result, prediction, budget, **kwargs)
    if not plan:
        return None
    primary = dict(plan["primary"])
    primary["plan_mode"] = plan["mode"]
    primary["selection_reason"] = plan["selection_reason"]
    primary["alternate_mode"] = (plan.get("alternate") or {}).get("mode")
    return primary
