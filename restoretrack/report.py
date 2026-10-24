"""Outputs: report.html, restore-review.md and the CSVs (systems, tests due, failing backups, evidence pack, DR actions, actions, findings)."""
from __future__ import annotations

import csv
import html
from datetime import timedelta
from pathlib import Path

from .checks import AREAS, CRITICAL, INFO, WARNING, Finding, area_status, dr_rows, orphan_jobs, system_rows
from .model import Data

e = html.escape


def build(d: Data) -> dict:
    return dict(sys=system_rows(d), orphans=orphan_jobs(d), dr=dr_rows(d))


def summary(d: Data, findings: list[Finding], b: dict) -> dict:
    rows = b["sys"]
    t1 = [r for r in rows if r["tier"] == "1"]
    in_rpo = [r for r in rows if r["jobs"] and r["hours"] is not None and r["hours"] <= r["rpo"]]
    tested = [r for r in rows if r["last_pass"] and not r["overdue"] and not (r["last"] and r["last"].result != "pass" and r["last"].date > r["last_pass"].date)]
    return dict(systems=len(rows), tier1=len(t1), red=sum(r["rag"] == "red" for r in rows), amber=sum(r["rag"] == "amber" for r in rows),
                green=sum(r["rag"] == "green" for r in rows), in_rpo=len(in_rpo), tested=len(tested),
                t1_tested=sum(r in tested for r in t1), copies_ok=sum(not r["missing"] and r["jobs"] > 0 for r in rows),
                due_soon=sum(1 for r in rows if r["due"] and 0 <= (r["due"] - d.today).days <= d.settings.due_soon_days),
                dr_age=b["dr"]["age"], dr_open=len(b["dr"]["open"]), dr_overdue=len(b["dr"]["overdue"]),
                critical=sum(f.severity == CRITICAL for f in findings), warning=sum(f.severity == WARNING for f in findings),
                info=sum(f.severity == INFO for f in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _d(v) -> str:
    return v.strftime("%Y-%m-%d") if v else ""


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


def write_systems(b: dict, path: Path) -> None:
    _w(path, ["system", "service", "owner", "tier", "rpo_h", "rto_h", "last_good_backup", "hours_since", "failed_in_a_row", "copies", "missing_copies",
              "last_test", "last_test_result", "last_pass", "next_test_due", "tested_rto_h", "tested_rpo_h", "rag", "issues"],
       [[r["system"], r["service"], r["owner"], r["tier"], r["rpo"], r["rto"], r["last_ok"].strftime("%Y-%m-%d %H:%M") if r["last_ok"] else "",
         "" if r["hours"] is None else r["hours"], r["streak"], " ".join(r["copies"]), " ".join(r["missing"]), _d(r["last"].date if r["last"] else None),
         r["last"].result if r["last"] else "", _d(r["last_pass"].date if r["last_pass"] else None), _d(r["due"]),
         "" if r["rto_tested"] is None else r["rto_tested"], "" if r["rpo_tested"] is None else r["rpo_tested"], r["rag"], " | ".join(r["issues"])]
        for r in b["sys"]])


def write_tests_due(d: Data, b: dict, path: Path) -> None:
    horizon = d.today + timedelta(days=90)
    rows = [r for r in b["sys"] if r["due"] is None or r["due"] <= horizon]
    rows.sort(key=lambda r: (r["due"] or d.today - timedelta(days=9999), r["tier"]))
    _w(path, ["system", "service", "owner", "tier", "due", "status", "last_pass", "suggested_test", "booked", "done"],
       [[r["system"], r["service"], r["owner"], r["tier"], _d(r["due"]) or "now",
         "never tested" if r["tests"] == 0 else "overdue" if r["overdue"] else "due", _d(r["last_pass"].date if r["last_pass"] else None),
         "full restore" if (r["no_full"] or r["last_full"] is None) and r["tier"] != "3" else "file or item restore", "", ""] for r in rows])


def write_failing(b: dict, path: Path) -> None:
    rows = [r for r in b["sys"] if r["jobs"] == 0 or r["hours"] is None or r["hours"] > r["rpo"] or r["streak"] or r["missing"]]
    _w(path, ["system", "tier", "rpo_h", "hours_since_good_backup", "failed_in_a_row", "missing_copies", "issue"],
       [[r["system"], r["tier"], r["rpo"], "" if r["hours"] is None else r["hours"], r["streak"], " ".join(r["missing"]),
         " | ".join(i for i in r["issues"] if "backup" in i or "failed" in i or "copy" in i)] for r in rows])


def write_evidence(b: dict, path: Path) -> None:
    rows = [r for r in b["sys"] if r["tier"] in ("1", "2")]
    _w(path, ["system", "service", "tier", "rto_target_h", "rpo_target_h", "last_successful_test", "test_type", "tested_rto_h", "tested_rpo_h",
              "evidence", "last_full_restore", "status"],
       [[r["system"], r["service"], r["tier"], r["rto"], r["rpo"], _d(r["last_pass"].date if r["last_pass"] else None),
         r["last_pass"].kind if r["last_pass"] else "", "" if r["rto_tested"] is None else r["rto_tested"], "" if r["rpo_tested"] is None else r["rpo_tested"],
         r["last_pass"].evidence if r["last_pass"] else "", _d(r["last_full"].date if r["last_full"] else None),
         "ok" if r["rag"] == "green" else "; ".join(i for i in r["issues"] if "test" in i or "restore" in i) or "backup issues only"] for r in rows])


def write_dr_actions(d: Data, path: Path) -> None:
    _w(path, ["action_id", "exercise", "action", "owner", "due", "status", "days_late"],
       [[a.action_id, a.exercise, a.action, a.owner, _d(a.due), a.status, (d.today - a.due).days if a.status == "open" and a.due and a.due < d.today else ""]
        for a in d.actions])


# ---------------------------------------------------------------- markdown

def review_md(d: Data, findings: list[Finding], b: dict) -> str:
    s, sm, dr = d.settings, summary(d, findings, b), b["dr"]
    out = [f"# Backup and restore review · {s.organisation}", "", f"As of {d.as_of:%d %b %Y %H:%M} · {sm['systems']} systems in scope "
           f"({sm['tier1']} tier 1).", "", "## Summary", "",
           f"- Systems: {sm['red']} red, {sm['amber']} amber, {sm['green']} green.",
           f"- Backups: {sm['in_rpo']} of {sm['systems']} inside their RPO; {sm['copies_ok']} with the copies their tier requires.",
           f"- Restore tests: {sm['tested']} of {sm['systems']} tested within the plan ({sm['t1_tested']} of {sm['tier1']} tier 1); "
           f"{sm['due_soon']} more due in the next {s.due_soon_days} days.",
           f"- DR: last exercise {sm['dr_age']} days ago; {sm['dr_open']} actions open, {sm['dr_overdue']} past their date." if sm["dr_age"] is not None
           else "- DR: no exercise recorded.",
           f"- Findings: {sm['critical']} critical, {sm['warning']} warnings, {sm['info']} for information.", "", "## Decisions for this review", ""]
    out += [f"- [ ] **{f.code} {f.subject}** ({f.owner or 'owner?'}): {f.detail} → {f.fix}" for f in findings if f.severity != INFO]
    out += ["", "## For information", ""]
    out += [f"- {f.code} {f.subject}: {f.detail}" for f in findings if f.severity == INFO] or ["- Nothing."]
    out += ["", "## Tier 1 at a glance", "", "| System | Last good backup | Copies | Last test | Tested RTO / target | Status |", "|---|---|---|---|---|---|"]
    for r in [x for x in b["sys"] if x["tier"] == "1"]:
        rto = f"{r['rto_tested']:g} h / {r['rto']:g} h" if r["rto_tested"] is not None else f"– / {r['rto']:g} h"
        out.append(f"| {r['system']} | {r['last_ok']:%d %b %H:%M} | {', '.join(r['copies']) or '–'} | "
                   f"{(r['last'].date.strftime('%d %b %Y') + ' ' + r['last'].result) if r['last'] else 'never'} | {rto} | {r['rag']} |"
                   if r["last_ok"] else f"| {r['system']} | none | – | {(r['last'].date.strftime('%d %b %Y') + ' ' + r['last'].result) if r['last'] else 'never'} | {rto} | {r['rag']} |")
    out += ["", "## Restore tests in the next 30 days", ""]
    soon = sorted([r for r in b["sys"] if r["due"] and 0 <= (r["due"] - d.today).days <= s.due_soon_days], key=lambda r: r["due"])
    out += [f"- {r['due']:%d %b}: {r['system']} (tier {r['tier']}, {r['owner']})" for r in soon] or ["- None."]
    if dr["upcoming"]:
        out += ["", "## Next DR exercise", "", f"- {dr['upcoming'][0].exercise}, {dr['upcoming'][0].planned:%d %b %Y}: {dr['upcoming'][0].scope}"]
    out += ["", "Generated by restoretrack from the backup tools' job logs and the restore test register.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical,.red{color:var(--bad)}.warning,.amber{color:var(--warn)}.info{color:var(--info)}.ok,.green{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--ok);margin-right:6px}.dot.red{background:var(--bad)}.dot.amber{background:var(--warn)}
.cal{display:grid;grid-template-columns:repeat(13,1fr);gap:4px}.cal div{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 4px;text-align:center;font-size:12px}
.cal b{display:block;font-size:18px}.cal .hot{border-color:var(--warn)}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}code{font-size:12px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def render_html(d: Data, findings: list[Finding], title: str, b: dict) -> str:
    s, sm, st, dr = d.settings, summary(d, findings, b), area_status(findings), b["dr"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Backup coverage, restore tests and DR exercises · as of {d.as_of:%d %b %Y %H:%M}</p><div class='tiles'>"]
    tiles = [("Systems in scope", str(sm["systems"]), f"{sm['tier1']} tier 1"),
             ("Red", str(sm["red"]), f"{sm['amber']} amber · {sm['green']} green"),
             ("Inside the RPO", f"{sm['in_rpo']}/{sm['systems']}", "last good backup"),
             ("Copies as required", f"{sm['copies_ok']}/{sm['systems']}", "offsite and immutable"),
             ("Tested on plan", f"{sm['tested']}/{sm['systems']}", f"tier 1: {sm['t1_tested']}/{sm['tier1']}"),
             ("Tests due", str(sm["due_soon"]), f"next {s.due_soon_days} days"),
             ("Last DR exercise", f"{sm['dr_age']} d" if sm["dr_age"] is not None else "never", f"{sm['dr_overdue']} actions late"),
             ("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} info")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'OK' if st[a] == 'ok' else st[a].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    h.append("<h2>Tier 1 systems</h2><div class='wrap'><table><tr><th>System</th><th>Last good backup</th><th>Copies</th><th>Last restore test</th>"
             "<th class='num'>Tested RTO</th><th class='num'>Target</th><th>Issues</th></tr>")
    for r in [x for x in b["sys"] if x["tier"] == "1"]:
        last = f"{r['last'].date:%d %b %Y} · {r['last'].kind} · {r['last'].result}" if r["last"] else "never"
        rto_cls = "critical" if r["rto_tested"] is not None and r["rto_tested"] > r["rto"] else ""
        h.append(f"<tr><td class='nw'><span class='dot {r['rag']}'></span><b>{e(r['system'])}</b><br><span class='muted'>{e(r['service'])}</span></td>"
                 f"<td class='nw'>{(r['last_ok'].strftime('%d %b %H:%M') + ' (' + format(r['hours'], 'g') + ' h)') if r['last_ok'] else '–'}</td>"
                 f"<td>{e(', '.join(r['copies']) or '–')}</td><td>{e(last)}</td>"
                 f"<td class='num {rto_cls}'>{'' if r['rto_tested'] is None else format(r['rto_tested'], 'g') + ' h'}</td><td class='num'>{r['rto']:g} h</td>"
                 f"<td>{'<br>'.join(e(i) for i in r['issues']) or '–'}</td></tr>")
    h.append("</table></div>")
    other = [r for r in b["sys"] if r["tier"] != "1" and r["rag"] != "green"]
    if other:
        h.append(f"<h2>Tier 2 and 3 with something to do ({len(other)})</h2><div class='wrap'><table><tr><th>System</th><th>Tier</th><th>Issues</th><th>Owner</th></tr>")
        h += [f"<tr><td class='nw'><span class='dot {r['rag']}'></span><b>{e(r['system'])}</b><br><span class='muted'>{e(r['service'])}</span></td>"
              f"<td>{r['tier']}</td><td>{'<br>'.join(e(i) for i in r['issues'])}</td><td class='nw'>{e(r['owner'])}</td></tr>" for r in other]
        h.append("</table></div>")
    # test calendar: tests due per month for the next 12 months, overdue first
    months = []
    first = d.today.replace(day=1)
    for i in range(12):
        y, m = first.year + (first.month - 1 + i) // 12, (first.month - 1 + i) % 12 + 1
        months.append((y, m))
    over = sum(1 for r in b["sys"] if r["overdue"] or r["tests"] == 0)
    counts = {k: 0 for k in months}
    for r in b["sys"]:
        if r["due"] and (r["due"].year, r["due"].month) in counts and r["due"] >= d.today:
            counts[(r["due"].year, r["due"].month)] += 1
    h.append("<h2>Restore tests due</h2><div class='cal'>")
    h.append(f"<div class='hot'><span class='muted'>Now</span><b class='{'critical' if over else ''}'>{over}</b><span class='muted'>late</span></div>")
    from calendar import month_abbr
    h += [f"<div><span class='muted'>{month_abbr[m]}</span><b>{counts[(y, m)]}</b><span class='muted'>{y % 100:02d}</span></div>" for y, m in months]
    h.append("</div><p class='muted'>Next test date = last successful test + the tier's interval. The list with a booked/done column is in <code>tests-due.csv</code>.</p>")
    # DR
    h.append("<h2>DR exercises</h2><div class='wrap'><table><tr><th>Exercise</th><th>Planned</th><th>Done</th><th>Result</th></tr>")
    for x in sorted(d.exercises, key=lambda x: x.planned or x.done or d.today):
        late = x.planned and x.planned < d.today and not x.done
        h.append(f"<tr><td>{e(x.exercise)}<br><span class='muted'>{e(x.scope)}</span></td><td class='nw {'warning' if late else ''}'>"
                 f"{x.planned:%d %b %Y}</td><td class='nw'>{x.done.strftime('%d %b %Y') if x.done else '–'}</td><td>{e(x.result or ('not done' if late else 'planned'))}</td></tr>"
                 if x.planned else "")
    h.append("</table></div>")
    if dr["open"]:
        h.append(f"<h3>Open actions ({len(dr['open'])}, {len(dr['overdue'])} late)</h3><div class='wrap'><table><tr><th>Action</th><th>Owner</th><th>Due</th></tr>")
        h += [f"<tr><td>{e(a.action)}<br><span class='muted'>{e(a.action_id)} · {e(a.exercise)}</span></td><td class='nw'>{e(a.owner)}</td>"
              f"<td class='nw {'critical' if a.due and a.due < d.today else ''}'>{a.due.strftime('%d %b %Y') if a.due else '–'}</td></tr>"
              for a in sorted(dr["open"], key=lambda a: a.due or d.today)]
        h.append("</table></div>")
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by restoretrack. Fictional demo data unless you ran it on your own exports.</footer></main></body></html>")
    return "".join(h)
