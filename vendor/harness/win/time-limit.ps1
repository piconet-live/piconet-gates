# time-limit.ps1 -Id PID -Started FILETIME -MaxSeconds N -RunDir DIR: launch.ps1's watchdog, started by it, detached.
# Watches the runner launch.ps1 started (its process ID and start time, as a UTC file time) and every process the
# runner starts (looked for every 3 s: a process whose parent is one of these, started after that parent).
#  - At N seconds after the runner's start it ends every one of them still up, the runner's children first, and
#    writes "stopped by its time limit after N s" to DIR\limit.txt.
#  - When the runner has ended by itself, a process it started that is still up 10 s later is ended (a launcher's
#    game never outlives its launcher); that is said in DIR\time-limit.txt, and no limit.txt is written.
#  - When all of them have ended, it ends too.
# A process is ended only by its ID, and only while that ID still has the start time seen at first: an ID that
# Windows gave to another process meanwhile is never hit. Its log: DIR\time-limit.txt.
param([int]$Id, [long]$Started, [int]$MaxSeconds, [string]$RunDir)
$log = "$RunDir\time-limit.txt"
function Say([string]$text) { "$(Get-Date -Format 'HH:mm:ss') $text" | Out-File -Append -Encoding ascii $log }
function StartOf([int]$procId) {
    try { (Get-Process -Id $procId -ErrorAction Stop).StartTime.ToFileTimeUtc() } catch { $null }
}
function Same($entry) { (StartOf $entry.Id) -eq $entry.Started }
function NameOf([int]$procId) { try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" } }

$tree = New-Object System.Collections.ArrayList
[void]$tree.Add([pscustomobject]@{ Id = $Id; Started = $Started; Name = (NameOf $Id) })
$deadline = [DateTime]::FromFileTimeUtc($Started).AddSeconds($MaxSeconds)
Say "watching $Id ($($tree[0].Name)) and what it starts: at most $MaxSeconds s, until $($deadline.ToLocalTime().ToString('HH:mm:ss'))"

function Discover {
    # the children of every process watched and still the same, and theirs (a launcher's game, its helpers)
    $added = $true
    while ($added) {
        $added = $false
        foreach ($parent in @($tree)) {
            if (-not (Same $parent)) { continue }
            $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($parent.Id)" -ErrorAction SilentlyContinue
            foreach ($k in @($kids)) {
                if (-not $k) { continue }
                $kid = [int]$k.ProcessId
                if (@($tree | Where-Object { $_.Id -eq $kid }).Count -gt 0) { continue }
                # a process of an older holder of the parent's ID was started before the parent: not ours
                $s = StartOf $kid
                if (-not $s -or $s -lt $parent.Started) { continue }
                [void]$tree.Add([pscustomobject]@{ Id = $kid; Started = $s; Name = $k.Name })
                Say "  $kid ($($k.Name)), started by $($parent.Id)"
                $added = $true
            }
        }
    }
}

function EndAll([string]$why) {
    $ended = @()
    for ($i = $tree.Count - 1; $i -ge 0; $i--) {          # the latest found first: children before their parents
        $e = $tree[$i]
        if (Same $e) { Stop-Process -Id $e.Id -Force -ErrorAction SilentlyContinue; $ended += "$($e.Id) ($($e.Name))" }
    }
    Say "$why; ended $($ended -join ', ')"
    return $ended
}

$rootGone = $null; $nextLook = [DateTime]::MinValue
while ($true) {
    $now = [DateTime]::UtcNow
    $alive = @($tree | Where-Object { Same $_ })
    if ($alive.Count -eq 0) { Say "all ended by themselves; the watch ends"; exit 0 }
    if ($now -ge $deadline) {
        $ended = EndAll "the time limit of $MaxSeconds s"
        @("stopped by its time limit after $MaxSeconds s", "ended: $($ended -join ', ')") |
            Out-File -Encoding ascii "$RunDir\limit.txt"
        exit 0
    }
    if (-not (Same $tree[0])) {
        if (-not $rootGone) { $rootGone = $now; Say "the runner $Id ended by itself; $($alive.Count) process(es) it started still up" }
        elseif (($now - $rootGone).TotalSeconds -ge 10) { [void](EndAll "left behind 10 s after the runner ended"); exit 0 }
    } elseif ($now -ge $nextLook) {
        Discover; $nextLook = [DateTime]::UtcNow.AddSeconds(3)
    }
    Start-Sleep -Milliseconds 500
}
