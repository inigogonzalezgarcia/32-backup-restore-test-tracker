"""Fictional demo: Proseware Industries, a made-up manufacturer with a head office, a plant and an Azure subscription, reviewed on
25 October 2026, with the problems placed on purpose. Deterministic (seed 32)."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

AS_OF = datetime(2026, 10, 25, 8, 0)
TODAY = AS_OF.date()

# system, service, owner, tier, platform, site
SYSTEMS = [
    ("erp-db01", "ERP database", "Finance systems", "1", "SQL Server", "HQ"),
    ("erp-app01", "ERP application server", "Finance systems", "1", "VM", "HQ"),
    ("erp-app02", "ERP application server", "Finance systems", "1", "VM", "HQ"),
    ("mes-app01", "MES application", "Plant systems", "1", "VM", "Plant"),
    ("mes-db01", "MES database", "Plant systems", "1", "SQL Server", "Plant"),
    ("mes-hist01", "MES historian", "Plant systems", "1", "VM", "Plant"),
    ("plm-db01", "PLM database", "Engineering", "1", "SQL Server", "HQ"),
    ("payroll-db01", "Payroll database", "HR systems", "1", "SQL Server", "HQ"),
    ("ad-dc01", "Active Directory", "Infrastructure", "1", "VM", "HQ"),
    ("ad-dc02", "Active Directory", "Infrastructure", "1", "VM", "Plant"),
    ("m365-mail", "Exchange Online mailboxes", "Infrastructure", "1", "Microsoft 365", "Cloud"),
    ("fs-hq01", "File server HQ", "Infrastructure", "1", "VM", "HQ"),
    ("wms-db01", "Warehouse management database", "Logistics", "1", "SQL Server", "Plant"),
    ("edi-gw01", "EDI gateway", "Logistics", "1", "VM", "Azure"),
]
TIER2 = [("crm-db01", "CRM database", "Sales", "SQL Server", "Azure"), ("crm-app01", "CRM application", "Sales", "VM", "Azure"),
         ("dw-db01", "Data warehouse", "BI", "SQL Server", "HQ"), ("bi-app01", "BI reporting", "BI", "VM", "HQ"),
         ("sql-bi01", "BI staging database", "BI", "SQL Server", "HQ"), ("fs-plant01", "File server plant", "Infrastructure", "VM", "Plant"),
         ("fs-plant02", "File server plant engineering", "Infrastructure", "VM", "Plant"), ("qa-lims01", "Quality lab system", "Quality", "VM", "Plant"),
         ("hr-app01", "HR portal", "HR systems", "VM", "Azure"), ("m365-sharepoint", "SharePoint Online sites", "Infrastructure", "Microsoft 365", "Cloud"),
         ("m365-onedrive", "OneDrive for Business", "Infrastructure", "Microsoft 365", "Cloud"), ("cad-lic01", "CAD licence server", "Engineering", "VM", "HQ"),
         ("pdm-app01", "Product data vault", "Engineering", "VM", "HQ"), ("scada-hist02", "Line SCADA history", "Plant systems", "VM", "Plant"),
         ("maint-app01", "Maintenance management", "Plant systems", "VM", "Plant"), ("tms-app01", "Transport management", "Logistics", "VM", "Azure"),
         ("portal-web01", "Supplier portal", "Purchasing", "VM", "Azure"), ("portal-db01", "Supplier portal database", "Purchasing", "SQL Server", "Azure"),
         ("treasury-app01", "Treasury", "Finance systems", "VM", "HQ"), ("expense-app01", "Expenses", "Finance systems", "VM", "Azure"),
         ("doc-mgmt01", "Document management", "Quality", "VM", "HQ"), ("itsm-app01", "Service desk", "Infrastructure", "VM", "Azure"),
         ("pki-ca01", "Certificate authority", "Infrastructure", "VM", "HQ"), ("radius01", "Wi-Fi authentication", "Infrastructure", "VM", "HQ"),
         ("vcenter01", "vCenter", "Infrastructure", "VM", "HQ"), ("backup-cfg", "Backup server configuration", "Infrastructure", "VM", "HQ"),
         ("intranet-app01", "Intranet", "Communications", "VM", "Azure"), ("labels-app01", "Label printing", "Logistics", "VM", "Plant"),
         ("energy-mon01", "Energy monitoring", "Plant systems", "VM", "Plant"), ("access-ctl01", "Building access control", "Facilities", "VM", "HQ")]
TIER3 = {"print01": "Print server HQ", "print02": "Print server plant", "wsus01": "Windows updates", "kms01": "Licence activation",
         "jump01": "Admin jump host", "jump02": "Admin jump host plant", "dev-build01": "Build server", "dev-git01": "Source code server",
         "dev-web01": "Development web server", "test-erp01": "ERP test", "test-mes01": "MES test", "test-crm01": "CRM test",
         "monitor01": "Monitoring", "syslog01": "Log collector", "ntp01": "Time server", "deploy01": "Software deployment", "mdt01": "OS deployment",
         "pdq01": "Patch deployment", "lab-vm01": "IT lab", "lab-vm02": "IT lab", "train-erp01": "ERP training", "kiosk-img01": "Kiosk images",
         "archive-fs01": "File archive", "scan01": "Scan to folder", "fax01": "Fax server", "vdi-tpl01": "VDI templates", "license-flex01": "Engineering licences",
         "ftp01": "Partner file transfer", "web-old01": "Old public website", "reports-tst01": "Reporting test", "sandbox-bi01": "BI sandbox",
         "edu-lms01": "Training platform"}
OLD = [("old-erp-db01", "Former ERP database", "decommissioned"), ("old-fs01", "Former file server", "decommissioned")]


def system_table() -> list[dict]:
    rows = []
    for name, svc, owner, tier, plat, site in SYSTEMS:
        rows.append(dict(system=name, service=svc, owner=owner, tier=tier, rpo=24, rto=4, platform=plat, site=site, status="active", scope="yes"))
    for name, svc, owner, plat, site in TIER2:
        rows.append(dict(system=name, service=svc, owner=owner, tier="2", rpo=24, rto=24, platform=plat, site=site, status="active", scope="yes"))
    for name, svc in TIER3.items():
        rpo = 168 if name.startswith("dev-") else 72
        rows.append(dict(system=name, service=svc, owner="Infrastructure", tier="3", rpo=rpo, rto=72, platform="VM",
                         site="HQ", status="active", scope="yes"))
    for name, svc, st in OLD:
        rows.append(dict(system=name, service=svc, owner="Infrastructure", tier="2", rpo=24, rto=24, platform="VM", site="HQ", status=st, scope="no"))
    rows.append(dict(system="sap-sandbox01", service="Vendor sandbox", owner="Finance systems", tier="3", rpo=168, rto=168, platform="VM", site="Azure",
                     status="active", scope="no"))
    return rows


def _jobs(rng: random.Random, systems: list[dict]) -> list[list]:
    rows = []
    start = TODAY - timedelta(days=15)
    names = [s["system"] for s in systems if s["system"] not in ("mes-hist01", "qa-lims01", "sap-sandbox01")] + ["test-vm-07", "sap-sandbox01"]
    tiers = {s["system"]: s for s in systems}
    for name in names:
        s = tiers.get(name, dict(tier="3", platform="VM"))
        tool = "Commvault" if s["platform"] in ("SQL Server", "Microsoft 365") else "Veeam"
        size = {"1": 180, "2": 90, "3": 25}[s["tier"]]
        day = start
        while day < TODAY:
            t = datetime.combine(day, datetime.min.time()) + timedelta(hours=22, minutes=rng.randint(0, 50))
            status = "Success" if rng.random() > 0.03 else "Warning"
            if name == "plm-db01" and day >= TODAY - timedelta(days=3):
                status = "Failed"
            if name == "fs-plant02" and day >= TODAY - timedelta(days=2):
                status = "Failed"
            if name == "print01" and day >= TODAY - timedelta(days=5):
                status = "Failed"
            if name == "dev-build01" and day >= TODAY - timedelta(days=3):
                status = "Failed"
            dur = rng.randint(20, 170)
            gb = 0 if status == "Failed" else round(size * rng.uniform(0.05, 0.25), 1)
            job = f"{'SQL' if tool == 'Commvault' and s['platform'] == 'SQL Server' else 'M365' if s['platform'] == 'Microsoft 365' else 'VM'}-{s.get('site', 'HQ')}-T{s['tier']}"
            rows.append([name, tool, job, t.strftime("%Y-%m-%d %H:%M"), (t + timedelta(minutes=dur)).strftime("%Y-%m-%d %H:%M"), status, "Primary", gb])
            if s["tier"] in ("1", "2") and tiers.get(name, {}).get("status") == "active":
                c = datetime.combine(day + timedelta(days=1), datetime.min.time()) + timedelta(hours=4, minutes=rng.randint(0, 40))
                st = "Failed" if name == "crm-db01" and day >= TODAY - timedelta(days=9) else "Failed" if name == "hr-app01" and day >= TODAY - timedelta(days=8) else "Success"
                rows.append([name, tool, f"Copy to DR site T{s['tier']}", c.strftime("%Y-%m-%d %H:%M"), (c + timedelta(minutes=dur // 2)).strftime("%Y-%m-%d %H:%M"),
                             st, "Offsite", gb])
                if s["tier"] == "1" and not (name == "erp-app02" and day >= TODAY - timedelta(days=12)):
                    c2 = c + timedelta(hours=1)
                    rows.append([name, tool, "Hardened repository copy", c2.strftime("%Y-%m-%d %H:%M"), (c2 + timedelta(minutes=dur // 2)).strftime("%Y-%m-%d %H:%M"),
                                 "Success", "Immutable", gb])
            day += timedelta(days=1)
    return rows


def _tests(rng: random.Random, systems: list[dict]) -> list[list]:
    rows = []
    n = 0

    def add(system, d, kind, result, minutes, age, evidence=True, notes=""):
        nonlocal n
        n += 1
        rows.append([f"RT-{n:03d}", system, d.isoformat(), kind, result, minutes, age, f"CHG-{24000 + n * 7}" if evidence else "",
                     rng.choice(["Infra engineer A", "Infra engineer B", "DBA"]), notes])

    no_evidence = {7, 19, 33, 48, 61}
    for s in systems:
        if s["status"] != "active" or s["scope"] != "yes":
            continue
        name, tier = s["system"], s["tier"]
        if name in ("mes-app01", "mes-hist01", "qa-lims01", "jump02", "fax01", "vdi-tpl01"):
            continue
        every = {"1": 80, "2": 150, "3": 330}[tier]
        last = TODAY - timedelta(days=rng.randint(10, every - 5))
        if name == "edi-gw01":
            last = TODAY - timedelta(days=121)
        if name in ("bi-app01", "cad-lic01", "maint-app01", "radius01"):
            last = TODAY - timedelta(days=rng.randint(200, 260))
        dates = [last]
        while dates[-1] > TODAY - timedelta(days=390):
            dates.append(dates[-1] - timedelta(days=every + rng.randint(-10, 10)))
        dates = sorted(d for d in dates if d > TODAY - timedelta(days=390))
        for i, d in enumerate(dates):
            if s["platform"] == "SQL Server":
                kind = "database" if i % 2 == 0 or tier == "1" else "file"
            elif s["platform"] == "Microsoft 365":
                kind = "item"
            elif name.startswith("ad-dc"):
                kind = "AD object"
            else:
                kind = "full VM" if (i % 2 == 0 and tier != "3") else "file"
            minutes = rng.randint(25, 200) if kind not in ("file", "item", "AD object") else rng.randint(5, 30)
            age = round(rng.uniform(6, 20), 1)
            if name == "erp-db01" and d == dates[-1]:
                kind, minutes = "database", 570
            if name == "dw-db01" and d == dates[-1]:
                age = 30.0
            add(name, d, kind, "Pass", minutes, age, evidence=(n + 1) not in no_evidence)
    # placed: payroll restored, but the application could not connect
    add("payroll-db01", TODAY - timedelta(days=20), "database", "Partial", 95, 11.5, notes="database restored; payroll application could not log in (service account missing in the test domain)")
    return rows


def _exercises() -> list[list]:
    return [["Annual DR failover to the plant site", "2025-11-14", "2025-11-14", "Tier 1 systems", "Partial: 2 of 14 tier 1 systems missed the RTO", "DR-2025-report"],
            ["Ransomware recovery tabletop", "2026-04-22", "2026-04-22", "Management team, IT, legal, communications", "Done, 4 actions", "TT-2026-04"],
            ["ERP failover to Azure", "2026-10-15", "", "ERP database and application servers", "", ""],
            ["Annual DR failover to the plant site", "2026-11-20", "", "Tier 1 systems", "", ""]]


def _actions() -> list[list]:
    return [["A-01", "Annual DR failover to the plant site", "Document the MES start-up order after a restore", "Plant systems", "2026-01-31", "Done"],
            ["A-02", "Annual DR failover to the plant site", "Pre-stage ERP application servers at the plant site to meet the RTO", "Finance systems", "2026-06-30", "Open"],
            ["A-03", "Annual DR failover to the plant site", "Add the PLM licence server to the DR plan", "Engineering", "2026-03-31", "Done"],
            ["A-04", "Ransomware recovery tabletop", "Offline copy of the DR runbooks and contact list", "Business continuity lead", "2026-06-30", "Open"],
            ["A-05", "Ransomware recovery tabletop", "Hardened repository for all tier 1 systems", "Infrastructure", "2026-07-31", "Done"],
            ["A-06", "Ransomware recovery tabletop", "Decision tree for paying, restoring or rebuilding, approved by management", "Business continuity lead", "2026-09-30", "Open"],
            ["A-07", "Ransomware recovery tabletop", "Restore test of Active Directory from scratch in an isolated network", "Infrastructure", "2026-12-15", "Open"],
            ["A-08", "Annual DR failover to the plant site", "Bandwidth upgrade between sites for the DR copy jobs", "Infrastructure", "2026-11-30", "Open"]]


SETTINGS = {
    "organisation": "Proseware Industries",
    "as_of": "2026-10-25 08:00",
    "tiers": {"1": {"test_days": 90, "full_test_days": 365, "copies": ["offsite", "immutable"]},
              "2": {"test_days": 180, "full_test_days": 730, "copies": ["offsite"]},
              "3": {"test_days": 365, "full_test_days": 0, "copies": []}},
    "job_window_days": 14,
    "fail_streak": 3,
    "copy_window_days": 7,
    "dr_exercise_days": 365,
    "due_soon_days": 30,
    "owners": {"backup": "Infrastructure team", "tests": "Infrastructure team", "dr": "Business continuity lead", "apps": "Application owners"},
}


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(32)
    systems = system_table()
    _write(folder / "systems.csv", ["System", "Service", "Owner", "Tier", "RPO hours", "RTO hours", "Platform", "Site", "Status", "In scope"],
           [[s["system"], s["service"], s["owner"], s["tier"], s["rpo"], s["rto"], s["platform"], s["site"], s["status"], s["scope"]] for s in systems])
    _write(folder / "backup_jobs.csv", ["System", "Tool", "Job", "Start", "End", "Status", "Copy", "Size GB"], _jobs(rng, systems))
    _write(folder / "restore_tests.csv", ["Test ID", "System", "Date", "Type", "Result", "Duration min", "Data age hours", "Evidence", "Tester", "Notes"],
           _tests(rng, systems))
    _write(folder / "dr_exercises.csv", ["Exercise", "Planned", "Done", "Scope", "Result", "Report"], _exercises())
    _write(folder / "dr_actions.csv", ["Action ID", "Exercise", "Action", "Owner", "Due", "Status"], _actions())
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder
