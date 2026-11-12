$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$rflRoot='D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflFolder=Join-Path $rflRoot 'experiments\v03r\f1_parallel_verify_20261008'
function Write-RflExclusive($rflPath,$rflValue){
    $rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflValue | ConvertTo-Json -Depth 6 -Compress))
    $rflStream=[IO.File]::Open($rflPath,[IO.FileMode]::CreateNew)
    try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
}
foreach($rflName in @('launcher_claim.json','pipeline_launch.json','control_claim.json','pipeline.stdout.log','pipeline.stderr.log')){
    if(Test-Path -LiteralPath (Join-Path $rflFolder $rflName)){throw 'One-shot launch already reserved; no overwrite/retry'}
}
$rflLive=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*RFL-CausalChase*'})
if(@($rflLive | Where-Object {$_.ProcessId -notin @(14804,37880)}).Count -ne 0){throw 'Unregistered existing RFL Python task'}
if((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 6291456){throw 'Less than 6GiB free memory'}
& (Join-Path $rflFolder 'handover.ps1') -CheckOnly
if($LASTEXITCODE -ne 0){throw 'Parent authentication preflight failed'}
Write-RflExclusive (Join-Path $rflFolder 'launcher_claim.json') @{launcher_pid=$PID;observed_at=[DateTime]::UtcNow.ToString('o');role='EXPLICIT_PARALLEL_F1_VALIDATION_ONLY';automatic_retry=$false}
$rflProcess=Start-Process -FilePath 'D:\python\python.exe' -ArgumentList @('-u','-B','-X','utf8',('"'+(Join-Path $rflFolder 'control_f1_parallel.py')+'"')) -WorkingDirectory $rflRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflFolder 'pipeline.stderr.log') -PassThru
$rflLaunch=@{pid=$rflProcess.Id;started_at=$rflProcess.StartTime.ToUniversalTime().ToString('o');start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks.ToString();launcher_pid=$PID;controller=(Join-Path $rflFolder 'control_f1_parallel.py');controller_sha256=(Get-FileHash -LiteralPath (Join-Path $rflFolder 'control_f1_parallel.py')).Hash.ToLowerInvariant();launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();root=$rflRoot;automatic_retry=$false;research_complete=$false}
Write-RflExclusive (Join-Path $rflFolder 'pipeline_launch.json') $rflLaunch
$rflProcess.WaitForExit()
Write-RflExclusive (Join-Path $rflFolder 'pipeline_exit.json') @{role='NATIVE_CONTROLLER_EXIT_ONLY';pid=$rflProcess.Id;start_utc_ticks=$rflLaunch.start_utc_ticks;native_exit_code=$rflProcess.ExitCode;observed_at=[DateTime]::UtcNow.ToString('o');automatic_retry=$false;research_complete=$false}
