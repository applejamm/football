"""赛后复盘：决策注单结算 + tracking 回填 + HTML 赛后态（T-4-9）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from virtual_tracking_lib import (
    evaluate_candidate,
    format_score,
    merge_into_tracking,
    parse_scores_arg,
    render_virtual_section,
    summarize_rows,
    virtual_pnl,
)

MATCH_NO_RE = re.compile(r"(周[一二三四五六日]\d{3})")
ISSUE_RE = re.compile(r"期号\s*(\d+)")
CODE_RE = re.compile(r"(\d{6})")
BET_ROW_RE = re.compile(
    r"^\|\s*\*{0,2}([^|*]+?)\*{0,2}\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([\d.]+)\s*\|\s*\*{0,2}([\d.]+)\s*元"
)


@dataclass
class BetRecord:
    bet_id: str
    match_no: str
    play: str
    pick: str
    odds: float
    stake: float
    teams: str = ""

    def to_candidate(self) -> dict[str, Any]:
        play_type, handicap = parse_play_handicap(self.play)
        return {
            "id": self.bet_id,
            "match_no": self.match_no,
            "play_type": play_type,
            "pick": normalize_pick(self.pick, self.play, self.teams),
            "handicap": handicap,
            "odds": self.odds,
        }


@dataclass
class SettledBet:
    bet: BetRecord
    score: str
    hit: bool
    pnl: float


def parse_play_handicap(play: str) -> tuple[str, int | None]:
    play = play.strip()
    m = re.search(r"让球\[([+-]?\d+)\]", play)
    if m:
        return "hcap", int(m.group(1))
    return "wdl", 0


def parse_teams_from_cell(match_cell: str) -> tuple[str, str] | None:
    """从「周三021 葡萄牙vs刚果金」解析主客队中文名。"""
    body = MATCH_NO_RE.sub("", match_cell).strip()
    parts = re.split(r"\s*vs\s*", body, flags=re.I)
    if len(parts) != 2:
        return None
    return parts[0].strip(), parts[1].strip()


def normalize_pick(pick: str, play: str, teams: str = "") -> str:
    pick = re.sub(r"\*+", "", pick).strip()
    if "客胜" in pick or pick.startswith("负") or "负（" in pick:
        return "负"
    parsed = parse_teams_from_cell(teams) if teams else None
    if parsed and "胜" in pick and "平" not in pick.replace("平局", ""):
        home, away = parsed
        if home and home in pick:
            return "胜"
        if away and away in pick:
            return "负"
    if "平" in pick:
        return "平"
    if "胜" in pick:
        return "胜"
    return pick


def extract_match_no(text: str) -> str | None:
    m = MATCH_NO_RE.search(text)
    return m.group(1) if m else None


def parse_decision_meta(text: str) -> dict[str, str]:
    issue_m = ISSUE_RE.search(text)
    issue = issue_m.group(1) if issue_m else ""
    code = issue[:6] if len(issue) >= 6 else ""
    skel_m = re.search(r"策略骨架[：:]\s*\*{0,2}([A-E])", text)
    skeleton = skel_m.group(1) if skel_m else "A"
    return {"issue_no": issue, "match_date_code": code, "skeleton": skeleton}


def parse_bets_from_md(text: str) -> list[BetRecord]:
    """从决策 MD 行动卡表格解析注单。"""
    bets: list[BetRecord] = []
    in_action = False
    for line in text.splitlines():
        if re.match(r"^##\s+1\.\s+行动卡", line) or re.match(r"^###\s+1\.A", line):
            in_action = True
            continue
        if in_action and line.startswith("## ") and "行动卡" not in line:
            break
        if not in_action or not line.startswith("|"):
            continue
        if "---" in line or "注 ID" in line or "scheme" in line.lower() and "实际比分" in line:
            continue
        # 标准 7 列：ID | 比赛 | 玩法 | 选择 | 赔率 | 金额 | ...
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]
        if len(parts) < 6:
            continue
        bet_id = re.sub(r"\*+", "", parts[0]).strip()
        if bet_id.lower() in ("scheme", "注 id"):
            continue
        match_cell = parts[1]
        match_no = extract_match_no(match_cell)
        if not match_no:
            continue
        try:
            odds = float(parts[4])
            stake = float(re.sub(r"[^\d.]", "", parts[5]))
        except ValueError:
            continue
        bets.append(
            BetRecord(
                bet_id=bet_id,
                match_no=match_no,
                play=parts[2],
                pick=parts[3],
                odds=odds,
                stake=stake,
                teams=match_cell,
            )
        )
    return bets


def settle_bets(bets: list[BetRecord], scores: dict[str, tuple[int, int]]) -> list[SettledBet]:
    out: list[SettledBet] = []
    for b in bets:
        if b.match_no not in scores:
            continue
        h, a = scores[b.match_no]
        hit = evaluate_candidate(b.to_candidate(), scores)
        if hit is None:
            continue
        pnl = virtual_pnl(int(b.stake), b.odds, hit)
        out.append(
            SettledBet(
                bet=b,
                score=format_score(h, a),
                hit=hit,
                pnl=pnl,
            )
        )
    return out


def find_latest_decision(root: Path, code: str) -> Path | None:
    from artifact_lib import REPORTS_DIR  # noqa: WPS433

    patterns = (f"decision_{code}_*.md", f"decision_{code}_workflow_*.md")
    candidates: list[Path] = []
    for base in (REPORTS_DIR, root):
        if not base.is_dir():
            continue
        for pat in patterns:
            candidates.extend(base.glob(pat))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def find_latest_scan(root: Path, code: str) -> Path | None:
    drafts = root / "validation" / "drafts"
    if not drafts.exists():
        return None
    files = sorted(drafts.glob(f"scan_{code}*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def update_tracking_rows(
    tracking_text: str,
    issue_no: str,
    settled: list[SettledBet],
) -> str:
    lines = tracking_text.splitlines()
    bet_map = {s.bet.bet_id: s for s in settled}
    out: list[str] = []
    in_detail = False
    for line in lines:
        if line.startswith("## 注级明细"):
            in_detail = True
            out.append(line)
            continue
        if in_detail and line.startswith("## ") and "注级明细" not in line:
            in_detail = False
        if in_detail and line.startswith("|") and not line.startswith("|---") and "期号" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 12 and cells[0] == issue_no:
                bid = cells[4]
                if bid in bet_map:
                    s = bet_map[bid]
                    mark = "✓" if s.hit else "✗"
                    pnl_s = f"**{s.pnl:+.2f}**" if s.pnl >= 0 else f"**{s.pnl:.2f}**"
                    cells[9] = f"**{s.score}**"
                    cells[10] = mark
                    cells[11] = pnl_s
                    line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out)


def update_decision_md_replay(md_text: str, settled: list[SettledBet]) -> str:
    """填充「复盘 hook」表。"""
    if not settled:
        return md_text
    lines = md_text.splitlines()
    out: list[str] = []
    in_replay = False
    bet_map = {s.bet.bet_id: s for s in settled}
    for line in lines:
        if "复盘 hook" in line or (in_replay and line.startswith("## 4.")):
            in_replay = True
            out.append(line)
            continue
        if in_replay and line.startswith("## ") and "复盘" not in line:
            in_replay = False
        if in_replay and line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells:
                key = re.sub(r"\*+", "", cells[0])
                if key in bet_map:
                    s = bet_map[key]
                    mark = "✓" if s.hit else "✗"
                    pnl_s = f"{s.pnl:+.2f}"
                    while len(cells) < 4:
                        cells.append("")
                    cells[1] = s.score
                    cells[2] = mark
                    cells[3] = pnl_s
                    line = "| " + " | ".join(cells) + " |"
        out.append(line)
    stamp = f"> 赛后复盘：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if stamp not in "\n".join(out):
        for i, line in enumerate(out):
            if line.startswith("> skill:") or line.startswith("> 本报告"):
                out.insert(i, stamp)
                break
    return "\n".join(out)


REPLAY_CSS = """
  body.post-settled .hero-pick.post-hit{border-color:var(--green);box-shadow:0 0 0 2px rgba(74,222,128,.25);}
  body.post-settled .hero-pick.post-miss{border-color:var(--red);box-shadow:0 0 0 2px rgba(248,113,113,.25);}
  body.post-settled .kpi .c.post-win .v{color:var(--green);}
  body.post-settled .kpi .c.post-lose .v{color:var(--red);}
  tr.replay-row.hit td{background:rgba(74,222,128,.12);color:var(--green);}
  tr.replay-row.miss td{background:rgba(248,113,113,.10);color:var(--red);}
"""


def patch_decision_html(html_text: str, settled: list[SettledBet], hero_id: str | None = None) -> str:
    if not settled:
        return html_text
    if "post-settled" not in html_text:
        html_text = html_text.replace("<body>", '<body class="post-settled">')
    if "tr.replay-row.hit" not in html_text and "</style>" in html_text:
        html_text = html_text.replace("</style>", REPLAY_CSS + "\n</style>", 1)

    hero = settled[0] if len(settled) == 1 else next(
        (s for s in settled if s.bet.bet_id == (hero_id or "S1")), settled[0]
    )
    cls = "post-hit" if hero.hit else "post-miss"
    html_text = re.sub(
        r'(<section class="hero-pick"[^>]*)(>)',
        rf'\1 {cls}\2',
        html_text,
        count=1,
    )
    kpi_cls = "post-win" if hero.hit else "post-lose"
    html_text = re.sub(
        r'(<div class="c gold"[^>]*)(>)',
        rf'\1 {kpi_cls}\2',
        html_text,
        count=1,
    )

    # 结局条切实际结果
    profit = hero.pnl
    if hero.hit:
        new_ov = (
            f'<div class="ov-bar">'
            f'<div class="seg" style="width:0%;background:#dc2626;color:#fff;"></div>'
            f'<div class="seg" style="width:100%;background:#22c55e;color:#fff;">'
            f'命中<small>{profit:+.0f} · 实际</small></div></div>'
        )
    else:
        new_ov = (
            f'<div class="ov-bar">'
            f'<div class="seg" style="width:100%;background:#dc2626;color:#fff;">'
            f'未中<small>{profit:.0f} · 实际</small></div>'
            f'<div class="seg" style="width:0%;background:#22c55e;color:#fff;"></div></div>'
        )
    ov_pat = r'(<div class="ov-bar">)(.*?)(</div>)'
    html_text = re.sub(ov_pat, new_ov, html_text, count=1, flags=re.S)

    # 复盘表：插入或更新
    rows_html = ""
    for s in settled:
        rc = "hit" if s.hit else "miss"
        mark = "✓" if s.hit else "✗"
        rows_html += (
            f'<tr class="replay-row {rc}"><td>{s.bet.bet_id}</td>'
            f'<td>{s.bet.teams or s.bet.match_no}</td>'
            f'<td class="num">{s.score}</td>'
            f'<td>{mark}</td>'
            f'<td class="num">{s.pnl:+.2f}</td></tr>\n'
        )
    replay_block = f"""
<h2>🔄 复盘（T-4-9 已结算）</h2>
<table class="t replay">
  <thead><tr><th>注 ID</th><th>比赛</th><th>实际比分</th><th>命中？</th><th>实际收益</th></tr></thead>
  <tbody>
{rows_html}  </tbody>
</table>
"""
    if "table.t.replay" in html_text or "class=\"t replay\"" in html_text:
        html_text = re.sub(
            r"<table class=\"t replay\">.*?</table>",
            replay_block.strip(),
            html_text,
            count=1,
            flags=re.S,
        )
    else:
        html_text = html_text.replace("<footer>", replay_block + "\n<footer>", 1)

    return html_text


def run_virtual_if_scan(
    scan_path: Path | None,
    scores: dict[str, tuple[int, int]],
    virtual_stake: int,
    tracking_path: Path,
    scan_loader,
) -> str | None:
    if not scan_path or not scan_path.exists():
        return None
    scan = scan_loader(scan_path)
    from virtual_tracking_lib import build_virtual_rows

    rows = build_virtual_rows(scan, scores, virtual_stake=virtual_stake)
    summary = summarize_rows(rows)
    section = render_virtual_section(rows, summary, scan_path.name)
    merge_into_tracking(tracking_path, section)
    return section
