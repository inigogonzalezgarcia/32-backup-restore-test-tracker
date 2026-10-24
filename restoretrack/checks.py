"""The checks: backup coverage against each system's tier and RPO, restore tests against the test plan and the RTO, and DR exercises
with their actions. Each finding says what to do and who owns it."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .model import Data, System

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Backups", "Restore tests", "DR exercises")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6) -> str:
    return ", ".join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def protected(d: Data) -> list[System]:
    return [s for s in d.systems if s.status == "active" and s.in_scope]


# ---------------------------------------------------------------- per system

def system_rows(d: Data) -> list[dict]:
    s, now, today = d.settings, d.as_of, d.today
    jobs, tests = {}, {}
    for j in d.jobs:
        if j.start <= now:
            jobs.setdefault(j.system.lower(), []).append(j)
    for t in d.tests:
        if t.date <= today:
            tests.setdefault(t.system.lower(), []).append(t)
    out = []
    for sy in protected(d):
        cfg = s.tier(sy.tier)
        js = sorted(jobs.get(sy.system.lower(), []), key=lambda j: j.start)
        prim = [j for j in js if j.copy == "primary"]
        last_ok = max((j.end or j.start for j in prim if j.status != "failed"), default=None)
        hours = round((now - last_ok).total_seconds() / 3600, 1) if last_ok else None
        streak = 0
        for j in reversed(prim):
            if j.status == "failed":
                streak += 1
            else:
                break
        since = now - timedelta(days=s.copy_window_days)
        copies = sorted({j.copy for j in js if j.copy != "primary" and j.status != "failed" and j.start >= since})
        missing = [c for c in cfg["copies"] if c not in copies and not (c == "offsite" and ("tape" in copies or "immutable" in copies))]
        ts = sorted(tests.get(sy.system.lower(), []), key=lambda t: t.date)
        last = ts[-1] if ts else None
        passes = [t for t in ts if t.result == "pass"]
        last_pass = passes[-1] if passes else None
        full = [t for t in passes if t.full]
        last_full = full[-1] if full else None
        due = (last_pass.date + timedelta(days=cfg["test_days"])) if last_pass else None
        overdue = (today - due).days if due and due < today else (None if last_pass else 0)
        # the restore time only says something about the RTO when the whole system was brought back
        rto_t = round(last_full.duration_min / 60, 1) if last_full and last_full.duration_min is not None else None
        rpo_t = last_pass.data_age_hours if last_pass else None
        full_due = cfg.get("full_test_days") or 0
        no_full = bool(full_due) and (last_full is None or (today - last_full.date).days > full_due)
        issues = []
        if not js:
            issues.append("no backup job")
        elif hours is None or hours > sy.rpo_hours:
            issues.append(f"last good backup {hours:.0f} h ago (RPO {sy.rpo_hours:g} h)" if hours is not None else "no successful backup")
        if streak >= s.fail_streak:
            issues.append(f"{streak} failed runs in a row")
        if js and missing:
            issues.append("no " + " or ".join(missing) + f" copy in {s.copy_window_days} days")
        if not ts:
            issues.append("never tested")
        elif last_pass is None:
            issues.append(f"no successful restore test (last {last.result} on {last.date:%d %b %Y})")
        else:
            if last is not last_pass and last.result != "pass":
                issues.append(f"last test {last.result} on {last.date:%d %b} with no retest")
            if overdue:
                issues.append(f"restore test overdue {overdue} days")
            if rto_t is not None and rto_t > sy.rto_hours:
                issues.append(f"tested restore took {rto_t:g} h (RTO {sy.rto_hours:g} h)")
            if rpo_t is not None and rpo_t > sy.rpo_hours:
                issues.append(f"restored data was {rpo_t:g} h old (RPO {sy.rpo_hours:g} h)")
        if ts and no_full:
            issues.append(f"no full restore test in {full_due} days")
        crit = sy.tier == "1" and any(x for x in issues if x.startswith(("no backup", "no successful", "last good", "never tested", "last test")) or
                                      "immutable" in x)
        rag = "red" if crit else "amber" if issues else "green"
        out.append(dict(system=sy.system, service=sy.service, owner=sy.owner, tier=sy.tier, rpo=sy.rpo_hours, rto=sy.rto_hours, platform=sy.platform,
                        site=sy.site, jobs=len(js), last_ok=last_ok, hours=hours, streak=streak, copies=copies, missing=missing if js else [],
                        tests=len(ts), last=last, last_pass=last_pass, last_full=last_full, due=due, overdue=overdue, rto_tested=rto_t,
                        rpo_tested=rpo_t, no_full=no_full and bool(ts), issues=issues, rag=rag))
    order = {"red": 0, "amber": 1, "green": 2}
    out.sort(key=lambda r: (order[r["rag"]], r["tier"], r["system"]))
    return out


def orphan_jobs(d: Data) -> list[dict]:
    known = {s.system.lower(): s for s in d.systems}
    since = d.as_of - timedelta(days=d.settings.job_window_days)
    seen: dict[str, dict] = {}
    for j in d.jobs:
        if j.start < since:
            continue
        sy = known.get(j.system.lower())
        if sy is None or sy.status == "decommissioned" or not sy.in_scope:
            why = "not in the register" if sy is None else "decommissioned" if sy.status == "decommissioned" else "out of scope"
            r = seen.setdefault(j.system.lower(), dict(system=j.system, why=why, runs=0, gb=0.0, jobs=set()))
            r["runs"] += 1
            r["gb"] += j.size_gb
            r["jobs"].add(j.job)
    return sorted(seen.values(), key=lambda r: -r["gb"])


def dr_rows(d: Data) -> dict:
    today, s = d.today, d.settings
    done = sorted([e for e in d.exercises if e.done and e.done <= today], key=lambda e: e.done)
    last = done[-1] if done else None
    missed = [e for e in d.exercises if e.planned and e.planned < today and not e.done]
    upcoming = sorted([e for e in d.exercises if e.planned and e.planned >= today and not e.done], key=lambda e: e.planned)
    overdue = [a for a in d.actions if a.status == "open" and a.due and a.due < today]
    open_ = [a for a in d.actions if a.status == "open"]
    age = (today - last.done).days if last else None
    return dict(last=last, age=age, stale=age is None or age > s.dr_exercise_days, missed=missed, upcoming=upcoming, overdue=overdue, open=open_)


# ---------------------------------------------------------------- findings

def run_all(d: Data, b: dict | None = None) -> list[Finding]:
    s = d.settings
    b = b or dict(sys=system_rows(d), orphans=orphan_jobs(d), dr=dr_rows(d))
    rows, f = b["sys"], []
    lab = lambda r: f"{r['system']} (tier {r['tier']})"  # noqa: E731

    def add(code, area, rows_, crit_rows, subject, detail_fn, fix, owner):
        if not rows_:
            return
        f.append(Finding(CRITICAL if crit_rows else WARNING, area, code, subject(len(rows_)),
                         _top([detail_fn(r) for r in sorted(rows_, key=lambda r: (r["tier"], r["system"]))]), fix, owner,
                         [r["system"] for r in rows_]))

    nojob = [r for r in rows if r["jobs"] == 0]
    add("BKP-01", "Backups", nojob, [r for r in nojob if r["tier"] == "1"], lambda k: f"{_n(k, 'system')} in scope with no backup job",
        lambda r: f"{lab(r)} · {r['service'] or r['platform']}",
        "Add each system to a backup job today and run it; then find out how it was missed (new systems should not go live without backup).",
        s.owner("backup"))
    stale = [r for r in rows if r["jobs"] and (r["hours"] is None or r["hours"] > r["rpo"])]
    add("BKP-02", "Backups", stale, [r for r in stale if r["tier"] == "1"], lambda k: f"{_n(k, 'system')} outside the RPO",
        lambda r: f"{lab(r)} {r['hours']:.0f} h vs {r['rpo']:g} h" if r["hours"] is not None else f"{lab(r)} never",
        "Fix the failing job and run it now; if it cannot run before the business day, tell the service owner that the RPO is not met.",
        s.owner("backup"))
    streak = [r for r in rows if r["streak"] >= s.fail_streak and r not in stale]
    add("BKP-03", "Backups", streak, [], lambda k: f"{_n(k, 'system')} failing {s.fail_streak}+ runs in a row, still inside the RPO",
        lambda r: f"{lab(r)} ({r['streak']} failures)",
        "Look at the job log before the RPO runs out: repeated failures are usually credentials, snapshots or a full repository.", s.owner("backup"))
    nocopy = [r for r in rows if r["missing"]]
    add("BKP-04", "Backups", nocopy, [r for r in nocopy if r["tier"] == "1" and "immutable" in r["missing"]],
        lambda k: f"{_n(k, 'system')} without the copies their tier requires",
        lambda r: f"{lab(r)} no {' or '.join(r['missing'])}",
        "Re-enable or create the copy job; a backup with no immutable or offsite copy does not survive ransomware or the loss of the site.",
        s.owner("backup"))
    if b["orphans"]:
        gb = sum(r["gb"] for r in b["orphans"])
        f.append(Finding(INFO, "Backups", "BKP-05", f"{_n(len(b['orphans']), 'system')} still backed up but not in scope ({gb:,.0f} GB in {s.job_window_days} days)",
                         _top([f"{r['system']} ({r['why']})" for r in b["orphans"]]),
                         "Confirm with the owners and remove the jobs, keeping the last backups for the agreed retention.", s.owner("backup"),
                         [r["system"] for r in b["orphans"]]))
    never = [r for r in rows if r["tests"] == 0]
    add("TST-01", "Restore tests", never, [r for r in never if r["tier"] == "1"], lambda k: f"{_n(k, 'system')} never restored in a test",
        lambda r: lab(r), "Schedule a restore test for each one, tier 1 first; a backup that has never been restored is a hope, not a control.",
        s.owner("tests"))
    failed = [r for r in rows if r["last"] and r["last"].result != "pass" and (r["last_pass"] is None or r["last"].date > r["last_pass"].date)]
    add("TST-02", "Restore tests", failed, [r for r in failed if r["tier"] == "1"], lambda k: f"{_n(k, 'system')} whose last restore test did not pass",
        lambda r: f"{lab(r)} {r['last'].result} on {r['last'].date:%d %b}" + (f": {r['last'].notes}" if r["last"].notes else ""),
        "Fix the cause with the application owner and repeat the test; until then the system counts as untested.", s.owner("tests"))
    late = [r for r in rows if r["overdue"]]
    add("TST-03", "Restore tests", late, [], lambda k: f"{_n(k, 'restore test')} overdue against the test plan",
        lambda r: f"{lab(r)} {r['overdue']} days", "Book the tests in the next change window, tier 1 first.", s.owner("tests"))
    slow = [r for r in rows if (r["rto_tested"] is not None and r["rto_tested"] > r["rto"]) or (r["rpo_tested"] is not None and r["rpo_tested"] > r["rpo"])]
    add("TST-04", "Restore tests", slow, [], lambda k: f"{_n(k, 'system')} restored slower or older than the target",
        lambda r: f"{lab(r)} " + "; ".join(x for x in (f"{r['rto_tested']:g} h vs RTO {r['rto']:g} h" if r["rto_tested"] is not None and r["rto_tested"] > r["rto"] else "",
                                                       f"data {r['rpo_tested']:g} h old vs RPO {r['rpo']:g} h" if r["rpo_tested"] is not None and r["rpo_tested"] > r["rpo"] else "") if x),
        "Either speed up the restore (instant recovery, more frequent backups, a closer copy) or agree a realistic target with the service owner; "
        "the number on paper should be the one the test can deliver.", s.owner("apps"))
    nofull = [r for r in rows if r["no_full"]]
    add("TST-05", "Restore tests", nofull, [], lambda k: f"{_n(k, 'system')} only tested with file or item restores",
        lambda r: lab(r), "Plan a full restore (whole VM, database or service) for each; restoring a file does not prove the system comes back.",
        s.owner("tests"))
    noev = [t for t in d.tests if not t.evidence and t.date >= d.today - timedelta(days=365)]
    if noev:
        f.append(Finding(WARNING, "Restore tests", "TST-06", f"{_n(len(noev), 'restore test')} in the last year with no evidence reference",
                         _top([f"{t.test_id} {t.system} ({t.date:%d %b})" for t in noev]),
                         "Attach the ticket or report to each test: an auditor counts the evidence, not the tests.", s.owner("tests"), [t.test_id for t in noev]))
    dr = b["dr"]
    if dr["stale"]:
        f.append(Finding(CRITICAL, "DR exercises", "DR-01", "No DR exercise in the last year",
                         f"Last exercise: {dr['last'].exercise} on {dr['last'].done:%d %b %Y}." if dr["last"] else "No exercise recorded.",
                         "Agree the date and scope with the business continuity lead and the service owners.", s.owner("dr")))
    for e in dr["missed"]:
        f.append(Finding(WARNING, "DR exercises", "DR-02", f"DR exercise '{e.exercise}' planned for {e.planned:%d %b} and not done",
                         f"Scope: {e.scope}." if e.scope else "No scope recorded.", "Set a new date and record why it moved.", s.owner("dr")))
    if dr["overdue"]:
        f.append(Finding(WARNING, "DR exercises", "DR-03", f"{_n(len(dr['overdue']), 'action')} from DR exercises past the due date",
                         _top([f"{a.action_id} {a.action} ({a.owner or 'no owner'}, due {a.due:%d %b})" for a in dr["overdue"]], 4),
                         "Review them with the owners; an action that keeps moving should be re-planned or accepted as a risk.", s.owner("dr"),
                         [a.action_id for a in dr["overdue"]]))
    f.sort(key=lambda x: (ORDER[x.severity], AREAS.index(x.area), x.code))
    return f


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st
