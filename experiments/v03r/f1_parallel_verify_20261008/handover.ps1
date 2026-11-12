param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$rflRoot='D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflFolder=Join-Path $rflRoot 'experiments\v03r\f1_parallel_verify_20261008'
$rflParent=Join-Path $rflRoot 'experiments\v03r\parallel_verify_restart_20261008'
$rflReg=Get-Content -LiteralPath (Join-Path $rflFolder 'preregistration.json') -Raw | ConvertFrom-Json
function Assert-RflIdentity($rflId,$rflTicks,$rflCommand){
    $rflCim=Get-CimInstance Win32_Process -Filter "ProcessId=$rflId"
    if(-not $rflCim -or $rflCim.CommandLine -cne $rflCommand){throw 'Process full command mismatch/absent'}
    $rflProcess=Get-Process -Id $rflId -ErrorAction Stop
    if($rflProcess.StartTime.ToUniversalTime().Ticks -ne [long]$rflTicks){throw 'Process actual start ticks mismatch'}
    return $rflProcess
}
function Assert-RflNoFullF1 {
    foreach($rflName in @('design_lock.receipt.json','pipeline_result.json','pipeline_exit.json','pipeline_failure.json','design_lock_plan.receipt.json')){
        if(Test-Path -LiteralPath (Join-Path $rflParent $rflName)){throw 'Parent advanced or exited; refuse handover'}
    }
    if(Test-Path -LiteralPath (Join-Path $rflRoot 'experiments\v03r\dev_lock.json')){throw 'Full F1 output exists; refuse handover'}
    $rflLines=Get-Content -LiteralPath (Join-Path $rflParent 'pipeline.stdout.log')
    if(@($rflLines | Where-Object {$_.StartsWith('START design_lock ')}).Count -ne 0){throw 'Original full F1 has started'}
    if($rflLines[-1] -notlike 'START design_lock_plan *'){throw 'Parent is not waiting in read-only plan'}
}
$rflParentCommand='"D:\python\python.exe" -u -B -X utf8 "'+(Join-Path $rflParent 'resume_after_shutdown.py')+'"'
$rflPlanCommand='D:\python\python.exe -B -X utf8 scripts/run_dev_lock.py --design '+(Join-Path $rflRoot 'experiments\v03r\dev_baseline.json')+' --manifest '+(Join-Path $rflParent 'f0_manifest_after_shutdown.json')+' --plan'
$rflParentProcess=Assert-RflIdentity $rflReg.parent_pid $rflReg.parent_start_utc_ticks $rflParentCommand
$rflPlanProcess=Assert-RflIdentity $rflReg.plan_pid $rflReg.plan_start_utc_ticks $rflPlanCommand
$rflPlanCim=Get-CimInstance Win32_Process -Filter "ProcessId=$($rflReg.plan_pid)"
if($rflPlanCim.ParentProcessId -ne $rflReg.parent_pid){throw 'Read-only plan is not the registered parent child'}
$rflChildren=@(Get-CimInstance Win32_Process | Where-Object {$_.ParentProcessId -eq $rflReg.parent_pid -and $_.Name -eq 'python.exe'})
if($rflChildren.Count -ne 1 -or $rflChildren[0].ProcessId -ne $rflReg.plan_pid){throw 'Parent has another Python child'}
if((Get-FileHash -LiteralPath (Join-Path $rflRoot 'scripts\run_dev_lock.py')).Hash.ToLowerInvariant() -ne '1e3cf733107471a5f68822f1b0528e09d2a6f5920c96a74ce611c18fd3a2ac7d'){throw 'Original plan CLI drift'}
Assert-RflNoFullF1
if($CheckOnly){Write-Output 'AUTHENTICATED_READ_ONLY_PLAN_NO_STOP';exit 0}
$rflReviewPath=Join-Path $rflFolder 'source_bound_parallel_f1_review.json'
$rflReview=Get-Content -LiteralPath $rflReviewPath -Raw | ConvertFrom-Json
if($rflReview.decision -cne 'VALID' -or $rflReview.sources_digest -cne $rflReg.sources_digest -or $rflReview.fresh_operational_tests.failures -ne 0 -or $rflReview.fresh_operational_tests.tests -lt 40){throw 'Fresh source-bound review invalid'}
foreach($rflItem in $rflReview.operational_control_files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $rflFolder $rflItem.Name)).Hash.ToLowerInvariant() -cne $rflItem.Value){throw 'Reviewed operational bytes changed'}
}
# Reauthenticate immediately before the only stop. Stop the Process object, not an unauthenticated PID.
$rflPlanProcess=Assert-RflIdentity $rflReg.plan_pid $rflReg.plan_start_utc_ticks $rflPlanCommand
$null=Assert-RflIdentity $rflReg.parent_pid $rflReg.parent_start_utc_ticks $rflParentCommand
Assert-RflNoFullF1
Stop-Process -InputObject $rflPlanProcess -Force
$rflDeadline=[DateTime]::UtcNow.AddSeconds(45)
while([DateTime]::UtcNow -lt $rflDeadline){
    if((Test-Path -LiteralPath (Join-Path $rflParent 'pipeline_exit.json')) -and $rflParentProcess.HasExited){break}
    Start-Sleep -Milliseconds 200
}
if(-not $rflParentProcess.HasExited -or -not (Test-Path -LiteralPath (Join-Path $rflParent 'pipeline_exit.json'))){throw 'Native parent/launcher exit not observed; no new F1 allowed'}
$rflNativePlan=Get-Content -LiteralPath (Join-Path $rflParent 'design_lock_plan.receipt.json') -Raw | ConvertFrom-Json
$rflNativeExit=Get-Content -LiteralPath (Join-Path $rflParent 'pipeline_exit.json') -Raw | ConvertFrom-Json
if($rflNativePlan.native_exit_code -eq 0 -or $rflNativeExit.native_exit_code -ne 2 -or [long]$rflNativeExit.start_utc_ticks -ne [long]$rflReg.parent_start_utc_ticks){throw 'Native exit identity/status not as expected'}
if(Test-Path -LiteralPath (Join-Path $rflParent 'design_lock.receipt.json')){throw 'Original full F1 advanced; refuse duplicate'}
$rflObservation=@{role='EXTERNAL_AUTHENTICATED_READ_ONLY_PLAN_HANDOVER_NOT_NATIVE_RECEIPT';parent_native_receipts_exist=$true;stopped_child_pid=$rflReg.plan_pid;child_start_utc_ticks=$rflReg.plan_start_utc_ticks;parent_pid=$rflReg.parent_pid;parent_native_exit_code=$rflNativeExit.native_exit_code;observed_at=[DateTime]::UtcNow.ToString('o');new_scientific_draws=0;automatic_retry=$false}
$rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflObservation | ConvertTo-Json -Depth 5 -Compress))
$rflStream=[IO.File]::Open((Join-Path $rflFolder 'parent_switch_observation.json'),[IO.FileMode]::CreateNew)
try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
Write-Output 'AUTHENTICATED_PLAN_STOP_AND_NATIVE_PARENT_EXIT_CONFIRMED'
