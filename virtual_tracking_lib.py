"""虚拟跟踪：主推 / Top6 / 被砍注赛后结算（T-5-5 / T-4-11）。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from predict_lib import outcome_from_score

ROOT = Path(__file__).resolve().parent
VIRTUAL_DIR = ROOT / "virtual"
RUNS_DIR = VIRTUAL_DIR / "runs"

TRACK_CLASS_HERO = "主推"
TRACK_CLASS_TOP6 = "Top6入围"
TRACK_CLASS_CUT = "被砍样本"


@dataclass
class VirtualRow:
    issue_no: str
    match_date_code: str
    track_class: str
    scheme_id: str
    candidate_id: str
    match_no: str
    category: str
    pick_label: str
    odds: float
    ev: float
    virtual_stake: int
    score: str
    hit: bool | None
    virtual_pnl: float | None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_match_no(s: str) -> str:
    return re.sub(r"\s+", "", s.strip())


def parse_scores_arg(text: str) -> dict[str, tuple[int, int]]:
    """解析 周二017:2:1,周日010:2-2 格式。"""
    out: dict[str, tuple[int, int]] = {}
    for part in re.split(r"[,;]\s*", text.strip()):
        if not part:
            continue
        m = re.match(r"^([^:]+):(\d+)[:\-](\d+)$", part.strip())
        if not m:
            raise ValueError(f"比分格式无效: {part}（期望 周二017:2:1）")
        out[normalize_match_no(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    return out


def format_score(h: int, a: int) -> str:
    return f"{h}:{a}"


def handicap_wdl(home: int, away: int, handicap: int) -> str:
    """体彩让球：adj_home = home + handicap（正=主队受让，负=主队让球）。"""
    adj = home + handicap
    if adj > away:
        return "胜"
    if adj == away:
        return "平"
    return "负"


def candidate_by_id(candidates: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in candidates}


def evaluate_candidate(
    c: dict[str, Any],
    scores: dict[str, tuple[int, int]],
    pool: dict[str, dict] | None = None,
) -> bool | None:
    """返回 True/False；无比分时 None。"""
    if c.get("play_type") == "parlay":
        legs = c.get("legs") or []
        if not legs or not pool:
            return None
        results: list[bool | None] = []
        for leg in legs:
            leg_c = pool.get(leg["id"])
            if not leg_c:
                return None
            results.append(evaluate_candidate(leg_c, scores, pool))
        if any(r is None for r in results):
            return None
        return all(r for r in results)

    match_no = normalize_match_no(c["match_no"].split("+")[0])
    if match_no not in scores:
        return None
    h, a = scores[match_no]
    pick = c["pick"]
    play = c.get("play_type")

    if play == "wdl":
        return pick == outcome_from_score(h, a)
    if play == "hcap":
        hc = c.get("handicap")
        if hc is None:
            return None
        return pick == handicap_wdl(h, a, int(hc))
    if play == "total":
        total = h + a
        if pick == "7+":
            return total >= 7
        return str(total) == str(pick)
    if play == "score":
        if pick in ("胜其它", "平其它", "负其它"):
            return None
        return format_score(h, a) == pick
    return None


def virtual_pnl(stake: int, odds: float, hit: bool) -> float:
    return round(stake * odds - stake, 2) if hit else float(-stake)


def pick_cut_samples(candidates: list[dict], n: int = 10) -> list[dict]:
    """被砍样本：取 EV 最高（最接近 reject 线）的 N 条。"""
    rejected = [c for c in candidates if c.get("status") == "rejected"]
    rejected.sort(key=lambda x: x.get("ev", -999), reverse=True)
    return rejected[:n]


def build_virtual_rows(
    scan: dict[str, Any],
    scores: dict[str, tuple[int, int]],
    virtual_stake: int = 50,
    cut_sample: int = 10,
) -> list[VirtualRow]:
    meta = scan["meta"]
    issue = meta.get("issue_no") or meta.get("match_date_code", "")
    code = meta.get("match_date_code", "")
    funnel = scan.get("funnel") or {}
    hero = funnel.get("hero")
    top6 = funnel.get("top6") or []
    candidates = scan.get("candidates") or []
    pool = candidate_by_id(candidates)
    rows: list[VirtualRow] = []

    def add_row(c: dict, track_class: str, scheme_id: str, note: str = "") -> None:
        hit = evaluate_candidate(c, scores, pool)
        score_txt = ""
        pnl: float | None = None
        if c.get("play_type") == "parlay":
            parts = []
            for leg in c.get("legs") or []:
                mn = normalize_match_no(leg["match_no"])
                if mn in scores:
                    h, a = scores[mn]
                    parts.append(f"{mn[-3:]} {h}:{a}")
            score_txt = " × ".join(parts)
        else:
            mn = normalize_match_no(c["match_no"].split("+")[0])
            if mn in scores:
                h, a = scores[mn]
                score_txt = format_score(h, a)
        if hit is not None:
            pnl = virtual_pnl(virtual_stake, float(c["odds"]), hit)
        rows.append(
            VirtualRow(
                issue_no=str(issue),
                match_date_code=str(code),
                track_class=track_class,
                scheme_id=scheme_id,
                candidate_id=c.get("id", ""),
                match_no=c.get("match_no", ""),
                category=c.get("category", ""),
                pick_label=c.get("pick_label", c.get("pick", "")),
                odds=float(c["odds"]),
                ev=float(c.get("ev", 0)),
                virtual_stake=virtual_stake,
                score=score_txt,
                hit=hit,
                virtual_pnl=pnl,
                note=note,
            )
        )

    if hero:
        hc = pool.get(hero["candidate_id"])
        if hc:
            add_row(hc, TRACK_CLASS_HERO, hero["scheme_id"], "funnel.hero")

    for t in top6:
        if t.get("status") == "主推":
            continue
        hc = pool.get(t["candidate_id"])
        if hc:
            add_row(hc, TRACK_CLASS_TOP6, t["scheme_id"])

    for i, c in enumerate(pick_cut_samples(candidates, cut_sample), 1):
        add_row(c, TRACK_CLASS_CUT, f"CUT{i}", c.get("reject_reason") or "")

    return rows


def summarize_rows(rows: list[VirtualRow]) -> dict[str, Any]:
    by_class: dict[str, list[VirtualRow]] = {}
    for r in rows:
        by_class.setdefault(r.track_class, []).append(r)

    summary: dict[str, Any] = {"by_class": {}, "cut_hits": []}
    for cls, items in by_class.items():
        settled = [r for r in items if r.hit is not None]
        hits = [r for r in settled if r.hit]
        total_stake = sum(r.virtual_stake for r in settled)
        total_pnl = sum(r.virtual_pnl or 0 for r in settled)
        summary["by_class"][cls] = {
            "count": len(items),
            "settled": len(settled),
            "hits": len(hits),
            "hit_rate": round(len(hits) / len(settled), 3) if settled else None,
            "virtual_stake": total_stake,
            "virtual_pnl": round(total_pnl, 2),
        }
    cut_hits = [r for r in rows if r.track_class == TRACK_CLASS_CUT and r.hit]
    summary["cut_hits"] = [
        {"pick": r.pick_label, "odds": r.odds, "pnl": r.virtual_pnl, "score": r.score}
        for r in cut_hits
    ]
    return summary


def render_virtual_section(
    rows: list[VirtualRow],
    summary: dict[str, Any],
    scan_source: str,
) -> str:
    lines = [
        "## 虚拟跟踪（主推 vs Top6 vs 被砍 · T-5-5）",
        "",
        f"> 来源 `{scan_source}` · 虚拟单注 {rows[0].virtual_stake if rows else 50} 元 · "
        f"更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "### 分类汇总",
        "",
        "| 类别 | 样本数 | 已结算 | 命中 | 命中率 | 虚拟总投注 | 虚拟总收益 |",
        "|---|---|---|---|---|---|---|",
    ]
    for cls in (TRACK_CLASS_HERO, TRACK_CLASS_TOP6, TRACK_CLASS_CUT):
        s = summary["by_class"].get(cls)
        if not s:
            continue
        hr = f"{s['hit_rate']*100:.1f}%" if s["hit_rate"] is not None else "—"
        lines.append(
            f"| {cls} | {s['count']} | {s['settled']} | {s['hits']} | {hr} | "
            f"{s['virtual_stake']} | **{s['virtual_pnl']:+.2f}** |"
        )

    if summary.get("cut_hits"):
        lines.extend(
            [
                "",
                "**本期被砍但虚拟命中**（单期翻盘 ≠ 方法论错）：",
                "",
            ]
        )
        for ch in summary["cut_hits"]:
            lines.append(
                f"- {ch['pick']} @ {ch['odds']} · 比分 {ch['score']} · 虚拟 **{ch['pnl']:+.2f}** 元"
            )

    lines.extend(
        [
            "",
            "### 虚拟跟踪明细",
            "",
            "| 期号 | 类别 | scheme | 场次 | 玩法 | 选项 | 赔率 | EV | 虚拟投注 | 比分 | 命中 | 虚拟收益 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for r in rows:
        hit_s = "✓" if r.hit else ("✗" if r.hit is False else "—")
        pnl_s = f"{r.virtual_pnl:+.2f}" if r.virtual_pnl is not None else "—"
        ev_s = f"{r.ev * 100:.1f}%"
        lines.append(
            f"| {r.issue_no} | {r.track_class} | {r.scheme_id} | {r.match_no} | {r.category} | "
            f"{r.pick_label} | {r.odds} | {ev_s} | {r.virtual_stake} | {r.score} | {hit_s} | {pnl_s} |"
        )
    lines.append("")
    return "\n".join(lines)


def merge_into_tracking(tracking_path: Path, section: str) -> None:
    text = tracking_path.read_text(encoding="utf-8") if tracking_path.exists() else ""
    marker = "## 虚拟跟踪（主推 vs Top6 vs 被砍 · T-5-5）"
    if marker in text:
        head = text.split(marker)[0].rstrip()
        # 去掉旧虚拟段落到下一个 ## 或文件尾
        tail_m = re.search(r"\n## (?!虚拟跟踪)", text.split(marker, 1)[1])
        tail = text.split(marker, 1)[1]
        if tail_m:
            tail = tail[tail_m.start() :]
        else:
            tail = ""
        new_text = head + "\n\n" + section
        if tail.strip():
            new_text += "\n" + tail.lstrip("\n")
    else:
        new_text = text.rstrip() + "\n\n---\n\n" + section
    tracking_path.write_text(new_text.rstrip() + "\n", encoding="utf-8")


def write_run_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
