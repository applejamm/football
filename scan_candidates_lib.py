"""玩法全量扫描 + Top6 排序 + 二次评估（T-5-1 ~ T-5-3）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from predict_lib import devig_1x2

ROOT = Path(__file__).resolve().parent
DEFAULT_STRATEGY = (
    ROOT.parent / ".cursor/skills/football-betting-strategist/STRATEGY_DEFAULT.yaml"
)
if not DEFAULT_STRATEGY.exists():
    DEFAULT_STRATEGY = ROOT / "STRATEGY_DEFAULT.yaml"

# 与 football-odds-analyst / README 一致
RETURN_1X2 = 0.885
RETURN_TOTAL = 0.797
RETURN_SCORE = 0.76
RETURN_HAFU = 0.775

PLAY_WDL = "wdl"
PLAY_HCAP = "hcap"
PLAY_TOTAL = "total"
PLAY_SCORE = "score"
PLAY_HAFU = "hafu"
PLAY_PARLAY = "parlay"

CATEGORY_LABELS = {
    PLAY_WDL: "不让球胜平负",
    PLAY_HCAP: "让球胜平负",
    PLAY_TOTAL: "总进球数",
    PLAY_SCORE: "比分",
    PLAY_HAFU: "半全场",
    PLAY_PARLAY: "串关",
}

# 二次评估权重（PRD §4.2）
WEIGHT_EV = 0.40
WEIGHT_ENGINE = 0.25
WEIGHT_FUNDAMENTALS = 0.20
WEIGHT_INDEPENDENCE = 0.15


@dataclass
class Candidate:
    id: str
    match_no: str
    home_team: str
    away_team: str
    category: str
    play_type: str
    pick: str
    pick_label: str
    odds: float
    p_true: float
    ev: float
    handicap: int | None = None
    handicap_label: str | None = None
    correlation_unit: str = ""
    status: str = "eligible"  # eligible | rejected
    reject_reason: str | None = None
    legs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_yaml_thresholds(strategy_path: Path | None = None) -> dict[str, float]:
    path = strategy_path or DEFAULT_STRATEGY
    text = path.read_text(encoding="utf-8")
    out: dict[str, float] = {
        "reject_below": -0.20,
        "must_have": -0.12,
        "preferred": -0.08,
    }
    for key in out:
        marker = f"{key}:"
        for line in text.splitlines():
            if line.strip().startswith(marker):
                try:
                    out[key] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
    return out


def compute_ev(p_true: float, odds: float) -> float:
    return round(p_true * odds - 1.0, 4)


def p_true_from_odds_single(odds: float, return_rate: float) -> float:
    return round((1.0 / odds) * return_rate, 4)


def _unit_for_match(match_no: str, pick: str, play_type: str) -> str:
    short = match_no[-3:]
    if play_type == PLAY_PARLAY:
        return "U_parlay"
    return f"U_{short}_{pick}"


def _next_id(counter: list[int], prefix: str = "C") -> str:
    counter[0] += 1
    return f"{prefix}{counter[0]:04d}"


def scan_wdl_and_hcap(
    match: dict[str, Any],
    thresholds: dict[str, float],
    counter: list[int],
    out: list[Candidate],
) -> None:
    match_no = match["match_no"]
    home = match["home_team"]
    away = match["away_team"]
    for market in match.get("markets", []):
        mtype = market.get("type")
        if mtype not in ("胜平负", "让球胜平负"):
            continue
        odds_map = market.get("odds") or {}
        play_type = PLAY_WDL if mtype == "胜平负" else PLAY_HCAP
        category = CATEGORY_LABELS[play_type]
        hc = market.get("handicap")
        hc_label = market.get("handicap_label")
        if play_type == PLAY_WDL and market.get("status") == "未开盘":
            continue
        probs = devig_1x2(odds_map)
        if not probs:
            continue
        for pick, p_true in probs.items():
            odds = float(odds_map[pick])
            ev = compute_ev(p_true, odds)
            status = "eligible"
            reason = None
            if ev < thresholds["reject_below"]:
                status = "rejected"
                reason = f"EV {ev:.1%} < reject_below {thresholds['reject_below']:.0%}"
            label = pick
            if play_type == PLAY_HCAP and hc is not None:
                if pick == "胜":
                    label = f"让球{hc_label} 主胜"
                elif pick == "平":
                    label = f"让球{hc_label} 平"
                else:
                    label = f"让球{hc_label} 客胜"
            out.append(
                Candidate(
                    id=_next_id(counter),
                    match_no=match_no,
                    home_team=home,
                    away_team=away,
                    category=category,
                    play_type=play_type,
                    pick=pick,
                    pick_label=label,
                    odds=odds,
                    p_true=round(p_true, 4),
                    ev=ev,
                    handicap=hc if isinstance(hc, int) else None,
                    handicap_label=hc_label,
                    correlation_unit=_unit_for_match(match_no, pick, play_type),
                    status=status,
                    reject_reason=reason,
                )
            )


def scan_total_goals(
    match: dict[str, Any],
    thresholds: dict[str, float],
    counter: list[int],
    out: list[Candidate],
) -> None:
    match_no = match["match_no"]
    home = match["home_team"]
    away = match["away_team"]
    for market in match.get("markets", []):
        if market.get("type") != "总进球数":
            continue
        odds_map = market.get("odds") or {}
        for bucket, odds_val in odds_map.items():
            if odds_val is None or float(odds_val) <= 1:
                continue
            odds = float(odds_val)
            p_true = p_true_from_odds_single(odds, RETURN_TOTAL)
            ev = compute_ev(p_true, odds)
            status = "eligible"
            reason = None
            if ev < thresholds["reject_below"]:
                status = "rejected"
                reason = f"EV {ev:.1%} < reject_below"
            label = f"总进球 {bucket} 球"
            out.append(
                Candidate(
                    id=_next_id(counter),
                    match_no=match_no,
                    home_team=home,
                    away_team=away,
                    category=CATEGORY_LABELS[PLAY_TOTAL],
                    play_type=PLAY_TOTAL,
                    pick=str(bucket),
                    pick_label=label,
                    odds=odds,
                    p_true=p_true,
                    ev=ev,
                    correlation_unit=f"U_{match_no[-3:]}_TG_{bucket}",
                    status=status,
                    reject_reason=reason,
                )
            )


def scan_scores(
    match: dict[str, Any],
    thresholds: dict[str, float],
    counter: list[int],
    out: list[Candidate],
) -> None:
    match_no = match["match_no"]
    home = match["home_team"]
    away = match["away_team"]
    for market in match.get("markets", []):
        if market.get("type") != "比分":
            continue
        odds_tree = market.get("odds") or {}
        for side, scores in odds_tree.items():
            if not isinstance(scores, dict):
                continue
            for scoreline, odds_val in scores.items():
                if odds_val is None or float(odds_val) <= 1:
                    continue
                odds = float(odds_val)
                p_true = p_true_from_odds_single(odds, RETURN_SCORE)
                ev = compute_ev(p_true, odds)
                status = "eligible"
                reason = None
                if ev < thresholds["reject_below"]:
                    status = "rejected"
                    reason = f"EV {ev:.1%} < reject_below"
                out.append(
                    Candidate(
                        id=_next_id(counter),
                        match_no=match_no,
                        home_team=home,
                        away_team=away,
                        category=CATEGORY_LABELS[PLAY_SCORE],
                        play_type=PLAY_SCORE,
                        pick=scoreline,
                        pick_label=f"{side} {scoreline}",
                        odds=odds,
                        p_true=p_true,
                        ev=ev,
                        correlation_unit=f"U_{match_no[-3:]}_SC_{scoreline}",
                        status=status,
                        reject_reason=reason,
                    )
                )


def scan_hafu(
    match: dict[str, Any],
    thresholds: dict[str, float],
    counter: list[int],
    out: list[Candidate],
) -> None:
    match_no = match["match_no"]
    home = match["home_team"]
    away = match["away_team"]
    for market in match.get("markets", []):
        if market.get("type") != "半全场":
            continue
        odds_map = market.get("odds") or {}
        for pick, odds_val in odds_map.items():
            if odds_val is None or float(odds_val) <= 1:
                continue
            odds = float(odds_val)
            p_true = p_true_from_odds_single(odds, RETURN_HAFU)
            ev = compute_ev(p_true, odds)
            status = "eligible"
            reason = None
            if ev < thresholds["reject_below"]:
                status = "rejected"
                reason = f"EV {ev:.1%} < reject_below"
            out.append(
                Candidate(
                    id=_next_id(counter),
                    match_no=match_no,
                    home_team=home,
                    away_team=away,
                    category=CATEGORY_LABELS[PLAY_HAFU],
                    play_type=PLAY_HAFU,
                    pick=pick,
                    pick_label=f"半全场 {pick}",
                    odds=odds,
                    p_true=p_true,
                    ev=ev,
                    correlation_unit=f"U_{match_no[-3:]}_HF_{pick}",
                    status=status,
                    reject_reason=reason,
                )
            )


def scan_parlays_2x1(
    singles: list[Candidate],
    thresholds: dict[str, float],
    counter: list[int],
    max_legs_pool: int = 12,
) -> list[Candidate]:
    """跨场 2 串 1：各腿来自不同场次、均为 eligible 单关。"""
    eligible = [c for c in singles if c.status == "eligible" and c.play_type != PLAY_PARLAY]
    eligible.sort(key=lambda c: c.ev, reverse=True)
    pool = eligible[:max_legs_pool]
    out: list[Candidate] = []
    for i, a in enumerate(pool):
        for b in pool[i + 1 :]:
            if a.match_no == b.match_no:
                continue
            odds = round(a.odds * b.odds, 2)
            p_true = round(a.p_true * b.p_true, 4)
            ev = compute_ev(p_true, odds)
            status = "eligible"
            reason = None
            if ev < thresholds["reject_below"]:
                status = "rejected"
                reason = f"EV {ev:.1%} < reject_below"
            label = f"{a.match_no[-3:]} {a.pick_label} × {b.match_no[-3:]} {b.pick_label}"
            out.append(
                Candidate(
                    id=_next_id(counter, "P"),
                    match_no=f"{a.match_no}+{b.match_no}",
                    home_team=a.home_team,
                    away_team=b.away_team,
                    category=CATEGORY_LABELS[PLAY_PARLAY],
                    play_type=PLAY_PARLAY,
                    pick="2x1",
                    pick_label=label,
                    odds=odds,
                    p_true=p_true,
                    ev=ev,
                    correlation_unit="U_parlay",
                    status=status,
                    reject_reason=reason,
                    legs=[
                        {"id": a.id, "match_no": a.match_no, "pick_label": a.pick_label, "odds": a.odds},
                        {"id": b.id, "match_no": b.match_no, "pick_label": b.pick_label, "odds": b.odds},
                    ],
                )
            )
    return out


def scan_all(
    odds: dict[str, Any],
    strategy_path: Path | None = None,
    include_parlays: bool = True,
) -> dict[str, Any]:
    thresholds = _load_yaml_thresholds(strategy_path)
    counter = [0]
    candidates: list[Candidate] = []
    matches = odds.get("matches") or []

    for match in matches:
        scan_wdl_and_hcap(match, thresholds, counter, candidates)
        scan_total_goals(match, thresholds, counter, candidates)
        scan_scores(match, thresholds, counter, candidates)
        scan_hafu(match, thresholds, counter, candidates)

    if include_parlays and len(matches) >= 2:
        candidates.extend(scan_parlays_2x1(candidates, thresholds, counter))

    by_category: dict[str, int] = {}
    for c in candidates:
        by_category[c.category] = by_category.get(c.category, 0) + 1

    rejected = sum(1 for c in candidates if c.status == "rejected")
    eligible = [c for c in candidates if c.status == "eligible"]

    return {
        "meta": {
            "schema_version": "1.0",
            "scanned_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "match_date_code": odds.get("match_date_code"),
            "issue_no": odds.get("issue_no"),
            "match_count": len(matches),
            "thresholds": thresholds,
        },
        "scan_summary": {
            "total_candidates": len(candidates),
            "eligible_count": len(eligible),
            "rejected_below": rejected,
            "by_category": by_category,
            "categories_covered": list(CATEGORY_LABELS.values()),
        },
        "candidates": [c.to_dict() for c in candidates],
    }


def _prediction_index(prediction: dict[str, Any]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for row in prediction.get("predictions") or []:
        idx[row.get("match_no", "")] = row
    return idx


def engine_align_score(candidate: Candidate, pred_row: dict | None) -> float:
    """PRD §4.2 Engine_align：与 prediction Top1 同向=100，Top3=70，否则=40。"""
    if not pred_row:
        return 50.0
    pred = pred_row.get("prediction") or {}
    schemes = pred.get("schemes") or []
    if not schemes:
        op = (pred.get("outcome_probs") or {})
        if candidate.play_type in (PLAY_WDL, PLAY_HCAP) and candidate.pick in op:
            top_pick = max(op, key=lambda k: op[k])
            if candidate.pick == top_pick:
                return 100.0
            return 40.0
        return 50.0
    top1 = schemes[0]
    top3 = {s.get("wdl") for s in schemes[:3]}
    wdl = candidate.pick if candidate.play_type in (PLAY_WDL, PLAY_HCAP) else None
    if wdl and wdl == top1.get("wdl"):
        return 100.0
    if wdl and wdl in top3:
        return 70.0
    return 40.0


def fundamentals_score(pred_row: dict | None) -> float:
    if not pred_row:
        return 50.0
    comp = (pred_row.get("prediction") or {}).get("composite") or {}
    ch = float(comp.get("composite_home", 50))
    return round(min(100, max(0, ch)), 1)


def independence_score(correlation_unit: str, all_units: list[str]) -> float:
    """独立单元越少越高：1 单元=100，每多 1 单元 −20。"""
    unique = len(set(all_units))
    return round(max(0, 100 - (unique - 1) * 20), 1)


def rank_top3_picks(
    scored: list[dict[str, Any]],
    ref_stake: int = 100,
) -> list[dict[str, Any]]:
    """T-5-7：在入围池内按命中毛奖金（ref_stake × odds）降序取 Top3 供用户选择。"""
    if not scored:
        return []
    labels = ["方案 A（赢利最高）", "方案 B", "方案 C"]
    enriched: list[dict[str, Any]] = []
    for row in scored:
        odds = float(row["odds"])
        gross = round(ref_stake * odds, 2)
        net = round(ref_stake * (odds - 1.0), 2)
        enriched.append(
            {
                **row,
                "ref_stake": ref_stake,
                "win_gross": gross,
                "win_net": net,
            }
        )
    enriched.sort(
        key=lambda x: (x["win_gross"], x["composite_score"], x["p_true"]),
        reverse=True,
    )
    top3: list[dict[str, Any]] = []
    for i, row in enumerate(enriched[:3], 1):
        pick = dict(row)
        pick["pick_rank"] = i
        pick["pick_label_user"] = labels[i - 1] if i <= len(labels) else f"方案 {i}"
        top3.append(pick)
    return top3


def rank_top6(
    scan_result: dict[str, Any],
    prediction: dict[str, Any] | None = None,
    top_n: int = 6,
) -> dict[str, Any]:
    """T-5-2：EV 降序取 Top N；tie-break: p_true → engine_align。"""
    thresholds = scan_result["meta"]["thresholds"]
    pred_idx = _prediction_index(prediction) if prediction else {}
    eligible = [
        Candidate(**{k: v for k, v in row.items() if k in Candidate.__dataclass_fields__})
        for row in scan_result["candidates"]
        if row.get("status") == "eligible"
    ]
    eligible.sort(
        key=lambda c: (
            c.ev,
            c.p_true,
            engine_align_score(c, pred_idx.get(c.match_no.split("+")[0])),
        ),
        reverse=True,
    )
    top = eligible[:top_n]
    units = [c.correlation_unit for c in top]
    scored: list[dict[str, Any]] = []
    ev_vals = [c.ev for c in top]
    ev_min, ev_max = (min(ev_vals), max(ev_vals)) if ev_vals else (0, 0)

    for rank, c in enumerate(top, 1):
        pred_row = pred_idx.get(c.match_no.split("+")[0])
        ev_norm = 100.0 if ev_max == ev_min else round((c.ev - ev_min) / (ev_max - ev_min) * 100, 1)
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
                "rank": rank,
                "scheme_id": f"S{rank}",
                "candidate_id": c.id,
                "match_no": c.match_no,
                "category": c.category,
                "play_type": c.play_type,
                "pick_label": c.pick_label,
                "odds": c.odds,
                "p_true": c.p_true,
                "ev": c.ev,
                "dims": {
                    "ev_norm": ev_norm,
                    "engine": eng,
                    "fundamentals": fund,
                    "independence": indep,
                },
                "composite_score": composite,
                "status": "入围",
                "correlation_unit": c.correlation_unit,
            }
        )

    if scored:
        scored.sort(key=lambda x: (x["composite_score"], x["ev"]), reverse=True)
        for i, row in enumerate(scored, 1):
            row["rank"] = i
            row["scheme_id"] = f"S{i}"
        scored[0]["status"] = "主推"

    top3 = rank_top3_picks(scored)

    return {
        "top6": scored,
        "top3": top3,
        "hero": scored[0] if scored else None,
        "rejected_below_count": scan_result["scan_summary"]["rejected_below"],
        "eligible_not_in_top6": max(0, len(eligible) - len(top)),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
