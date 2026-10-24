"""Loading: the system register, the backup job log, the restore test register, DR exercises and their actions, and settings.json,
with forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

SYSTEM_ALIASES = {
    "system": ["system", "name", "server", "host", "workload", "asset", "sistema", "servidor"],
    "service": ["service", "application", "business service", "app", "servicio", "aplicacion"],
    "owner": ["owner", "service owner", "responsable", "app owner"],
    "tier": ["tier", "criticality", "class", "nivel", "criticidad"],
    "rpo_hours": ["rpo hours", "rpo", "rpo h"],
    "rto_hours": ["rto hours", "rto", "rto h"],
    "platform": ["platform", "type", "kind", "plataforma"],
    "site": ["site", "location", "datacenter", "sede"],
    "status": ["status", "state", "estado"],
    "in_scope": ["in scope", "backup required", "protected", "scope"],
}
JOB_ALIASES = {
    "system": ["system", "object", "vm", "client", "server", "workload", "name"],
    "tool": ["tool", "product", "software", "herramienta"],
    "job": ["job", "job name", "policy", "plan", "subclient"],
    "start": ["start", "start time", "started", "creation time", "inicio"],
    "end": ["end", "end time", "finished", "fin"],
    "status": ["status", "result", "state", "estado"],
    "copy": ["copy", "copy type", "target", "tier", "destino"],
    "size_gb": ["size gb", "size", "transferred gb", "data gb"],
}
TEST_ALIASES = {
    "test_id": ["test id", "id", "test", "ref"],
    "system": ["system", "server", "workload", "sistema"],
    "date": ["date", "test date", "fecha"],
    "kind": ["kind", "type", "test type", "scope", "tipo"],
    "result": ["result", "status", "outcome", "resultado"],
    "duration_min": ["duration min", "duration", "restore minutes", "minutes", "rto achieved min"],
    "data_age_hours": ["data age hours", "rpo achieved hours", "restore point age hours", "data age"],
    "evidence": ["evidence", "evidence ref", "ticket", "report", "link", "evidencia"],
    "tester": ["tester", "tested by", "engineer"],
    "notes": ["notes", "issues", "comments", "notas"],
}
EXERCISE_ALIASES = {
    "exercise": ["exercise", "name", "test", "ejercicio"],
    "planned": ["planned", "planned date", "scheduled", "planificado"],
    "done": ["done", "done date", "executed", "completed", "realizado"],
    "scope": ["scope", "systems", "alcance"],
    "result": ["result", "outcome", "resultado"],
    "report": ["report", "evidence", "informe"],
}
ACTION_ALIASES = {
    "action_id": ["action id", "id", "ref"],
    "exercise": ["exercise", "source", "origen"],
    "action": ["action", "description", "accion", "acción"],
    "owner": ["owner", "responsable"],
    "due": ["due", "due date", "fecha"],
    "status": ["status", "state", "estado"],
}
YES = {"yes", "y", "true", "1", "si", "x", "in scope", "required"}
JOB_STATUS = {"success": "ok", "ok": "ok", "succeeded": "ok", "completed": "ok", "warning": "warning", "completed with warnings": "warning",
              "partial": "warning", "failed": "failed", "failure": "failed", "error": "failed", "killed": "failed", "missed": "failed"}
TEST_RESULT = {"pass": "pass", "passed": "pass", "ok": "pass", "success": "pass", "partial": "partial", "fail": "fail", "failed": "fail"}
FULL_KINDS = {"full", "vm", "database", "bare metal", "dr", "instant", "application"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d %b %Y")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip().replace("Z", "")
    if not s or _norm(s) in {"never", "n a", "na", "none", "nunca"}:
        return None
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s[:19] if "T" in s else s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def num(v, default: float | None = 0.0) -> float | None:
    s = str(v or "").strip().replace(" ", "").lower().replace("h", "").replace("min", "")
    if not s:
        return default
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        heads = {_norm(h): h for h in (reader.fieldnames or [])}
        cols = {}
        for key, names in aliases.items():
            for n in [key.replace("_", " ")] + names:
                if _norm(n) in heads:
                    cols[key] = heads[_norm(n)]
                    break
        return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in reader]


def _map(raw: str, table: dict, default: str) -> str:
    n = _norm(raw)
    return table.get(n) or table.get((n.split() or [default])[0], default)


def tier_of(v: str) -> str:
    n = _norm(v)
    words = {"gold": "1", "critical": "1", "platinum": "1", "silver": "2", "important": "2", "high": "1", "medium": "2",
             "bronze": "3", "standard": "3", "low": "3"}
    m = re.search(r"\d", n)
    return m.group(0) if m else words.get(n.split()[0] if n else "", "3")


def copy_of(v: str) -> str:
    n = _norm(v)
    if any(k in n for k in ("immutable", "hardened", "worm", "object lock", "air gap", "airgap", "vault")):
        return "immutable"
    if any(k in n for k in ("tape", "cinta")):
        return "tape"
    if any(k in n for k in ("offsite", "off site", "copy", "secondary", "cloud", "dr site", "replica")):
        return "offsite"
    return "primary"


@dataclass
class System:
    system: str
    service: str = ""
    owner: str = ""
    tier: str = "3"
    rpo_hours: float = 24.0
    rto_hours: float = 24.0
    platform: str = ""
    site: str = ""
    status: str = "active"            # active | decommissioned
    in_scope: bool = True


@dataclass
class JobRun:
    system: str
    tool: str
    job: str
    start: datetime
    end: datetime | None
    status: str                       # ok | warning | failed
    copy: str = "primary"             # primary | offsite | immutable | tape
    size_gb: float = 0.0


@dataclass
class RestoreTest:
    test_id: str
    system: str
    date: date
    kind: str = "file"
    result: str = "pass"              # pass | partial | fail
    duration_min: float | None = None
    data_age_hours: float | None = None
    evidence: str = ""
    tester: str = ""
    notes: str = ""

    @property
    def full(self) -> bool:
        return _norm(self.kind) in FULL_KINDS or any(k in _norm(self.kind) for k in ("full", "database", "bare metal", "dr", "failover"))


@dataclass
class Exercise:
    exercise: str
    planned: date | None = None
    done: date | None = None
    scope: str = ""
    result: str = ""
    report: str = ""


@dataclass
class DRAction:
    action_id: str
    exercise: str
    action: str
    owner: str = ""
    due: date | None = None
    status: str = "open"              # open | done


@dataclass
class Settings:
    organisation: str = "Organisation"
    as_of: datetime | None = None
    tiers: dict = field(default_factory=lambda: {
        "1": {"test_days": 90, "full_test_days": 365, "copies": ["offsite", "immutable"]},
        "2": {"test_days": 180, "full_test_days": 730, "copies": ["offsite"]},
        "3": {"test_days": 365, "full_test_days": 0, "copies": []}})
    job_window_days: int = 14
    fail_streak: int = 3
    copy_window_days: int = 7
    dr_exercise_days: int = 365
    due_soon_days: int = 30
    owners: dict = field(default_factory=lambda: {"backup": "Infrastructure team", "tests": "Infrastructure team", "dr": "Business continuity lead",
                                                  "apps": "Application owners"})

    def tier(self, t: str) -> dict:
        return self.tiers.get(str(t)) or self.tiers.get("3") or {"test_days": 365, "full_test_days": 0, "copies": []}

    def owner(self, key: str) -> str:
        return self.owners.get(key, "")


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k):
            continue
        cur = getattr(s, k)
        if k == "as_of":
            v = parse_dt(v)
        elif k == "tiers":
            v = {str(t): {**{"test_days": 365, "full_test_days": 0, "copies": []}, **cfg} for t, cfg in v.items()}
        elif k == "owners":
            v = {**cur, **v}
        elif isinstance(cur, int):
            v = int(v)
        setattr(s, k, v)
    return s


def load_systems(path: Path) -> list[System]:
    out = []
    for r in _rows(path, SYSTEM_ALIASES):
        if not r.get("system"):
            continue
        st = _norm(r.get("status", ""))
        status = "decommissioned" if st.startswith(("decom", "retired", "baja", "removed", "off")) else "active"
        scope = r.get("in_scope", "")
        out.append(System(r["system"], r.get("service", ""), r.get("owner", ""), tier_of(r.get("tier", "")), num(r.get("rpo_hours"), 24.0),
                          num(r.get("rto_hours"), 24.0), r.get("platform", ""), r.get("site", ""), status, True if not scope else _norm(scope) in YES))
    return out


def load_jobs(path: Path) -> list[JobRun]:
    out = []
    for r in _rows(path, JOB_ALIASES):
        t = parse_dt(r.get("start"))
        if not r.get("system") or not t:
            continue
        out.append(JobRun(r["system"], r.get("tool", ""), r.get("job", ""), t, parse_dt(r.get("end")), _map(r.get("status", ""), JOB_STATUS, "failed"),
                          copy_of(r.get("copy", "") or r.get("job", "")), num(r.get("size_gb"))))
    return out


def load_tests(path: Path) -> list[RestoreTest]:
    out = []
    for r in _rows(path, TEST_ALIASES):
        dt = parse_date(r.get("date"))
        if not r.get("system") or not dt:
            continue
        out.append(RestoreTest(r.get("test_id") or f"T{len(out) + 1}", r["system"], dt, r.get("kind") or "file",
                               _map(r.get("result", ""), TEST_RESULT, "fail"), num(r.get("duration_min"), None), num(r.get("data_age_hours"), None),
                               r.get("evidence", ""), r.get("tester", ""), r.get("notes", "")))
    return out


def load_exercises(path: Path) -> list[Exercise]:
    return [Exercise(r["exercise"], parse_date(r.get("planned")), parse_date(r.get("done")), r.get("scope", ""), r.get("result", ""), r.get("report", ""))
            for r in _rows(path, EXERCISE_ALIASES) if r.get("exercise")]


def load_actions(path: Path) -> list[DRAction]:
    out = []
    for r in _rows(path, ACTION_ALIASES):
        if not r.get("action"):
            continue
        st = _norm(r.get("status", "open"))
        out.append(DRAction(r.get("action_id") or f"A{len(out) + 1}", r.get("exercise", ""), r["action"], r.get("owner", ""), parse_date(r.get("due")),
                            "done" if st.startswith(("done", "closed", "complete", "cerr", "hech")) else "open"))
    return out


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    systems: list[System]
    jobs: list[JobRun] = field(default_factory=list)
    tests: list[RestoreTest] = field(default_factory=list)
    exercises: list[Exercise] = field(default_factory=list)
    actions: list[DRAction] = field(default_factory=list)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def system(self, name: str) -> System | None:
        key = name.lower()
        return next((s for s in self.systems if s.system.lower() == key), None)


def load(folder: Path, as_of: datetime | date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "systems.csv").exists():
        raise FileNotFoundError(f"{folder / 'systems.csv'} not found: the system register is required")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    systems = load_systems(folder / "systems.csv")
    if not systems:
        raise ValueError("systems.csv has no rows with a system name")
    opt = lambda name, fn: fn(folder / name) if (folder / name).exists() else []  # noqa: E731
    jobs, tests, ex, act = opt("backup_jobs.csv", load_jobs), opt("restore_tests.csv", load_tests), opt("dr_exercises.csv", load_exercises), \
        opt("dr_actions.csv", load_actions)
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(hours=8)
    when = as_of or s.as_of or (max(j.start for j in jobs) if jobs else datetime.now().replace(microsecond=0))
    return Data(s, when, systems, jobs, tests, ex, act)
