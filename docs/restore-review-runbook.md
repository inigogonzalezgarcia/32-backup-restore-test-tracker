# Monthly backup and restore review runbook

A 30-minute monthly review with the infrastructure team, the business continuity lead and, for the systems in red, their application owners. The tool only reads exports; jobs, tests and exercises are changed in the backup tools and through the change process.

## Before the meeting (20 minutes)

1. Export the job sessions (read-only):
   ```powershell
   .\scripts\Export-VeeamJobs.ps1 -OutputFolder .\data -Days 14
   ```
   Append the job report of any other backup tool to the same `backup_jobs.csv`.
2. Copy the current `systems.csv` (the register with tiers, RPO and RTO), `restore_tests.csv`, `dr_exercises.csv` and `dr_actions.csv`.
3. Build the outputs and send `restore-review.md` as the agenda:
   ```bash
   python -m restoretrack review data/ --title "Backup and restore review · November"
   ```

## Agenda

| Minutes | Topic | Output |
|---|---|---|
| 5 | Fix first: systems with no backup, tier 1 outside the RPO or without an immutable copy, tier 1 never tested or with a failed test | `report.html` → Fix first |
| 10 | Backups: the rest of the RPO breaches, failing streaks, missing copies, jobs to remove | `failing-backups.csv` |
| 10 | Restore tests: overdue, slower than the RTO, only file-level; book next month's tests | `tests-due.csv` (booked/done columns) |
| 5 | DR: next exercise, missed dates, actions past due | `dr-actions.csv` |

## How to read it

- **The RPO check uses the last good backup, not the schedule.** A job scheduled every night that failed three nights in a row is three days outside a 24-hour RPO.
- **A copy counts only if it ran.** A copy job that exists but failed for a week leaves the system with one copy, in one place.
- **Only a full restore says anything about the RTO.** Restoring a file proves the backup is readable; restoring the VM, the database or the service proves the system comes back, and how long that takes.
- **A partial test is a failed test** until it is repeated: "the database came back but the application could not log in" is exactly what a real recovery would hit.
- **Evidence is part of the test.** For an ISO 22301 or ISO 27001 audit, `evidence-pack.csv` lists the last successful test of every tier 1 and 2 system with its reference.

## After the meeting

- Book the tests from `tests-due.csv` in the next change windows and fill in the booked column.
- Raise changes for the job fixes and copy jobs.
- Keep each month's output folder; the next review starts with last month's red systems.
