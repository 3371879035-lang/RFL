$ErrorActionPreference = 'Stop'
$rflParallelRoot = 'D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflParallelFolder = Join-Path $rflParallelRoot 'experiments\v03r\parallel16_20261008'
$rflLaunchPath = Join-Path $rflParallelFolder 'pipeline_launch.json'
if (Test-Path -LiteralPath $rflLaunchPath) { throw 'Launch is already reserved; no retry.' }
$rflReservationStream = [System.IO.File]::Open((Join-Path $rflParallelFolder 'launcher_claim.json'), [System.IO.FileMode]::CreateNew)
try {
    $rflReservationBytes = [System.Text.UTF8Encoding]::new($false).GetBytes((@{launcher_pid=$PID;observed_at=[DateTime]::UtcNow.ToString('o');no_automatic_retry=$true}|ConvertTo-Json -Compress))
    $rflReservationStream.Write($rflReservationBytes,0,$rflReservationBytes.Length)
} finally { $rflReservationStream.Dispose() }
foreach ($rflLogName in @('pipeline.stdout.log','pipeline.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $rflParallelFolder $rflLogName)) { throw 'Prior logs exist; refuse overwrite.' }
}
$rflArguments = @('-u','-B','-X','utf8',('"'+(Join-Path $rflParallelFolder 'control_parallel16.py')+'"'))
$rflProcess = Start-Process -FilePath 'D:\python\python.exe' -ArgumentList $rflArguments -WorkingDirectory $rflParallelRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflParallelFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflParallelFolder 'pipeline.stderr.log') -PassThru
$rflLaunch = [ordered]@{
    pid=$rflProcess.Id
    start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks
    started_at=$rflProcess.StartTime.ToUniversalTime().ToString('o')
    root=$rflParallelRoot
    controller=(Join-Path $rflParallelFolder 'control_parallel16.py')
    launch_host='Once-only WMI detached PowerShell with real child exit receipt'
    launcher_pid=$PID
    launcher_executable=(Get-Process -Id $PID).Path
    launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    role='P16_PREPARATION_THEN_CONTROLLED_SWITCH'
    research_complete=$false
}
$rflLaunchBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($rflLaunch|ConvertTo-Json -Compress))
$rflLaunchStream = [System.IO.File]::Open($rflLaunchPath,[System.IO.FileMode]::CreateNew)
try { $rflLaunchStream.Write($rflLaunchBytes,0,$rflLaunchBytes.Length) } finally { $rflLaunchStream.Dispose() }
$rflProcess.WaitForExit()
$rflExit = [ordered]@{role='NATIVE_CONTROLLER_EXIT_ONLY';pid=$rflProcess.Id;start_utc_ticks=$rflLaunch.start_utc_ticks;observed_at=[DateTime]::UtcNow.ToString('o');native_exit_code=$rflProcess.ExitCode;scientific_completion_claimed=$false;automatic_retry=$false}
$rflExitBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($rflExit|ConvertTo-Json -Compress))
$rflExitStream = [System.IO.File]::Open((Join-Path $rflParallelFolder 'pipeline_exit.json'),[System.IO.FileMode]::CreateNew)
try { $rflExitStream.Write($rflExitBytes,0,$rflExitBytes.Length) } finally { $rflExitStream.Dispose() }
