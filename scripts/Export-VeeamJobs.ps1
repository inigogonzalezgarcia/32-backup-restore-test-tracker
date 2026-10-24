<#
.SYNOPSIS
    Read-only export of Veeam Backup & Replication job sessions to the backup_jobs.csv used by restoretrack.

.DESCRIPTION
    Writes one row per object (VM, server, database) per session for the last -Days days: system, tool, job, start, end, status, copy
    type and transferred GB. It only reads sessions; it does not start, stop or change jobs.

    Copy type:
      - backup copy jobs (JobType BackupSync or SimpleBackupCopyPolicy) are written as "Offsite";
      - jobs whose name matches -ImmutablePattern are written as "Immutable" (immutability is a repository setting, so name the
        jobs that write to the hardened or object-lock repository, or adjust the pattern);
      - tape jobs are written as "Tape"; everything else as "Primary".

    Other tools: export the job history as CSV (for example the job summary report in Commvault Command Center) with columns close
    to System, Tool, Job, Start, End, Status, Copy and Size GB; restoretrack matches the names loosely (see docs/data-format.md) and
    appending the rows to the same file is fine.

    Run it in a PowerShell session on the backup server, or wherever the Veeam console and its PowerShell module are installed, with
    an account that has the Veeam Backup Viewer role.

.PARAMETER Days
    How many days of sessions to export (default 14).

.PARAMETER ImmutablePattern
    Regular expression for the names of jobs that write to an immutable repository (default 'immutable|hardened').

.EXAMPLE
    .\scripts\Export-VeeamJobs.ps1 -OutputFolder .\data -Days 14 -ImmutablePattern 'hardened|object lock'
#>
[CmdletBinding()]
param(
    [string] $OutputFolder = '.\data',
    [int] $Days = 14,
    [string] $ImmutablePattern = 'immutable|hardened'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Module -ListAvailable -Name Veeam.Backup.PowerShell)) {
    throw 'The Veeam.Backup.PowerShell module was not found: run this where the Veeam console is installed.'
}
Import-Module Veeam.Backup.PowerShell
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$since = (Get-Date).AddDays(-$Days)

function Copy-Type($session) {
    $type = "$($session.JobType)"
    if ($session.JobName -match $ImmutablePattern) { return 'Immutable' }
    if ($type -match 'Tape') { return 'Tape' }
    if ($type -match 'BackupSync|BackupCopy|SimpleBackupCopy') { return 'Offsite' }
    return 'Primary'
}

$rows = foreach ($s in Get-VBRBackupSession | Where-Object { $_.CreationTime -ge $since }) {
    $copy = Copy-Type $s
    foreach ($t in $s.GetTaskSessions()) {
        [pscustomobject]@{
            System    = $t.Name
            Tool      = 'Veeam'
            Job       = $s.JobName
            Start     = $s.CreationTime.ToString('yyyy-MM-dd HH:mm')
            End       = if ($s.EndTime -gt $s.CreationTime) { $s.EndTime.ToString('yyyy-MM-dd HH:mm') } else { '' }
            Status    = "$($t.Status)"
            Copy      = $copy
            'Size GB' = [math]::Round($t.Progress.TransferedSize / 1GB, 1)
        }
    }
}
$rows | Export-Csv -Path (Join-Path $OutputFolder 'backup_jobs.csv') -NoTypeInformation -Encoding UTF8
Write-Host ("{0} rows written to {1}" -f @($rows).Count, (Join-Path $OutputFolder 'backup_jobs.csv'))
Write-Host 'Add systems.csv, restore_tests.csv, dr_exercises.csv, dr_actions.csv and settings.json, then: python -m restoretrack review .\data'
