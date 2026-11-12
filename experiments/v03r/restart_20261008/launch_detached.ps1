$ErrorActionPreference = 'Stop'
$rflRestartRoot = 'D:\强化反馈学习\RFL-CausalChase-v0.3-restart-20261008'
$rflRestartFolder = Join-Path $rflRestartRoot 'experiments\v03r\restart_20261008'
$rflLaunchPath = Join-Path $rflRestartFolder 'pipeline_launch.json'
if (Test-Path -LiteralPath $rflLaunchPath) { throw 'Launch is already reserved; no automatic retry.' }
$rflReservation = Join-Path $rflRestartFolder 'launcher_claim.json'
$rflReservationStream = [System.IO.File]::Open($rflReservation, [System.IO.FileMode]::CreateNew)
try {
    $rflReservationBytes = [System.Text.UTF8Encoding]::new($false).GetBytes((@{launcher_pid=$PID; observed_at=[DateTime]::UtcNow.ToString('o'); no_automatic_retry=$true} | ConvertTo-Json -Compress))
    $rflReservationStream.Write($rflReservationBytes, 0, $rflReservationBytes.Length)
} finally { $rflReservationStream.Dispose() }
foreach ($rflLogName in @('pipeline.stdout.log', 'pipeline.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $rflRestartFolder $rflLogName)) { throw 'Prior launch logs exist; refusing overwrite.' }
}
Set-Location -LiteralPath $rflRestartRoot
$rflArguments = @('-u', '-B', '-X', 'utf8', ('"' + (Join-Path $rflRestartFolder 'continue_pipeline.py') + '"'))
$rflProcess = Start-Process -FilePath 'D:\python\python.exe' -ArgumentList $rflArguments -WorkingDirectory $rflRestartRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflRestartFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflRestartFolder 'pipeline.stderr.log') -PassThru
$rflLaunch = [ordered]@{
    pid = $rflProcess.Id
    start_utc_ticks = $rflProcess.StartTime.ToUniversalTime().Ticks
    started_at = $rflProcess.StartTime.ToUniversalTime().ToString('o')
    root = $rflRestartRoot
    controller = (Join-Path $rflRestartFolder 'continue_pipeline.py')
    launch_host = 'WMI-created detached PowerShell, not the interactive Codex shell process tree'
    launcher_pid = $PID
    launcher_executable = (Get-Process -Id $PID).Path
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    role = 'ONE_SHOT_PROSPECTIVE_INTERRUPTION_RESTART_R1'
    research_complete = $false
}
$rflLaunchBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($rflLaunch | ConvertTo-Json -Compress))
$rflLaunchStream = [System.IO.File]::Open($rflLaunchPath, [System.IO.FileMode]::CreateNew)
try { $rflLaunchStream.Write($rflLaunchBytes, 0, $rflLaunchBytes.Length) } finally { $rflLaunchStream.Dispose() }

# Retain the detached launcher until its child exits; capture the real native exit.
# This is not proof that scientific stages succeeded and never starts a retry.
$rflProcess.WaitForExit()
$rflExitReceipt = [ordered]@{
    role = 'NATIVE_CONTROLLER_EXIT_ONLY'
    pid = $rflProcess.Id
    start_utc_ticks = $rflLaunch.start_utc_ticks
    observed_at = [DateTime]::UtcNow.ToString('o')
    native_exit_code = $rflProcess.ExitCode
    scientific_completion_claimed = $false
    automatic_retry = $false
}
$rflExitBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($rflExitReceipt | ConvertTo-Json -Compress))
$rflExitStream = [System.IO.File]::Open((Join-Path $rflRestartFolder 'pipeline_exit.json'), [System.IO.FileMode]::CreateNew)
try { $rflExitStream.Write($rflExitBytes, 0, $rflExitBytes.Length) } finally { $rflExitStream.Dispose() }
