$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$rflVerifyRoot='D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflVerifyFolder=Join-Path $rflVerifyRoot 'experiments\v03r\parallel_verify_20261008'
function Write-RflExclusive($rflPath,$rflValue){
    $rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflValue|ConvertTo-Json -Depth 6 -Compress))
    $rflStream=[IO.File]::Open($rflPath,[IO.FileMode]::CreateNew)
    try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
}
if(Test-Path -LiteralPath (Join-Path $rflVerifyFolder 'pipeline_launch.json')){throw 'Launch already reserved'}
Write-RflExclusive (Join-Path $rflVerifyFolder 'launcher_claim.json') @{launcher_pid=$PID;observed_at=[DateTime]::UtcNow.ToString('o');role='EXPLICIT_USER_AUTHORIZED_VERIFICATION_ACCELERATION';automatic_retry=$false}
foreach($rflName in @('pipeline.stdout.log','pipeline.stderr.log')){if(Test-Path -LiteralPath (Join-Path $rflVerifyFolder $rflName)){throw 'Logs exist; no overwrite'}}
$rflProcess=Start-Process -FilePath 'D:\python\python.exe' -ArgumentList @('-u','-B','-X','utf8',('"'+(Join-Path $rflVerifyFolder 'continue_verified.py')+'"')) -WorkingDirectory $rflVerifyRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflVerifyFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflVerifyFolder 'pipeline.stderr.log') -PassThru
$rflLaunch=@{pid=$rflProcess.Id;started_at=$rflProcess.StartTime.ToUniversalTime().ToString('o');start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks;launcher_pid=$PID;controller=(Join-Path $rflVerifyFolder 'continue_verified.py');launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();root=$rflVerifyRoot;automatic_retry=$false;research_complete=$false}
Write-RflExclusive (Join-Path $rflVerifyFolder 'pipeline_launch.json') $rflLaunch
$rflProcess.WaitForExit()
Write-RflExclusive (Join-Path $rflVerifyFolder 'pipeline_exit.json') @{role='NATIVE_CONTROLLER_EXIT_ONLY';pid=$rflProcess.Id;start_utc_ticks=$rflLaunch.start_utc_ticks;native_exit_code=$rflProcess.ExitCode;observed_at=[DateTime]::UtcNow.ToString('o');automatic_retry=$false;scientific_completion_claimed=$false}
