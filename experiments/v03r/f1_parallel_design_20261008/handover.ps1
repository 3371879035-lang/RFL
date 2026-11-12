param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$rflRoot='D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflFolder=Join-Path $rflRoot 'experiments\v03r\f1_parallel_design_20261008'
$rflParent=Join-Path $rflRoot 'experiments\v03r\f1_parallel_verify_20261008'
$rflReg=Get-Content -LiteralPath (Join-Path $rflFolder 'preregistration.json') -Raw | ConvertFrom-Json
function Assert-RflIdentity($rflId,$rflTicks,$rflCommand){
    $rflRow=Get-CimInstance Win32_Process -Filter "ProcessId=$rflId"
    if(-not $rflRow -or $rflRow.CommandLine -cne $rflCommand){throw 'Process full CommandLine -cne registered command'}
    $rflProcess=Get-Process -Id $rflId -ErrorAction Stop
    if($rflProcess.StartTime.ToUniversalTime().Ticks -ne [long]$rflTicks){throw 'Actual start ticks differ'}
    return $rflProcess
}
function Assert-RflStillUnfinished {
    foreach($rflName in @('design_lock.receipt.json','pipeline_result.json','pipeline_exit.json','pipeline_failure.json','f1_execution.json')){
        if(Test-Path -LiteralPath (Join-Path $rflParent $rflName)){throw 'Full F1 has already completed/exited; abort switch, respect existing result'}
    }
    if(Test-Path -LiteralPath (Join-Path $rflRoot 'experiments\v03r\dev_lock.json')){throw 'Published design lock exists; no duplicate analysis'}
    $rflLines=Get-Content -LiteralPath (Join-Path $rflParent 'pipeline.stdout.log')
    if($rflLines[-1] -notlike 'START design_lock *'){throw 'Parent is not waiting in registered full analysis'}
}
$rflParentCommand='"D:\python\python.exe" -u -B -X utf8 "'+(Join-Path $rflParent 'control_f1_parallel.py')+'"'
$rflAnalysisCommand='D:\python\python.exe -u -B -X utf8 '+(Join-Path $rflParent 'parallel_f1.py')
$rflParentProcess=Assert-RflIdentity $rflReg.parent_pid $rflReg.parent_start_utc_ticks $rflParentCommand
$rflAnalysisProcess=Assert-RflIdentity $rflReg.analysis_pid $rflReg.analysis_start_utc_ticks $rflAnalysisCommand
$rflAnalysisRow=Get-CimInstance Win32_Process -Filter "ProcessId=$($rflReg.analysis_pid)"
if($rflAnalysisRow.ParentProcessId -ne $rflReg.parent_pid){throw 'Analysis parent-child identity mismatch'}
$rflChildren=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.ParentProcessId -eq $rflReg.parent_pid})
if($rflChildren.Count -ne 1 -or $rflChildren[0].ProcessId -ne $rflReg.analysis_pid){throw 'Other Python child under old controller'}
Assert-RflStillUnfinished
if((Get-FileHash -LiteralPath (Join-Path $rflParent 'parallel_f1.py')).Hash.ToLowerInvariant() -cne 'aecc5b3abcaae3ce61e00252b92077effcd9fdb315cdb5cf4d3bbcab68363c42'){throw 'Original running adapter drift'}
if($CheckOnly){Write-Output 'AUTHENTICATED_FULL_ANALYSIS_NO_STOP';exit 0}
$rflReview=Get-Content -LiteralPath (Join-Path $rflFolder 'source_bound_parallel_design_review.json') -Raw | ConvertFrom-Json
if($rflReview.decision -cne 'VALID' -or $rflReview.fresh_checks.tests -lt 80 -or $rflReview.fresh_checks.failures -ne 0 -or $rflReview.fresh_checks.errors -ne 0 -or $rflReview.fresh_checks.skipped -ne 0){throw 'Fresh design backend review invalid'}
foreach($rflItem in $rflReview.binding.analysis_execution_files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $rflFolder $rflItem.Name)).Hash.ToLowerInvariant() -cne $rflItem.Value){throw 'Reviewed backend bytes changed'}
}
$rflAnalysisProcess=Assert-RflIdentity $rflReg.analysis_pid $rflReg.analysis_start_utc_ticks $rflAnalysisCommand
$null=Assert-RflIdentity $rflReg.parent_pid $rflReg.parent_start_utc_ticks $rflParentCommand
Assert-RflStillUnfinished
# New explicit user authorization permits this full ANALYSIS interruption, not any seed acquisition restart.
Stop-Process -InputObject $rflAnalysisProcess -Force
$rflDeadline=[DateTime]::UtcNow.AddSeconds(45)
while([DateTime]::UtcNow -lt $rflDeadline){
    if($rflParentProcess.HasExited -and (Test-Path -LiteralPath (Join-Path $rflParent 'pipeline_exit.json'))){break}
    Start-Sleep -Milliseconds 200
}
if(-not $rflParentProcess.HasExited -or -not (Test-Path -LiteralPath (Join-Path $rflParent 'pipeline_exit.json'))){throw 'Real native old controller/launcher exit not observed'}
$rflNative=Get-Content -LiteralPath (Join-Path $rflParent 'design_lock.receipt.json') -Raw | ConvertFrom-Json
$rflExit=Get-Content -LiteralPath (Join-Path $rflParent 'pipeline_exit.json') -Raw | ConvertFrom-Json
if($rflNative.native_exit_code -eq 0 -or $rflExit.native_exit_code -ne 2 -or [long]$rflExit.start_utc_ticks -ne [long]$rflReg.parent_start_utc_ticks){throw 'Unexpected native old exit; refuse new analysis'}
if(Test-Path -LiteralPath (Join-Path $rflParent 'pipeline_result.json')){throw 'Old final result exists; cannot restart analysis'}
$rflObservation=@{role='EXTERNAL_USER_AUTHORIZED_FULL_ANALYSIS_SWITCH_NOT_NATIVE_RECEIPT';observed_at=[DateTime]::UtcNow.ToString('o');stopped_analysis_pid=$rflReg.analysis_pid;actual_start_ticks=$rflReg.analysis_start_utc_ticks;native_old_child_exit=$rflNative.native_exit_code;native_old_controller_exit=$rflExit.native_exit_code;new_acquisition=$false;scientific_outcome_claimed=$false;automatic_retry=$false}
$rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflObservation | ConvertTo-Json -Depth 5 -Compress))
$rflStream=[IO.File]::Open((Join-Path $rflFolder 'parent_switch_observation.json'),[IO.FileMode]::CreateNew)
try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
Write-Output 'AUTHORIZED_FULL_ANALYSIS_SWITCH_NATIVE_EXITS_CONFIRMED'
