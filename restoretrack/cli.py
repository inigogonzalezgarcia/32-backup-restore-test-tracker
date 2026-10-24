"""Command line: `demo` builds everything from the fictional company, `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import report, simulate
from .checks import run_all
from .model import load, parse_date

OUTPUTS = ("report.html", "restore-review.md", "systems.csv", "tests-due.csv", "failing-backups.csv", "evidence-pack.csv", "dr-actions.csv",
           "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: date | None = None) -> dict:
    d = load(data, as_of)
    b = report.build(d)
    findings = run_all(d, b)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, findings, title, b), encoding="utf-8")
    (out / "restore-review.md").write_text(report.review_md(d, findings, b), encoding="utf-8")
    report.write_systems(b, out / "systems.csv")
    report.write_tests_due(d, b, out / "tests-due.csv")
    report.write_failing(b, out / "failing-backups.csv")
    report.write_evidence(b, out / "evidence-pack.csv")
    report.write_dr_actions(d, out / "dr-actions.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    return report.summary(d, findings, b)


def _date(value: str) -> date:
    d = parse_date(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="restoretrack", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional company to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, help="folder with systems.csv (required) and backup_jobs.csv, restore_tests.csv, dr_exercises.csv, "
                                            "dr_actions.csv, settings.json (optional)")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Backup and restore review")
    rv.add_argument("--as-of", type=_date, help="review date, YYYY-MM-DD (default: settings.json, or the latest job)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, "Proseware Industries · Backup and restore review")
    else:
        try:
            sm = run(a.data, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['systems']} systems ({sm['red']} red, {sm['amber']} amber, {sm['green']} green) · inside RPO {sm['in_rpo']} · copies as required "
          f"{sm['copies_ok']} · tested on plan {sm['tested']} (tier 1 {sm['t1_tested']}/{sm['tier1']}) · last DR exercise "
          f"{sm['dr_age']} days ago · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
