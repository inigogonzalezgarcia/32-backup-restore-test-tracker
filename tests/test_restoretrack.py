import csv
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from restoretrack import cli
from restoretrack.checks import CRITICAL, INFO, ORDER, WARNING, dr_rows, orphan_jobs, run_all, system_rows
from restoretrack.model import (DRAction, Data, Exercise, JobRun, RestoreTest, Settings, System, copy_of, load, load_jobs, load_systems, load_tests, num,
                                settings_from_dict, tier_of)

AS_OF = datetime(2026, 10, 25, 8, 0)
TODAY = AS_OF.date()


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def nightly(system: str, days: int = 14, status: str = "ok", copy: str = "primary", hour: int = 22) -> list[JobRun]:
    out = []
    for i in range(1, days + 1):
        t = datetime.combine(TODAY - timedelta(days=i), datetime.min.time()) + timedelta(hours=hour)
        out.append(JobRun(system, "Veeam", "job", t, t + timedelta(hours=1), status, copy))
    return out


def data(systems=None, jobs=None, tests=None, **kw) -> Data:
    return Data(kw.pop("settings", Settings()), AS_OF, systems or [System("app01", tier="2", rpo_hours=24, rto_hours=8)], jobs or [], tests or [], **kw)


def row(d: Data, name: str = "app01") -> dict:
    return next(r for r in system_rows(d) if r["system"] == name)


class TestLoading(unittest.TestCase):
    def test_register_with_other_names_tiers_and_semicolons(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "s.csv", ["Servidor", "Aplicación", "Criticidad", "RPO", "RTO", "Estado", "Backup required"],
                      [["erp01", "ERP", "Gold", "4h", "8 h", "Active", "yes"], ["old01", "Old", "Tier 2", "24", "24", "Decommissioned", "no"],
                       ["dev01", "Dev", "Bronze", "", "", "", ""]], delimiter=";")
            ss = load_systems(p)
        self.assertEqual([(s.tier, s.rpo_hours, s.rto_hours, s.status, s.in_scope) for s in ss],
                         [("1", 4.0, 8.0, "active", True), ("2", 24.0, 24.0, "decommissioned", False), ("3", 24.0, 24.0, "active", True)])
        self.assertEqual(tier_of("Platinum"), "1")
        self.assertEqual(num("1,5 h"), 1.5)

    def test_job_log_statuses_and_copy_types(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "j.csv", ["Client", "Product", "Policy", "Creation time", "Result", "Target"],
                      [["erp01", "Commvault", "SQL-T1", "2026-10-24T22:00:00", "Completed with warnings", ""],
                       ["erp01", "Veeam", "Copy to DR site", "2026-10-25 04:00", "Success", ""],
                       ["erp01", "Veeam", "Hardened repository copy", "2026-10-25 05:00", "Failed", ""],
                       ["erp01", "Veeam", "Weekly", "2026-10-25 06:00", "Killed", "LTO tape"]])
            js = load_jobs(p)
        self.assertEqual([(j.status, j.copy) for j in js], [("warning", "primary"), ("ok", "offsite"), ("failed", "immutable"), ("failed", "tape")])
        self.assertEqual(copy_of("S3 object lock"), "immutable")

    def test_test_register(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "t.csv", ["Ref", "Server", "Fecha", "Test type", "Outcome", "Restore minutes", "Ticket"],
                      [["T1", "erp01", "05/10/2026", "Database", "Passed", "95", "CHG-1"], ["T2", "erp01", "2026-10-06", "File", "Failed", "", ""]])
            ts = load_tests(p)
        self.assertEqual([(x.date, x.result, x.full, x.duration_min) for x in ts], [(date(2026, 10, 5), "pass", True, 95.0), (date(2026, 10, 6), "fail", False, None)])

    def test_settings_and_required_register(self):
        s = settings_from_dict({"as_of": "2026-10-25 08:00", "tiers": {"1": {"test_days": 30}}, "owners": {"dr": "BCM"}, "fail_streak": "2"})
        self.assertEqual(s.tier("1"), {"test_days": 30, "full_test_days": 0, "copies": []})
        self.assertEqual((s.owner("dr"), s.owner("backup"), s.fail_streak), ("BCM", "Infrastructure team", 2))
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            load(Path(t))


class TestBackups(unittest.TestCase):
    def test_healthy_and_rpo(self):
        r = row(data(jobs=nightly("app01") + nightly("app01", copy="offsite", hour=4)))
        self.assertEqual((r["hours"], r["streak"], r["missing"]), (9.0, 0, []))
        jobs = nightly("app01", days=3, status="failed") + nightly("app01")[3:] + nightly("app01", copy="offsite", hour=4)
        r = row(data(jobs=jobs))
        self.assertEqual((r["hours"], r["streak"]), (81.0, 3))
        self.assertIn("last good backup 81 h ago (RPO 24 h)", r["issues"])

    def test_required_copies_by_tier(self):
        sy = [System("t1", tier="1"), System("t2", tier="2")]
        jobs = nightly("t1") + nightly("t1", copy="offsite", hour=4) + nightly("t2") + nightly("t2", copy="immutable", hour=4)
        rows = {r["system"]: r for r in system_rows(data(systems=sy, jobs=jobs))}
        self.assertEqual(rows["t1"]["missing"], ["immutable"])
        self.assertEqual(rows["t2"]["missing"], [])           # an immutable copy also counts as offsite
        f = {x.code: x.severity for x in run_all(data(systems=sy, jobs=jobs))}
        self.assertEqual(f["BKP-04"], CRITICAL)

    def test_orphans_and_no_job(self):
        sy = [System("app01", tier="1"), System("old01", status="decommissioned", in_scope=False)]
        jobs = nightly("old01") + nightly("ghost01", days=2)
        self.assertEqual({(r["system"], r["why"]) for r in orphan_jobs(data(systems=sy, jobs=jobs))},
                         {("old01", "decommissioned"), ("ghost01", "not in the register")})
        f = {x.code: x.severity for x in run_all(data(systems=sy, jobs=jobs))}
        self.assertEqual((f["BKP-01"], f["BKP-05"]), (CRITICAL, INFO))


class TestRestoreTests(unittest.TestCase):
    def test_plan_rto_and_full_restores(self):
        s = settings_from_dict({"tiers": {"1": {"test_days": 90, "full_test_days": 365, "copies": []}}})
        sy = [System("db", tier="1", rpo_hours=24, rto_hours=4)]
        tests = [RestoreTest("a", "db", TODAY - timedelta(days=120), "database", "pass", 300, 30, "CHG-1"),
                 RestoreTest("b", "db", TODAY - timedelta(days=100), "file", "pass", 5, 10, "CHG-2")]
        r = row(data(settings=s, systems=sy, jobs=nightly("db"), tests=tests), "db")
        self.assertEqual((r["overdue"], r["rto_tested"], r["rpo_tested"]), (10, 5.0, 10))   # RTO from the full restore, RPO from the last test
        self.assertIn("tested restore took 5 h (RTO 4 h)", r["issues"])
        tests = [RestoreTest("c", "db", TODAY - timedelta(days=30), "file", "pass", 5, 10, "CHG-3")]
        r = row(data(settings=s, systems=sy, jobs=nightly("db"), tests=tests), "db")
        self.assertTrue(r["no_full"])

    def test_failed_last_test_and_evidence(self):
        sy = [System("db", tier="1")]
        tests = [RestoreTest("a", "db", TODAY - timedelta(days=60), "database", "pass", 60, 5, "CHG-1"),
                 RestoreTest("b", "db", TODAY - timedelta(days=10), "database", "partial", 60, 5, "", notes="app did not start")]
        f = {x.code: x for x in run_all(data(systems=sy, jobs=nightly("db"), tests=tests))}
        self.assertEqual(f["TST-02"].severity, CRITICAL)
        self.assertIn("app did not start", f["TST-02"].detail)
        self.assertEqual(f["TST-06"].items, ["b"])
        self.assertEqual(row(data(systems=sy, jobs=nightly("db"), tests=tests), "db")["rag"], "red")

    def test_never_tested(self):
        f = {x.code: x.severity for x in run_all(data(systems=[System("a", tier="1"), System("b", tier="3")], jobs=nightly("a") + nightly("b")))}
        self.assertEqual(f["TST-01"], CRITICAL)


class TestDR(unittest.TestCase):
    def test_exercises_and_actions(self):
        ex = [Exercise("Failover", date(2025, 11, 1), date(2025, 11, 1)), Exercise("ERP to Azure", date(2026, 10, 15), None)]
        act = [DRAction("A1", "Failover", "Fix it", "Infra", date(2026, 6, 30), "open"), DRAction("A2", "Failover", "Done", "Infra", date(2026, 1, 1), "done")]
        d = data(exercises=ex, actions=act)
        dr = dr_rows(d)
        self.assertEqual((dr["age"], dr["stale"], len(dr["missed"]), [a.action_id for a in dr["overdue"]]), (358, False, 1, ["A1"]))
        codes = {x.code: x.severity for x in run_all(d)}
        self.assertEqual((codes["DR-02"], codes["DR-03"]), (WARNING, WARNING))
        self.assertEqual({x.code for x in run_all(data())} & {"DR-01"}, {"DR-01"})


class TestDemo(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS})
            self.assertEqual(hashes[0], hashes[1])
            d = load(Path(t) / "data0")
        f = run_all(d)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        for c in ("BKP-01", "BKP-02", "BKP-03", "BKP-04", "BKP-05", "TST-01", "TST-02", "TST-03", "TST-04", "TST-05", "TST-06", "DR-02", "DR-03"):
            self.assertIn(c, {x.code for x in f})
        self.assertEqual(d.settings.organisation, "Proseware Industries")

    def test_review_reports_a_missing_register(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
