$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$rflResumeRoot = 'D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflResumeFolder = Join-Path $rflResumeRoot 'experiments\v03r\parallel16_resume_20261008'
$rflLaunchPath = Join-Path $rflResumeFolder 'pipeline_launch.json'
if (Test-Path -LiteralPath $rflLaunchPath) { throw 'Launch is already reserved; no retry.' }
function Write-RflExclusiveJson($rflPath, $rflData) {
    $rflBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($rflData | ConvertTo-Json -Depth 6 -Compress))
    $rflStream = [System.IO.File]::Open($rflPath, [System.IO.FileMode]::CreateNew)
    try { $rflStream.Write($rflBytes, 0, $rflBytes.Length) } finally { $rflStream.Dispose() }
}
Write-RflExclusiveJson (Join-Path $rflResumeFolder 'launcher_claim.json') @{launcher_pid=$PID;observed_at=[DateTime]::UtcNow.ToString('o');no_automatic_retry=$true;role='USER_EXPLICITLY_AUTHORIZED_NEW_RESERVATION'}
foreach ($rflLogName in @('pipeline.stdout.log','pipeline.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $rflResumeFolder $rflLogName)) { throw 'Prior logs exist; refuse overwrite.' }
}
$rflArguments = @('-u','-B','-X','utf8',('"'+(Join-Path $rflResumeFolder 'resume_parallel16.py')+'"'))
$rflProcess = Start-Process -FilePath 'D:\python\python.exe' -ArgumentList $rflArguments -WorkingDirectory $rflResumeRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflResumeFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflResumeFolder 'pipeline.stderr.log') -PassThru
$rflLaunch = [ordered]@{pid=$rflProcess.Id;start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks;started_at=$rflProcess.StartTime.ToUniversalTime().ToString('o');root=$rflResumeRoot;controller=(Join-Path $rflResumeFolder 'resume_parallel16.py');launcher_pid=$PID;launcher_executable=(Get-Process -Id $PID).Path;launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();launch_host='Once-only WMI detached launcher with explicit UTF-8 and real exit receipt';role='AUTHORIZED_P16_RESUME_ALREADY_STOPPED_PARENT';research_complete=$false}
Write-RflExclusiveJson $rflLaunchPath $rflLaunch
$rflProcess.WaitForExit()
Write-RflExclusiveJson (Join-Path $rflResumeFolder 'pipeline_exit.json') @{role='NATIVE_CONTROLLER_EXIT_ONLY';pid=$rflProcess.Id;start_utc_ticks=$rflLaunch.start_utc_ticks;observed_at=[DateTime]::UtcNow.ToString('o');native_exit_code=$rflProcess.ExitCode;scientific_completion_claimed=$false;automatic_retry=$false}
