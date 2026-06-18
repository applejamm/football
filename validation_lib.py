"""数据验证门禁共享库（T-3-9 / T-3-10）。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from artifact_lib import (
    ROOT,
    resolve_snapshot,
)

VALIDATION_DIR = ROOT / "validation"
RUNS_DIR = VALIDATION_DIR / "runs"
DRAFTS_DIR = VALIDATION_DIR / "drafts"
LATEST_DIR = VALIDATION_DIR / "latest"
DEFAULT_STRATEGY = (
    ROOT.parent / ".cursor/skills/football-betting-strategist/STRATEGY_DEFAULT.yaml"
)
if not DEFAULT_STRATEGY.exists():
    DEFAULT_STRATEGY = ROOT / "STRATEGY_DEFAULT.yaml"

MATCH_NO_RE = re.compile(r"(周[一二三四五六日]\d{3})")
ODDS_MENTION_RE = re.compile(r"@(\d+\.\d{2,3})\b")
VALIDATION_RUN_ID_RE = re.compile(r"validation_run_id=[\w-]+")
HTML_VALIDATION_COMMENT_RE = re.compile(r"<!--\s*validation_run_id:\s*[\w-]+\s*-->")


class PromoteBlockedError(RuntimeError):
    """门禁未 PASS 或目标不合法时拒绝 promote。"""


@dataclass
class PromoteResult:
    run_id: str
    promoted_at: str
    artifacts: dict[str, str]
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    check_id: str
    status: str  # PASS | FAIL | SKIP
    message: str
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateReport:
    run_id: str
    started_at: str
    overall: str  # PASS | FAIL
    inputs: dict[str, str] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)

    def to_checks_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "overall": self.overall,
            "inputs": self.inputs,
            "checks": [c.to_dict() for c in self.checks],
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_run_id(when: datetime | None = None) -> str:
    dt = when or datetime.now()
    return dt.strftime("%Y%m%d-%H%M%S")


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def ensure_run_dir(run_id: str) -> Path:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_manifest(run_dir: Path, files: dict[str, Path]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "sources": {},
    }
    for key, path in files.items():
        if path is None:
            continue
        p = path.resolve()
        manifest["sources"][key] = {
            "path": rel_path(p),
            "sha256": sha256_file(p) if p.is_file() else None,
            "exists": p.exists(),
        }
    out = run_dir / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def update_latest_link(run_id: str) -> None:
    target = RUNS_DIR / run_id
    if LATEST_DIR.is_symlink() or LATEST_DIR.exists():
        if LATEST_DIR.is_symlink():
            LATEST_DIR.unlink()
        elif LATEST_DIR.is_dir():
            # 旧式目录：写 pointer 文件
            pointer = LATEST_DIR / "RUN_ID"
            pointer.write_text(run_id + "\n", encoding="utf-8")
            return
    try:
        LATEST_DIR.symlink_to(target, target_is_directory=True)
    except OSError:
        LATEST_DIR.mkdir(parents=True, exist_ok=True)
        (LATEST_DIR / "RUN_ID").write_text(run_id + "\n", encoding="utf-8")


def draft_text_from_json(data: dict[str, Any]) -> str:
    """从决策草案 JSON 提取场次/赔率文本，供门禁锚定检查。"""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("match_no", "pick_label", "scheme_id", "odds") and value is not None:
                    parts.append(str(value))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return "\n".join(parts)


def draft_text_for_checks(
    *,
    draft_json: Path | None = None,
    draft_md: Path | None = None,
    draft_html: Path | None = None,
) -> str:
    if draft_json and draft_json.exists():
        return draft_text_from_json(load_json(draft_json))
    if draft_md and draft_md.exists():
        return draft_md.read_text(encoding="utf-8")
    if draft_html and draft_html.exists():
        return draft_html.read_text(encoding="utf-8")
    return ""


def write_report_md(run_dir: Path, report: GateReport, *, emit_md: bool = False) -> Path | None:
    if not emit_md:
        return None
    lines = [
        f"# 数据验证门禁报告 · {report.run_id}",
        "",
        f"- **结论**：**{report.overall}**",
        f"- **时间**：{report.started_at}",
        "",
        "## 输入",
        "",
    ]
    for k, v in report.inputs.items():
        lines.append(f"- `{k}` → `{v}`")
    lines.extend(["", "## 检查项", ""])
    for c in report.checks:
        icon = "✅" if c.status == "PASS" else ("⏭" if c.status == "SKIP" else "❌")
        lines.append(f"### {icon} `{c.check_id}` · {c.status}")
        lines.append("")
        lines.append(c.message)
        if c.status == "FAIL" and (c.expected is not None or c.actual is not None):
            lines.append("")
            lines.append(f"- 期望：`{c.expected}`")
            lines.append(f"- 实际：`{c.actual}`")
        lines.append("")
    if report.overall == "FAIL":
        lines.extend(
            [
                "## 下一步",
                "",
                "1. 修正草案或源数据",
                "2. 重新运行 `validate_gate.py`",
                "3. **不要**在 FAIL 时 promote 根目录正式报告",
                "",
            ]
        )
    out = run_dir / "report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_match_no(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def check_inputs_present(paths: dict[str, Path | None]) -> CheckResult:
    missing = [k for k, p in paths.items() if p is None or not p.exists()]
    if missing:
        return CheckResult(
            "inputs_present",
            "FAIL",
            f"缺少或不存在：{', '.join(missing)}",
            expected="全部输入存在",
            actual=missing,
        )
    return CheckResult("inputs_present", "PASS", "所有声明输入文件存在")


def check_reference_chain(prediction: dict[str, Any], odds_path: Path) -> CheckResult:
    meta = prediction.get("meta") or {}
    src = meta.get("odds_source") or ""
    if not src:
        return CheckResult(
            "reference_chain",
            "FAIL",
            "prediction.meta.odds_source 缺失",
            expected="odds_*.json 路径",
            actual=src,
        )
    resolved = resolve_snapshot(src)
    if resolved.resolve() != odds_path.resolve():
        return CheckResult(
            "reference_chain",
            "FAIL",
            "prediction 引用的 odds 与传入文件不一致",
            expected=src,
            actual=rel_path(odds_path),
        )
    return CheckResult(
        "reference_chain",
        "PASS",
        f"prediction.meta.odds_source 与 `--odds` 一致（{src}）",
    )


def _odds_match_index(odds_data: dict[str, Any]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for m in odds_data.get("matches") or []:
        key = normalize_match_no(m.get("match_no", ""))
        if key:
            idx[key] = m
    return idx


def check_entity_anchor(prediction: dict[str, Any], odds_data: dict[str, Any]) -> CheckResult:
    idx = _odds_match_index(odds_data)
    missing: list[str] = []
    for pr in prediction.get("predictions") or []:
        key = normalize_match_no(pr.get("match_no", ""))
        if key not in idx:
            missing.append(key or "(空场次号)")
    if missing:
        return CheckResult(
            "entity_anchor",
            "FAIL",
            f"prediction 中有场次不在 odds 中：{missing}",
            expected="prediction ⊆ odds.matches",
            actual=missing,
        )
    return CheckResult(
        "entity_anchor",
        "PASS",
        f"prediction 全部 {len(prediction.get('predictions') or [])} 场锚定在 odds",
    )


def check_team_names_anchor(prediction: dict[str, Any], odds_data: dict[str, Any]) -> CheckResult:
    idx = _odds_match_index(odds_data)
    mismatches: list[str] = []
    for pr in prediction.get("predictions") or []:
        key = normalize_match_no(pr.get("match_no", ""))
        om = idx.get(key)
        if not om:
            continue
        home = (pr.get("home_cn") or "").strip()
        away = (pr.get("away_cn") or "").strip()
        if home and home != om.get("home_team"):
            mismatches.append(f"{key} 主队 {home} != {om.get('home_team')}")
        if away and away != om.get("away_team"):
            mismatches.append(f"{key} 客队 {away} != {om.get('away_team')}")
    if mismatches:
        return CheckResult(
            "team_names_anchor",
            "FAIL",
            "队名与 odds 不一致",
            expected="home_cn/away_cn 同 odds",
            actual=mismatches,
        )
    return CheckResult("team_names_anchor", "PASS", "主客队中文名与 odds 一致")


def _collect_odds_values(odds_data: dict[str, Any]) -> set[float]:
    values: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (int, float)):
            values.add(round(float(node), 2))

    for m in odds_data.get("matches") or []:
        for market in m.get("markets") or []:
            walk(market.get("odds"))
    return values


def check_draft_odds_mention(draft_text: str, odds_data: dict[str, Any]) -> CheckResult:
    if not draft_text.strip():
        return CheckResult("draft_odds_mention", "SKIP", "未提供 decision 草案")
    allowed = _collect_odds_values(odds_data)
    mentioned = [float(x) for x in ODDS_MENTION_RE.findall(draft_text)]
    bad = [v for v in mentioned if round(v, 2) not in allowed]
    if bad:
        return CheckResult(
            "draft_odds_mention",
            "FAIL",
            f"草案 @赔率 不在 odds 源中：{bad[:10]}",
            expected="⊆ odds 全部玩法赔率",
            actual=bad[:20],
        )
    return CheckResult(
        "draft_odds_mention",
        "PASS",
        f"草案中 {len(mentioned)} 处 @赔率 均锚定 odds",
    )


def check_draft_match_mention(draft_text: str, odds_data: dict[str, Any]) -> CheckResult:
    if not draft_text.strip():
        return CheckResult("draft_match_mention", "SKIP", "未提供 decision 草案")
    idx = _odds_match_index(odds_data)
    found = {normalize_match_no(x) for x in MATCH_NO_RE.findall(draft_text)}
    unknown = sorted(k for k in found if k not in idx)
    if unknown:
        return CheckResult(
            "draft_match_mention",
            "FAIL",
            f"草案引用了 odds 中不存在的场次：{unknown}",
            expected="⊆ odds.matches",
            actual=unknown,
        )
    return CheckResult(
        "draft_match_mention",
        "PASS",
        f"草案场次号 {len(found)} 个均存在于 odds",
    )


def check_strategy_config(strategy_path: Path) -> CheckResult:
    if not strategy_path.exists():
        return CheckResult(
            "strategy_config",
            "FAIL",
            f"策略文件不存在：{rel_path(strategy_path)}",
        )
    text = strategy_path.read_text(encoding="utf-8")
    required = ["reject_below", "must_have", "max_loss_per_round"]
    missing = [k for k in required if k not in text]
    if missing:
        return CheckResult(
            "strategy_config",
            "FAIL",
            f"策略文件缺少关键字段：{missing}",
            expected=required,
            actual=missing,
        )
    return CheckResult(
        "strategy_config",
        "PASS",
        f"策略配置可读（{rel_path(strategy_path)}）",
    )


def run_gate(
    *,
    odds: Path,
    prediction: Path,
    fundamentals: Path | None = None,
    strategy: Path | None = None,
    draft_json: Path | None = None,
    draft_md: Path | None = None,
    draft_html: Path | None = None,
    run_id: str | None = None,
    emit_md: bool = False,
) -> tuple[GateReport, Path]:
    rid = run_id or make_run_id()
    started = datetime.now().isoformat(timespec="seconds")
    run_dir = ensure_run_dir(rid)

    strategy_path = strategy or DEFAULT_STRATEGY
    file_map = {
        "odds": odds,
        "prediction": prediction,
        "fundamentals": fundamentals,
        "strategy": strategy_path,
        "draft_json": draft_json,
        "draft_md": draft_md,
        "draft_html": draft_html,
    }
    write_manifest(run_dir, {k: v for k, v in file_map.items() if v is not None})

    checks: list[CheckResult] = []
    checks.append(check_inputs_present({"odds": odds, "prediction": prediction}))

    odds_data = load_json(odds)
    prediction_data = load_json(prediction)

    checks.append(check_reference_chain(prediction_data, odds))
    checks.append(check_entity_anchor(prediction_data, odds_data))
    checks.append(check_team_names_anchor(prediction_data, odds_data))
    checks.append(check_strategy_config(strategy_path))

    draft_text = draft_text_for_checks(
        draft_json=draft_json,
        draft_md=draft_md,
        draft_html=draft_html,
    )

    checks.append(check_draft_match_mention(draft_text, odds_data))
    checks.append(check_draft_odds_mention(draft_text, odds_data))

    overall = "PASS" if all(c.status in ("PASS", "SKIP") for c in checks) else "FAIL"
    report = GateReport(
        run_id=rid,
        started_at=started,
        overall=overall,
        inputs={k: rel_path(v) for k, v in file_map.items() if v is not None},
        checks=checks,
    )

    checks_path = run_dir / "checks.json"
    checks_path.write_text(
        json.dumps(report.to_checks_json(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report_md(run_dir, report, emit_md=emit_md)
    update_latest_link(rid)
    return report, run_dir


def validation_run_dir_rel(run_id: str) -> str:
    return f"validation/runs/{run_id}"


def stamp_prediction_meta(data: dict[str, Any], run_id: str) -> dict[str, Any]:
    meta = data.setdefault("meta", {})
    meta["validation_run_id"] = run_id
    meta["validation_promoted_at"] = datetime.now().isoformat(timespec="seconds")
    meta["validation_run_dir"] = validation_run_dir_rel(run_id)
    return data


def stamp_decision_md(text: str, run_id: str) -> str:
    line = (
        f"> 数据验证：`validation_run_id={run_id}` · "
        f"`{validation_run_dir_rel(run_id)}/checks.json`"
    )
    if "validation_run_id=" in text:
        return VALIDATION_RUN_ID_RE.sub(f"validation_run_id={run_id}", text, count=1)
    parts = text.split("\n", 1)
    if len(parts) == 2 and parts[0].startswith("#"):
        return parts[0] + "\n\n" + line + "\n\n" + parts[1]
    return line + "\n\n" + text


def stamp_decision_html(text: str, run_id: str) -> str:
    comment = f"<!-- validation_run_id: {run_id} -->"
    footer_snip = (
        f'<span class="validation-run">validation_run_id={run_id}</span>'
        f'<span class="sep">|</span>'
    )
    out = text
    if HTML_VALIDATION_COMMENT_RE.search(out):
        out = HTML_VALIDATION_COMMENT_RE.sub(comment, out, count=1)
    elif "<head>" in out:
        out = out.replace("<head>", f"<head>\n{comment}", 1)
    else:
        out = comment + "\n" + out
    if "validation_run_id=" in out and "class=\"validation-run\"" in out:
        out = re.sub(
            r'<span class="validation-run">validation_run_id=[\w-]+</span>',
            f'<span class="validation-run">validation_run_id={run_id}</span>',
            out,
            count=1,
        )
    elif "<footer" in out:
        out = re.sub(
            r"(<footer[^>]*>\s*)",
            rf"\1{footer_snip}\n  ",
            out,
            count=1,
        )
    return out


def _assert_promotable_dest(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(VALIDATION_DIR.resolve())
        raise PromoteBlockedError(
            f"正式产物不得写入 validation/ 内：{rel_path(path)}"
        )
    except ValueError:
        pass
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as e:
        raise PromoteBlockedError(f"promote 目标须在项目根目录下：{path}") from e


def _copy_with_stamp(
    src: Path,
    dest: Path,
    *,
    run_id: str,
    kind: str,
    force: bool,
    dry_run: bool,
) -> None:
    _assert_promotable_dest(dest)
    if dest.exists() and not force:
        raise PromoteBlockedError(f"目标已存在，使用 --force 覆盖：{rel_path(dest)}")
    text = src.read_text(encoding="utf-8")
    if kind == "md":
        stamped = stamp_decision_md(text, run_id)
    elif kind == "html":
        stamped = stamp_decision_html(text, run_id)
    else:
        raise ValueError(kind)
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(stamped, encoding="utf-8")


def promote_prediction(
    prediction: Path,
    run_id: str,
    *,
    force: bool = False,
    dry_run: bool = False,
    dest: Path | None = None,
) -> Path:
    """将 validation_run_id 写入 prediction JSON（默认覆盖原文件）。"""
    target = dest or prediction
    _assert_promotable_dest(target)
    if target.exists() and target != prediction and not force:
        raise PromoteBlockedError(f"prediction 目标已存在：{rel_path(target)}")
    data = load_json(prediction)
    stamped = stamp_prediction_meta(data, run_id)
    if dry_run:
        return target
    target.write_text(
        json.dumps(stamped, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def promote_artifacts(
    report: GateReport,
    run_dir: Path,
    *,
    draft_json: Path | None = None,
    draft_md: Path | None = None,
    draft_html: Path | None = None,
    prediction: Path | None = None,
    out_md: Path | None = None,
    out_report: Path | None = None,
    out_html: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    promote_prediction_file: bool = False,
    emit_md: bool = True,
) -> PromoteResult:
    if report.overall != "PASS":
        raise PromoteBlockedError(
            f"门禁 {report.overall}，禁止 promote（run_id={report.run_id}）"
        )

    promoted_at = datetime.now().isoformat(timespec="seconds")
    artifacts: dict[str, str] = {}

    if emit_md:
        md_src = draft_md if draft_md and draft_md.exists() else None
        if not md_src and draft_json and draft_json.exists():
            from generate_decision_draft import write_md_from_json  # noqa: WPS433

            tmp_md = run_dir / f"_promote_{draft_json.stem}.md"
            if not dry_run:
                write_md_from_json(draft_json, tmp_md)
            md_src = tmp_md
        if md_src and md_src.exists():
            from artifact_lib import delivery_path  # noqa: WPS433

            default_name = (
                draft_json.name.replace(".json", ".md")
                if draft_json
                else md_src.name
            )
            if default_name.startswith("_promote_"):
                default_name = default_name[len("_promote_") :]
            dest = out_md or delivery_path(default_name)
            _copy_with_stamp(
                md_src,
                dest,
                run_id=report.run_id,
                kind="md",
                force=force,
                dry_run=dry_run,
            )
            artifacts["decision_md"] = rel_path(dest)

    if draft_json and draft_json.exists() and prediction and prediction.exists():
        from artifact_lib import delivery_path  # noqa: WPS433
        from report_merge_lib import (  # noqa: WPS433
            report_filename_from_decision_json,
            write_merged_report,
        )

        dest = out_report or delivery_path(report_filename_from_decision_json(draft_json))
        if out_html and not out_report:
            dest = out_html
        if not dry_run:
            write_merged_report(
                prediction,
                draft_json,
                dest,
                run_id=report.run_id,
            )
        else:
            _assert_promotable_dest(dest)
            if dest.exists() and not force:
                raise PromoteBlockedError(f"目标已存在，使用 --force 覆盖：{rel_path(dest)}")
        artifacts["report_html"] = rel_path(dest)
    elif draft_json and draft_json.exists():
        from artifact_lib import delivery_path  # noqa: WPS433
        from generate_decision_draft import write_html_from_json  # noqa: WPS433

        dest = out_html or delivery_path(draft_json.name.replace(".json", ".html"))
        tmp_html = run_dir / f"_promote_{draft_json.stem}.html"
        if not dry_run:
            write_html_from_json(draft_json, tmp_html)
            _copy_with_stamp(
                tmp_html,
                dest,
                run_id=report.run_id,
                kind="html",
                force=force,
                dry_run=False,
            )
        elif dry_run:
            _assert_promotable_dest(dest)
            if dest.exists() and not force:
                raise PromoteBlockedError(f"目标已存在，使用 --force 覆盖：{rel_path(dest)}")
        artifacts["decision_html"] = rel_path(dest)
    elif draft_html and draft_html.exists():
        from artifact_lib import delivery_path  # noqa: WPS433

        dest = out_html or delivery_path(draft_html.name)
        _copy_with_stamp(
            draft_html,
            dest,
            run_id=report.run_id,
            kind="html",
            force=force,
            dry_run=dry_run,
        )
        artifacts["decision_html"] = rel_path(dest)

    if promote_prediction_file and prediction and prediction.exists():
        pred_dest = promote_prediction(
            prediction,
            report.run_id,
            force=force,
            dry_run=dry_run,
        )
        artifacts["prediction"] = rel_path(pred_dest)

    if not artifacts:
        raise PromoteBlockedError(
            "无 promote 目标：请提供 --draft-json + --prediction 和/或 --promote-prediction"
        )

    result = PromoteResult(
        run_id=report.run_id,
        promoted_at=promoted_at,
        artifacts=artifacts,
        dry_run=dry_run,
    )

    if not dry_run:
        promote_path = run_dir / "promote.json"
        promote_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["promoted"] = result.to_dict()
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    return result
