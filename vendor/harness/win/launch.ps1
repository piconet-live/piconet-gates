# launch.ps1 -Runner EXE -RunDir DIR [-Env "K=V;K=V"] [-ArgList "a|b|c"] [-MaxSeconds N]
# Starts the runner minimised with its own environment, working folder and output files, and records its
# process ID in <RunDir>\pid.txt. "{run}" in an environment value stands for RunDir.
# Lifted from the first project's launch.ps1; the game, user folder and module now arrive in -ArgList.
# Time limit: no process started here outlives -MaxSeconds (default 180), counted from its start, whatever its
# caller does or fails to do. A detached watchdog (time-limit.ps1, beside this file) ends the runner and every
# process the runner started (a launcher's game) at the limit, each by its process ID and only while that ID still
# names the same process (its start time), and writes "stopped by its time limit after N s" to <RunDir>\limit.txt.
# A process the runner started that is still up when the runner has ended by itself is ended too (a game must not
# outlive its launcher). When they have all ended by themselves the watchdog ends with them and writes no limit.txt.
# Its own process ID is in <RunDir>\time-limit-pid.txt, its log in <RunDir>\time-limit.txt.
param([string]$Runner, [string]$RunDir, [string]$Env = "", [string]$ArgList = "", [int]$MaxSeconds = 180)
if ($MaxSeconds -lt 1) { Write-Error "launch.ps1: -MaxSeconds must be 1 or more"; exit 2 }
New-Item -ItemType Directory -Force -Path "$RunDir\auto" | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue "$RunDir\limit.txt", "$RunDir\time-limit.txt", "$RunDir\time-limit-pid.txt"
foreach ($kv in ($Env -split ';')) { if ($kv) { $k, $v = $kv -split '=', 2; [Environment]::SetEnvironmentVariable($k, $v.Replace('{run}', $RunDir)) } }
$list = @(); foreach ($a in ($ArgList -split '\|')) { if ($a) { $list += $a } }
$p = Start-Process -FilePath $Runner -ArgumentList $list -WorkingDirectory $RunDir -RedirectStandardOutput "$RunDir\stdout.txt" -RedirectStandardError "$RunDir\stderr.txt" -PassThru -WindowStyle Minimized
$p.Id | Out-File -Encoding ascii "$RunDir\pid.txt"
# The watchdog is started without redirection (no handle of this shell is inherited, so it holds no caller waiting)
# and hidden; it is told the runner's start time, which tells the runner from a later process given the same ID.
# A runner that cannot be given its watchdog does not run on: it is ended here, and the caller finds it gone.
try {
    $started = $p.StartTime.ToFileTimeUtc()
    $dog = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ErrorAction Stop -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\time-limit.ps1`"",
        "-Id", $p.Id, "-Started", $started, "-MaxSeconds", $MaxSeconds, "-RunDir", "`"$RunDir`"")
    $dog.Id | Out-File -Encoding ascii "$RunDir\time-limit-pid.txt"
} catch {
    "no time limit could be set ($_): the runner was ended at once" | Out-File -Encoding ascii "$RunDir\limit.txt"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
Write-Output $p.Id
