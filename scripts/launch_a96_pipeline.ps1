$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$rflRoot=Split-Path -Parent $PSScriptRoot
$rflFolder=Join-Path $rflRoot 'experiments\v03r\a96_dense\pipeline'
function Write-RflExclusive($rflPath,$rflValue){
    $rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflValue | ConvertTo-Json -Depth 8 -Compress))
    $rflStream=[IO.File]::Open($rflPath,[IO.FileMode]::CreateNew)
    try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
}
New-Item -ItemType Directory -Path $rflFolder -Force | Out-Null
foreach($rflName in @('launcher_claim.json','pipeline_launch.json','pipeline_claim.json','pipeline.stdout.log','pipeline.stderr.log')){
    if(Test-Path -LiteralPath (Join-Path $rflFolder $rflName)){throw 'One-shot reservation exists; no retry/overwrite'}
}
$rflOther=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*RFL-CausalChase*'})
if($rflOther.Count -ne 0){throw 'Another RFL task is running; do not start duplicate'}
if((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 6291456){throw 'Less than 6GiB free memory'}
Write-RflExclusive (Join-Path $rflFolder 'launcher_claim.json') @{launcher_pid=$PID;start_utc_ticks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks.ToString();observed_at=[DateTime]::UtcNow.ToString('o');automatic_retry=$false;root=$rflRoot}
$rflController=Join-Path $rflRoot 'scripts\run_a96_pipeline.py'
$rflProcess=Start-Process -FilePath 'D:\python\python.exe' -ArgumentList @('-u','-B','-X','utf8',('"'+$rflController+'"')) -WorkingDirectory $rflRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $rflFolder 'pipeline.stdout.log') -RedirectStandardError (Join-Path $rflFolder 'pipeline.stderr.log') -PassThru
$rflLaunch=@{pid=$rflProcess.Id;start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks.ToString();started_at=$rflProcess.StartTime.ToUniversalTime().ToString('o');launcher_pid=$PID;controller=$rflController;controller_sha256=(Get-FileHash -LiteralPath $rflController).Hash.ToLowerInvariant();launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();root=$rflRoot;automatic_retry=$false;research_complete=$false}
Write-RflExclusive (Join-Path $rflFolder 'pipeline_launch.json') $rflLaunch
$rflProcess.WaitForExit()
$rflProcess.Refresh()
if($null -eq $rflProcess.ExitCode){throw 'Native controller exit unavailable; do not fabricate'}
Write-RflExclusive (Join-Path $rflFolder 'pipeline_exit.json') @{role='NATIVE_CONTROLLER_EXIT_ONLY';pid=$rflProcess.Id;start_utc_ticks=$rflLaunch.start_utc_ticks;native_exit_code=$rflProcess.ExitCode;observed_at=[DateTime]::UtcNow.ToString('o');automatic_retry=$false;research_complete=$false}
