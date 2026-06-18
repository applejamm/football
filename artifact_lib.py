"""产物格式约定：过程文档默认 JSON；HTML/MD 视图从 JSON 派生；人类报告统一落盘 reports/。"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 人类可读报告统一目录（promote 交付、回测报告等）
REPORTS_DIR = ROOT / "reports"
BACKTEST_REPORTS_DIR = REPORTS_DIR / "backtest"

# 过程快照 JSON 统一目录
SNAPSHOTS_DIR = ROOT / "snapshots"
SNAPSHOT_ODDS_DIR = SNAPSHOTS_DIR / "odds"
SNAPSHOT_PREDICTION_DIR = SNAPSHOTS_DIR / "prediction"
SNAPSHOT_FUNDAMENTALS_DIR = SNAPSHOTS_DIR / "fundamentals"
SNAPSHOT_DIFFS_DIR = SNAPSHOTS_DIR / "diffs"
SNAPSHOT_RAW_DIR = SNAPSHOTS_DIR / "raw"

SNAPSHOT_KIND_DIRS = {
    "odds": SNAPSHOT_ODDS_DIR,
    "prediction": SNAPSHOT_PREDICTION_DIR,
    "fundamentals": SNAPSHOT_FUNDAMENTALS_DIR,
    "diffs": SNAPSHOT_DIFFS_DIR,
    "raw": SNAPSHOT_RAW_DIR,
}


def ensure_snapshot_dirs() -> None:
    for path in SNAPSHOT_KIND_DIRS.values():
        path.mkdir(parents=True, exist_ok=True)


def latest_in_dirs(pattern: str, dirs: list[Path]) -> Path | None:
    candidates: list[Path] = []
    for directory in dirs:
        if directory.is_dir():
            candidates.extend(directory.glob(pattern))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def odds_search_dirs() -> list[Path]:
    return [SNAPSHOT_ODDS_DIR, ROOT]


def prediction_search_dirs() -> list[Path]:
    return [SNAPSHOT_PREDICTION_DIR, ROOT]


def fundamentals_search_dirs() -> list[Path]:
    return [SNAPSHOT_FUNDAMENTALS_DIR, ROOT]


def rel_snapshot(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def resolve_snapshot(ref: str) -> Path:
    """解析 meta/CLI 中的快照路径（snapshots/ 或遗留根目录）。"""
    p = Path(ref)
    if p.is_absolute():
        return p
    direct = ROOT / ref
    if direct.is_file():
        return direct
    name = p.name
    for base in (
        SNAPSHOT_ODDS_DIR,
        SNAPSHOT_PREDICTION_DIR,
        SNAPSHOT_FUNDAMENTALS_DIR,
        SNAPSHOT_DIFFS_DIR,
        ROOT,
    ):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return direct


def snapshot_path(kind: str, filename: str) -> Path:
    directory = SNAPSHOT_KIND_DIRS[kind]
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename

# 过程文档（prediction / fundamentals / validation draft / gate report）默认不写 MD
DEFAULT_EMIT_MD = False

# 阶段2 prediction 默认不写独立 HTML（promote 时与决策合并为 report_*.html）
DEFAULT_EMIT_HTML = False

# 视图产物（HTML / 可选 MD）一律从已落盘 JSON 生成，禁止与 JSON 并行双写
VIEWS_FROM_JSON = True


def ensure_reports_dir(subdir: str | None = None) -> Path:
    path = REPORTS_DIR / subdir if subdir else REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def delivery_path(filename: str, *, subdir: str | None = None) -> Path:
    """正式人类交付物路径（默认 reports/ 根下）。"""
    return ensure_reports_dir(subdir) / filename


def add_emit_md_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--emit-md",
        action="store_true",
        help="额外从 JSON 派生 Markdown（默认仅 JSON + 由 JSON 生成的 HTML）",
    )


def add_emit_html_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--emit-html",
        action="store_true",
        help="额外从 JSON 派生独立 prediction HTML（默认 promote 时合并为 report_*.html）",
    )
