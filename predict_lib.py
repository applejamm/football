"""PRD 五维权重预测引擎核心库（v1）。"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parent / "weights.yaml"

TEAM_CN_TO_EN: dict[str, str] = {
    "阿根廷": "Argentina", "澳大利亚": "Australia", "奥地利": "Austria", "比利时": "Belgium",
    "巴西": "Brazil", "加拿大": "Canada", "佛得角": "Cape Verde", "哥伦比亚": "Colombia",
    "克罗地亚": "Croatia", "库拉索": "Curacao", "刚果（金）": "D.R. Congo", "刚果金": "Congo DR", "厄瓜多尔": "Ecuador",
    "埃及": "Egypt", "英格兰": "England", "法国": "France", "德国": "Germany", "加纳": "Ghana",
    "海地": "Haiti", "伊朗": "Iran", "科特迪瓦": "Ivory Coast", "日本": "Japan",
    "墨西哥": "Mexico", "摩洛哥": "Morocco", "荷兰": "Netherlands", "新西兰": "New Zealand",
    "巴拿马": "Panama", "巴拉圭": "Paraguay", "葡萄牙": "Portugal", "沙特阿拉伯": "Saudi Arabia",
    "苏格兰": "Scotland", "塞内加尔": "Senegal", "西班牙": "Spain", "瑞典": "Sweden",
    "突尼斯": "Tunisia", "土耳其": "Turkey", "美国": "United States", "乌拉圭": "Uruguay",
    "乌兹别克斯坦": "Uzbekistan", "瑞士": "Switzerland", "韩国": "South Korea", "威尔士": "Wales",
    "丹麦": "Denmark", "波兰": "Poland", "塞尔维亚": "Serbia", "乌克兰": "Ukraine",
    "捷克": "Czechia", "南非": "South Africa", "波黑": "Bosnia and Herzegovina", "卡塔尔": "Qatar",
}

# ESPN / OddsPortal / 体彩英文名差异 → 统一 canonical key（小写）
TEAM_EN_ALIASES: dict[str, str] = {
    "czechia": "czechia",
    "czech republic": "czechia",
    "czech": "czechia",
    "bosnia-herzegovina": "bosnia",
    "bosnia and herzegovina": "bosnia",
    "bosnia": "bosnia",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "south korea": "south korea",
    "turkiye": "turkey",
    "türkiye": "turkey",
    "usa": "united states",
    "u.s.": "united states",
    "d.r. congo": "congo dr",
    "congo dr": "congo dr",
    "curacao": "curacao",
    "curaçao": "curacao",
}


def load_weights(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_WEIGHTS_PATH
    text = p.read_text("utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # 极简 fallback：无 PyYAML 时用 json 兼容子集不可行，要求安装或内嵌默认
    raise RuntimeError("需要 PyYAML：pip install pyyaml")


def normalize_team(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def cn_to_en(cn: str) -> str:
    cn = normalize_team(cn)
    if cn in TEAM_CN_TO_EN:
        return TEAM_CN_TO_EN[cn]
    for k, v in TEAM_CN_TO_EN.items():
        if k in cn or cn in k:
            return v
    return cn


def canonical_en(name: str) -> str:
    raw = normalize_team(name).lower()
    if raw in TEAM_EN_ALIASES:
        return TEAM_EN_ALIASES[raw]
    mapped = cn_to_en(name).lower()
    return TEAM_EN_ALIASES.get(mapped, mapped)


def teams_match(a: str, b: str) -> bool:
    ca, cb = canonical_en(a), canonical_en(b)
    if ca == cb:
        return True
    if ca in cb or cb in ca:
        return True
    a, b = normalize_team(a).lower(), normalize_team(b).lower()
    if a == b or a in b or b in a:
        return True
    return False


def parse_score(score: str | None) -> tuple[int | None, int | None]:
    if not score or "-" not in score:
        return None, None
    parts = score.replace(" ", "").split("-")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def goals_from_events(events: list[dict], team_perspective: str | None = None) -> list[tuple[int, int]]:
    """返回 (gf, ga) 列表。score 格式为 ESPN 主队-客队。"""
    out: list[tuple[int, int]] = []
    for e in events:
        hg, ag = parse_score(e.get("score"))
        if hg is None or ag is None:
            continue
        at = e.get("at_venue")
        if at == "vs":
            out.append((hg, ag))
        elif at == "@":
            out.append((ag, hg))
        else:
            out.append((hg, ag))
    return out


def compute_form_score(events: list[dict]) -> float | None:
    if not events:
        return None
    w = sum(1 for e in events if e.get("result") == "W")
    d = sum(1 for e in events if e.get("result") == "D")
    n = len(events)
    if n == 0:
        return None
    return (w * 3 + d * 1) / (n * 3) * 100


def compute_team_stats(events: list[dict]) -> dict[str, Any]:
    n = len(events)
    if n == 0:
        return {"n": 0, "form_score": None, "win_rate": None, "avg_gf": None, "avg_ga": None}
    wins = sum(1 for e in events if e.get("result") == "W")
    goals = goals_from_events(events)
    if goals:
        avg_gf = sum(g[0] for g in goals) / len(goals)
        avg_ga = sum(g[1] for g in goals) / len(goals)
    else:
        avg_gf = avg_ga = None
    return {
        "n": n,
        "form_score": compute_form_score(events),
        "win_rate": wins / n if n else None,
        "avg_gf": round(avg_gf, 2) if avg_gf is not None else None,
        "avg_ga": round(avg_ga, 2) if avg_ga is not None else None,
    }


def merge_last_n(primary: list[dict], extra: list[dict], n: int = 10) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for e in primary + extra:
        key = f"{e.get('date')}|{e.get('opponent')}|{e.get('score')}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda x: x.get("date") or "", reverse=True)
    return merged[:n]


def h2h_decay_weight(event_date: str, ref_date: str, cfg: dict) -> float:
    try:
        d = datetime.strptime(event_date[:10], "%Y-%m-%d")
        r = datetime.strptime(ref_date[:10], "%Y-%m-%d")
    except ValueError:
        return cfg.get("decay", {}).get("older", 0.2)
    years = (r - d).days / 365.25
    dec = cfg.get("decay", {})
    if years <= 5:
        return dec.get("within_5_years", 1.0)
    if years <= 10:
        return dec.get("within_10_years", 0.5)
    return dec.get("older", 0.2)


def score_h2h_dimension(h2h_blocks: list[dict], ref_date: str, cfg: dict) -> dict[str, Any]:
    events: list[dict] = []
    for b in h2h_blocks or []:
        events.extend(b.get("events") or [])
    if not events:
        return {"score": None, "available": False, "detail": "无 H2H 数据"}
    events = sorted(events, key=lambda x: x.get("date") or "", reverse=True)
    max_m = cfg.get("max_meetings", 3)
    events = events[:max_m]
    w_sum = d_sum = l_sum = 0.0
    draw_rate = 0.0
    total_w = 0.0
    for e in events:
        w = h2h_decay_weight(e.get("date") or ref_date, ref_date, cfg)
        total_w += w
        r = e.get("result")
        if r == "W":
            w_sum += w
        elif r == "D":
            d_sum += w
        else:
            l_sum += w
    if total_w <= 0:
        return {"score": None, "available": False, "detail": "H2H 权重为 0"}
    draw_rate = d_sum / total_w
    advantage = (w_sum - l_sum) / total_w
    score = 50 + advantage * 50
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "available": True,
        "meetings_used": len(events),
        "draw_rate": round(draw_rate, 3),
        "advantage_home": round(advantage, 3),
        "detail": f"近 {len(events)} 次交手（时间衰减），主队 advantage {advantage:+.2f}",
    }


def team_strength_index(stats: dict[str, Any], wcfg: dict) -> float | None:
    fs, wr, gb = stats.get("form_score"), stats.get("win_rate"), None
    if stats.get("avg_gf") is not None and stats.get("avg_ga") is not None:
        gb = (stats["avg_gf"] - stats["avg_ga"] + 3) / 6 * 100
        gb = max(0.0, min(100.0, gb))
    parts: list[tuple[float, float]] = []
    if fs is not None:
        parts.append((fs, wcfg.get("form_weight", 0.4)))
    if wr is not None:
        parts.append((wr * 100, wcfg.get("win_rate_weight", 0.3)))
    if gb is not None:
        parts.append((gb, wcfg.get("goal_balance_weight", 0.3)))
    if not parts:
        return None
    tw = sum(p[1] for p in parts)
    return sum(p[0] * p[1] for p in parts) / tw


def score_strength_dimension(home_stats: dict, away_stats: dict, wcfg: dict) -> dict[str, Any]:
    hi = team_strength_index(home_stats, wcfg)
    ai = team_strength_index(away_stats, wcfg)
    if hi is None or ai is None:
        return {"score": None, "available": False, "detail": "形式/胜率/进失球不足"}
    diff = hi - ai
    score = 50 + diff / 2
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "available": True,
        "home_index": round(hi, 1),
        "away_index": round(ai, 1),
        "detail": f"主队硬实力 {hi:.0f} vs 客队 {ai:.0f}（含近5场形式/进失球、近10场胜率）",
    }


def score_personnel_dimension(features: dict) -> dict[str, Any]:
    missing = features.get("missing") or []
    injuries = features.get("injuries") or []
    rosters = features.get("rosters_size") or []
    if "rosters_lineups_injuries" in missing and not injuries:
        return {"score": 50.0, "available": False, "detail": "暂无：伤停/首发数据未覆盖"}
    if injuries:
        home_pen = sum(1 for i in injuries if i.get("team") == "home" and i.get("severity") != "minor")
        away_pen = sum(1 for i in injuries if i.get("team") == "away" and i.get("severity") != "minor")
        score = 50 + (away_pen - home_pen) * 8
        score = max(0.0, min(100.0, score))
        return {
            "score": round(score, 1),
            "available": True,
            "detail": f"伤病影响：主队缺阵 {home_pen} 人，客队 {away_pen} 人",
        }
    if rosters and any(r.get("size", 0) > 0 for r in rosters):
        return {"score": 50.0, "available": True, "detail": "阵容名单可用，无伤病明细，中性计分"}
    return {"score": 50.0, "available": False, "detail": "暂无：关键人员状态数据未覆盖"}


def score_tournament_dimension(features: dict, news: list[dict], cfg: dict) -> dict[str, Any]:
    keywords = cfg.get("scenario_keywords", {})
    must_win_kw = keywords.get("must_win", [])
    texts = " ".join(
        (n.get("headline") or "") + " " + (n.get("type") or "")
        for n in (news or [])
    ).lower()
    notes: list[str] = []
    score = 50.0
    for kw in must_win_kw:
        if kw.lower() in texts:
            notes.append(f"检测到大赛关键词「{kw}」")
            score = 55.0
    ou = (features.get("consensus_odds") or {}).get("over_under")
    if ou is not None:
        notes.append(f"共识大小球 {ou}（节奏参考）")
    detail = "；".join(notes) if notes else "暂无：出线/气候/海拔数据未覆盖，中性计分"
    return {"score": round(score, 1), "available": bool(notes), "detail": detail}


def devig_1x2(odds: dict[str, float | None]) -> dict[str, float] | None:
    keys = ("胜", "平", "负")
    vals = [odds.get(k) for k in keys]
    if any(v is None or v <= 1 for v in vals):
        return None
    impl = [1.0 / float(v) for v in vals]
    s = sum(impl)
    if s <= 0:
        return None
    return {k: impl[i] / s for i, k in enumerate(keys)}


def score_market_dimension(cn_odds: dict | None, consensus: dict | None) -> dict[str, Any]:
    probs = devig_1x2(cn_odds) if cn_odds else None
    source = "体彩"
    if not probs and consensus:
        # DraftKings moneyline fallback
        def ml_p(ml: float | None) -> float | None:
            if ml is None:
                return None
            ml = float(ml)
            if ml > 0:
                return 100 / (ml + 100)
            if ml < 0:
                return (-ml) / (-ml + 100)
            return None
        h, d, a = ml_p(consensus.get("home_money_line")), ml_p(consensus.get("draw_money_line")), ml_p(consensus.get("away_money_line"))
        if None not in (h, d, a):
            t = h + d + a
            probs = {"胜": h / t, "平": d / t, "负": a / t}
            source = consensus.get("provider") or "consensus"
    if not probs:
        return {"score": None, "available": False, "detail": "无市场赔率"}
    score = probs["胜"] * 100
    return {
        "score": round(score, 1),
        "available": True,
        "probs": {k: round(v, 4) for k, v in probs.items()},
        "detail": f"{source} 去水后主胜 {probs['胜']:.1%} / 平 {probs['平']:.1%} / 客胜 {probs['负']:.1%}",
    }


def composite_home_score(dims: dict[str, dict], weights: dict[str, float], missing_score: float) -> dict[str, Any]:
    total_w = 0.0
    acc = 0.0
    breakdown: dict[str, Any] = {}
    for name, w in weights.items():
        d = dims.get(name, {})
        if d.get("score") is not None:
            s = float(d["score"])
            used = w
        else:
            s = missing_score
            used = w * 0.5  # 缺失维度半权重
        acc += s * used
        total_w += used
        breakdown[name] = {"score": s, "weight": w, "available": d.get("available", False)}
    composite = acc / total_w if total_w else missing_score
    return {"composite_home": round(composite, 2), "breakdown": breakdown}


def composite_to_outcome_probs(composite: float, market_probs: dict[str, float] | None, blend: dict) -> dict[str, float]:
    fw = blend.get("fundamental_weight", 0.35)
    mw = blend.get("market_weight", 0.65)
    # 基本面 composite → 粗略三向概率
    home_edge = (composite - 50) / 50
    fund = {
        "胜": max(0.05, 0.33 + home_edge * 0.35),
        "平": max(0.05, 0.28 - abs(home_edge) * 0.08),
        "负": max(0.05, 0.33 - home_edge * 0.35),
    }
    s = sum(fund.values())
    fund = {k: v / s for k, v in fund.items()}
    if market_probs:
        out = {k: fw * fund[k] + mw * market_probs[k] for k in fund}
    else:
        out = fund
    s2 = sum(out.values())
    return {k: round(out[k] / s2, 4) for k in out}


def expected_goals(home_stats: dict, away_stats: dict, consensus: dict | None) -> tuple[float, float]:
    hg = home_stats.get("avg_gf") or 1.2
    ag = away_stats.get("avg_gf") or 1.0
    hga = home_stats.get("avg_ga") or 1.0
    aga = away_stats.get("avg_ga") or 1.2
    lam_h = max(0.3, (hg + aga) / 2)
    lam_a = max(0.3, (ag + hga) / 2)
    if consensus and consensus.get("over_under"):
        total = float(consensus["over_under"])
        cur = lam_h + lam_a
        if cur > 0:
            scale = total / cur
            lam_h *= scale
            lam_a *= scale
    return round(lam_h, 2), round(lam_a, 2)


def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def scoreline_probs(lam_h: float, lam_a: float, max_g: int = 5) -> dict[str, float]:
    probs: dict[str, float] = {}
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            p = poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
            probs[f"{i}:{j}"] = p
    tail = 1.0 - sum(probs.values())
    if tail > 0:
        probs["其它"] = tail
    s = sum(probs.values())
    return {k: v / s for k, v in probs.items()}


def total_goals_probs(score_probs: dict[str, float]) -> dict[str, float]:
    tg: dict[str, float] = {}
    for sc, p in score_probs.items():
        if sc == "其它":
            tg["7+"] = tg.get("7+", 0) + p
            continue
        i, j = map(int, sc.split(":"))
        t = i + j
        key = "7+" if t >= 7 else str(t)
        tg[key] = tg.get(key, 0) + p
    s = sum(tg.values())
    return {k: round(v / s, 4) for k, v in sorted(tg.items(), key=lambda x: (x[0] == "7+", int(x[0]) if x[0].isdigit() else 99))}


def outcome_from_score(h: int, a: int) -> str:
    if h > a:
        return "胜"
    if h < a:
        return "负"
    return "平"


def build_logic_explain(dims: dict, composite: dict, pick: dict) -> str:
    parts = [f"综合主队优势 {composite['composite_home']:.0f}/100"]
    for name, label in (
        ("strength", "硬实力"), ("personnel", "人员"), ("tournament", "大赛"),
        ("h2h", "H2H"), ("market", "市场"),
    ):
        d = dims.get(name, {})
        if d.get("available"):
            parts.append(f"{label} {d.get('score', '?')}")
    parts.append(f"→ {pick['wdl']} / 总进球 {pick['total_goals']} / 比分 {pick['score']}")
    if pick.get("scenario_note"):
        parts.append(pick["scenario_note"])
    return "；".join(parts)


def detect_scenarios(h2h_dim: dict, news: list[dict], cfg: dict) -> list[str]:
    notes: list[str] = []
    dr = h2h_dim.get("draw_rate")
    if dr is not None and dr >= cfg.get("scenario_keywords", {}).get("high_draw_h2h", 0.45):
        notes.append(f"历史交锋平局率 {dr:.0%}，方案倾向防平")
    injury_kw = cfg.get("scenario_keywords", {}).get("injury", [])
    for n in news or []:
        h = (n.get("headline") or "").lower()
        if any(k in h for k in injury_kw):
            notes.append("赛前新闻含伤病信号，人员维度已下调/上调")
            break
    return notes


def generate_schemes(
    outcome_probs: dict[str, float],
    total_probs: dict[str, float],
    score_probs: dict[str, float],
    dims: dict,
    composite: dict,
    scenario_notes: list[str],
    cfg: dict,
) -> list[dict]:
    min_c = cfg.get("schemes", {}).get("min_count", 3)
    max_c = cfg.get("schemes", {}).get("max_count", 5)
    candidates: list[dict] = []
    top_scores = sorted(score_probs.items(), key=lambda x: -x[1])[:12]
    for sc, sp in top_scores:
        if sc == "其它":
            continue
        h, a = map(int, sc.split(":"))
        wdl = outcome_from_score(h, a)
        tg = str(h + a) if h + a < 7 else "7+"
        op = outcome_probs.get(wdl, 0.1)
        tp = total_probs.get(tg, 0.1)
        combined = op * 0.45 + sp * 0.35 + tp * 0.20
        pick = {
            "wdl": wdl,
            "total_goals": tg,
            "score": sc,
            "combined_prob": round(combined, 4),
            "scenario_note": scenario_notes[0] if scenario_notes else None,
        }
        pick["logic"] = build_logic_explain(dims, composite, pick)
        candidates.append(pick)
    # 补充纯赛果导向方案
    for wdl in sorted(outcome_probs, key=lambda k: -outcome_probs[k]):
        tg = max(total_probs, key=lambda k: total_probs[k])
        combined = outcome_probs[wdl] * 0.6 + total_probs[tg] * 0.4
        pick = {"wdl": wdl, "total_goals": tg, "score": "—", "combined_prob": round(combined, 4), "scenario_note": None}
        pick["logic"] = build_logic_explain(dims, composite, pick)
        candidates.append(pick)
    seen: set[tuple] = set()
    schemes: list[dict] = []
    for c in sorted(candidates, key=lambda x: -x["combined_prob"]):
        key = (c["wdl"], c["total_goals"], c["score"])
        if key in seen:
            continue
        seen.add(key)
        schemes.append({"id": f"P{len(schemes)+1}", **c})
        if len(schemes) >= max_c:
            break
    while len(schemes) < min_c and candidates:
        c = candidates[len(schemes) % len(candidates)]
        key = (c["wdl"], c["total_goals"], c["score"])
        if key not in seen:
            seen.add(key)
            schemes.append({"id": f"P{len(schemes)+1}", **c})
    for i, s in enumerate(schemes, 1):
        s["id"] = f"P{i}"
        s["rank"] = i
    return schemes


def predict_match(
    home: str,
    away: str,
    features: dict[str, Any] | None = None,
    cn_odds: dict[str, float | None] | None = None,
    ref_date: str | None = None,
    weights_path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_weights(weights_path)
    features = features or {}
    ref_date = ref_date or datetime.now().strftime("%Y-%m-%d")
    dim_weights = cfg["dimensions"]
    missing_score = cfg.get("missing_dimension_score", 50.0)

    l5_map = {g["team"]: g.get("events", []) for g in features.get("last_five_games", [])}
    l10_map = {g["team"]: g.get("events", []) for g in features.get("last_ten_games", [])}
    home_ev = l10_map.get(home) or merge_last_n(l5_map.get(home, []), [], 10)
    away_ev = l10_map.get(away) or merge_last_n(l5_map.get(away, []), [], 10)
    home_stats = compute_team_stats(home_ev)
    away_stats = compute_team_stats(away_ev)
    ts = features.get("team_stats") or {}
    if home in ts:
        home_stats = {**home_stats, **ts[home]}
    if away in ts:
        away_stats = {**away_stats, **ts[away]}

    h2h_blocks = features.get("head_to_head", [])
    if features.get("h2h_last_three"):
        h2h_blocks = [{"title": "last_three", "events": features["h2h_last_three"]}]
    dims = {
        "strength": score_strength_dimension(home_stats, away_stats, cfg.get("strength", {})),
        "personnel": score_personnel_dimension(features),
        "tournament": score_tournament_dimension(features, features.get("news_headlines", []), cfg),
        "h2h": score_h2h_dimension(h2h_blocks, ref_date, cfg.get("h2h", {})),
        "market": score_market_dimension(cn_odds, features.get("consensus_odds")),
    }
    composite = composite_home_score(dims, dim_weights, missing_score)
    market_probs = (dims["market"].get("probs") if dims["market"].get("available") else None)
    outcome_probs = composite_to_outcome_probs(composite["composite_home"], market_probs, cfg.get("outcome_blend", {}))
    lam_h, lam_a = expected_goals(home_stats, away_stats, features.get("consensus_odds"))
    sc_probs = scoreline_probs(lam_h, lam_a)
    tg_probs = total_goals_probs(sc_probs)
    scenarios = detect_scenarios(dims["h2h"], features.get("news_headlines", []), cfg)
    schemes = generate_schemes(outcome_probs, tg_probs, sc_probs, dims, composite, scenarios, cfg)

    return {
        "home": home,
        "away": away,
        "ref_date": ref_date,
        "dimensions": dims,
        "composite": composite,
        "outcome_probs": outcome_probs,
        "expected_goals": {"home": lam_h, "away": lam_a},
        "total_goals_probs": tg_probs,
        "top_scorelines": dict(sorted(sc_probs.items(), key=lambda x: -x[1])[:8]),
        "schemes": schemes,
        "scenario_flags": scenarios,
        "home_stats": home_stats,
        "away_stats": away_stats,
    }


def evaluate_scheme(scheme: dict, actual_home: int, actual_away: int) -> bool:
    wdl = outcome_from_score(actual_home, actual_away)
    tg = str(actual_home + actual_away) if actual_home + actual_away < 7 else "7+"
    sc = f"{actual_home}:{actual_away}"
    if scheme.get("wdl") != wdl:
        return False
    if scheme.get("total_goals") != tg:
        return False
    if scheme.get("score") not in (sc, "—"):
        return False
    return True


def find_fundamentals_record(records: list[dict], home_cn: str, away_cn: str) -> dict | None:
    home_en, away_en = cn_to_en(home_cn), cn_to_en(away_cn)
    for r in records:
        ev = r.get("event", {})
        if teams_match(ev.get("home", ""), home_en) and teams_match(ev.get("away", ""), away_en):
            return r
        if teams_match(ev.get("home", ""), home_cn) and teams_match(ev.get("away", ""), away_cn):
            return r
    return None


def extract_cn_1x2_odds(match: dict) -> dict[str, float | None] | None:
    for m in match.get("markets", []):
        if m.get("type") == "胜平负" and m.get("status") == "已开盘":
            return m.get("odds")
        if m.get("type") == "让球胜平负" and m.get("handicap") == 0:
            return m.get("odds")
    for m in match.get("markets", []):
        if m.get("type") == "让球胜平负" and m.get("odds", {}).get("胜"):
            return m.get("odds")
    return None
