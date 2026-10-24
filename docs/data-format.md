# Data format

Put the files in one folder and run `python -m restoretrack review <folder>`. Only `systems.csv` is required; every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below are accepted.

## systems.csv (required)

The register of systems that should be backed up, with the targets agreed with their owners.

| Column | Also accepted | Notes |
|---|---|---|
| System | name, server, host, workload, servidor | Must match the object name in the backup jobs and the restore tests (case is ignored) |
| Service | application, aplicacion | What the business calls it |
| Owner | service owner, responsable | |
| Tier | criticality, class, criticidad | `1`, `2`, `3`; also Gold/Silver/Bronze, Critical/Important/Standard |
| RPO hours, RTO hours | RPO, RTO | `4`, `4h`, `4 h` |
| Platform, Site | type, location | Shown in the report |
| Status | estado | `active` or `decommissioned` (retired, baja) |
| In scope | backup required, protected | `yes`/`no`; empty means yes |

## backup_jobs.csv

One row per object per job run, for at least `job_window_days` (14 by default). `scripts/Export-VeeamJobs.ps1` writes it from Veeam; other tools' job reports work with columns close to these.

| Column | Also accepted | Notes |
|---|---|---|
| System | object, vm, client, server | |
| Tool, Job | product, policy, plan, subclient | |
| Start, End | start time, creation time, end time | `YYYY-MM-DD HH:MM` or ISO |
| Status | result | success / warning / failed (completed with warnings, killed, missed also accepted) |
| Copy | copy type, target | primary, offsite (copy, secondary, cloud, DR site), immutable (hardened, object lock, WORM, air gap), tape. If empty, the job name is used |
| Size GB | size, transferred GB | |

## restore_tests.csv

The register of restore tests, one row per test.

| Column | Also accepted | Notes |
|---|---|---|
| Test ID | id, ref | |
| System, Date | server, test date, fecha | |
| Type | test type, scope | file, item, AD object, full VM, database, bare metal, DR. Full VM, database, bare metal and DR count as full restores |
| Result | status, outcome | pass / partial / fail |
| Duration min | restore minutes | Time to bring the system back; compared with the RTO (full restores only) |
| Data age hours | restore point age hours | Age of the restored data; compared with the RPO |
| Evidence | ticket, report, link | Reference an auditor can follow |
| Tester, Notes | tested by, issues | Notes of a failed test are shown in the finding |

## dr_exercises.csv and dr_actions.csv

`dr_exercises.csv`: `Exercise`, `Planned`, `Done`, `Scope`, `Result`, `Report`. `dr_actions.csv`: `Action ID`, `Exercise`, `Action`, `Owner`, `Due`, `Status` (open/done).

## settings.json

All keys are optional; the demo's file in `sample_data/` shows every key.

| Key | Default | Meaning |
|---|---|---|
| `organisation`, `as_of` | | Title and review time (`YYYY-MM-DD HH:MM`) |
| `tiers` | 1: 90 days, full every 365, offsite + immutable · 2: 180, full every 730, offsite · 3: 365, none | Per tier: `test_days` between successful tests, `full_test_days` between full restores (0 = not required), required `copies` |
| `job_window_days`, `fail_streak`, `copy_window_days` | 14, 3, 7 | Job log window, failed runs in a row before a warning, window for the required copies |
| `dr_exercise_days`, `due_soon_days` | 365, 30 | Maximum time without a DR exercise; horizon for "tests due" |
| `owners` | | Owner per area: backup, tests, dr, apps |
