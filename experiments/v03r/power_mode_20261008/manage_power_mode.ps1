param([ValidateSet('Status','Watch','Restore')][string]$Mode='Status')
# User-approved resource lease only. No experiment edits, process stops or retries.
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$rflFolder=$PSScriptRoot
$rflRoot='D:\强化反馈学习\RFL-CausalChase-v0.3-parallel16-20261008'
$rflControllerId=27268
$rflControllerTicks='639270661004126546'
$rflControllerCommand='"D:\python\python.exe" -u -B -X utf8 "'+$rflRoot+'\experiments\v03r\f1_parallel_design_20261008\control_parallel_design.py"'
$rflTarget=[guid]'ded574b5-45a0-4f42-8737-46345c09c238'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RflPowerMode {
  [DllImport("powrprof.dll")] public static extern uint PowerGetUserConfiguredACPowerMode(out Guid mode);
  [DllImport("powrprof.dll")] public static extern uint PowerGetUserConfiguredDCPowerMode(out Guid mode);
  [DllImport("powrprof.dll")] public static extern uint PowerSetUserConfiguredACPowerMode(ref Guid mode);
  [DllImport("powrprof.dll")] public static extern uint PowerSetUserConfiguredDCPowerMode(ref Guid mode);
  [StructLayout(LayoutKind.Sequential)] public struct Supply {
    public byte ACLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
    public uint BatteryLifeTime, BatteryFullLifeTime;
  }
  [DllImport("kernel32.dll")][return: MarshalAs(UnmanagedType.Bool)]
  public static extern bool GetSystemPowerStatus(out Supply status);
}
'@
function Write-RflExclusive($rflName,$rflValue){
    $rflBytes=[Text.UTF8Encoding]::new($false).GetBytes(($rflValue|ConvertTo-Json -Depth 8 -Compress))
    $rflStream=[IO.File]::Open((Join-Path $rflFolder $rflName),[IO.FileMode]::CreateNew)
    try{$rflStream.Write($rflBytes,0,$rflBytes.Length)}finally{$rflStream.Dispose()}
}
function Get-RflPowerState {
    $rflAc=[guid]::Empty; $rflDc=[guid]::Empty
    $rflAcCode=[RflPowerMode]::PowerGetUserConfiguredACPowerMode([ref]$rflAc)
    $rflDcCode=[RflPowerMode]::PowerGetUserConfiguredDCPowerMode([ref]$rflDc)
    if($rflAcCode -ne 0 -or $rflDcCode -ne 0){throw "Power mode query failed AC=$rflAcCode DC=$rflDcCode"}
    $rflSupply=[RflPowerMode+Supply]::new()
    if(-not [RflPowerMode]::GetSystemPowerStatus([ref]$rflSupply)){throw 'Power supply query failed'}
    return @{ac=$rflAc.ToString();dc=$rflDc.ToString();ac_line_status=[int]$rflSupply.ACLineStatus;
        battery_percent=[int]$rflSupply.BatteryLifePercent;observed_at=[DateTime]::UtcNow.ToString('o')}
}
function Test-RflController {
    $rflRow=Get-CimInstance Win32_Process -Filter "ProcessId=$rflControllerId"
    if(-not $rflRow -or $rflRow.CommandLine -cne $rflControllerCommand){return $false}
    $rflProcess=Get-Process -Id $rflControllerId -ErrorAction SilentlyContinue
    return ($null -ne $rflProcess -and $rflProcess.StartTime.ToUniversalTime().Ticks.ToString() -ceq $rflControllerTicks)
}
function Restore-RflPower($rflLease,$rflReason){
    if(Test-Path -LiteralPath (Join-Path $rflFolder 'restored.json')){return}
    $rflActions=@{}
    foreach($rflChannel in @('ac','dc')){
        $rflCurrent=Get-RflPowerState
        $rflOriginal=[guid]$rflLease.original[$rflChannel]
        if($rflCurrent[$rflChannel] -ceq $rflLease.target){
            if($rflChannel -eq 'ac'){$rflCode=[RflPowerMode]::PowerSetUserConfiguredACPowerMode([ref]$rflOriginal)}
            else{$rflCode=[RflPowerMode]::PowerSetUserConfiguredDCPowerMode([ref]$rflOriginal)}
            if($rflCode -ne 0){throw "Restore failed channel=$rflChannel native=$rflCode"}
            if((Get-RflPowerState)[$rflChannel] -cne $rflOriginal.ToString()){throw 'Restore readback differs'}
            $rflActions[$rflChannel]='RESTORED_NATIVE_ZERO_AND_READBACK'
        } elseif($rflCurrent[$rflChannel] -ceq $rflOriginal.ToString()) {
            $rflActions[$rflChannel]='ALREADY_ORIGINAL'
        } else {$rflActions[$rflChannel]='PRESERVED_LATER_USER_CHANGE'}
    }
    Write-RflExclusive 'restored.json' @{status='RESTORED_OR_LATER_USER_CHANGE_PRESERVED';reason=$rflReason;
        actions=$rflActions;after=(Get-RflPowerState);observed_at=[DateTime]::UtcNow.ToString('o')}
}
if($Mode -eq 'Status'){Get-RflPowerState|ConvertTo-Json -Compress;exit 0}
$rflLeasePath=Join-Path $rflFolder 'lease.json'
if($Mode -eq 'Restore'){
    $rflLease=Get-Content -LiteralPath $rflLeasePath -Raw|ConvertFrom-Json -AsHashtable
    if((Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant() -cne $rflLease.script_sha256){throw 'Lease helper bytes changed'}
    Restore-RflPower $rflLease 'EXPLICIT_RECOVERY_OF_RECORDED_ORIGINAL_POWER_MODE'
    Get-RflPowerState|ConvertTo-Json -Compress
    exit 0
}
if(Test-Path -LiteralPath $rflLeasePath){throw 'Existing power lease: no duplicate apply or retry'}
if(-not (Test-RflController)){throw 'Registered running F1 controller identity does not match'}
$rflOriginal=Get-RflPowerState
if($rflOriginal.ac_line_status -eq 0 -and $rflOriginal.battery_percent -le 20){throw 'Low battery: refuse performance lease'}
$rflLease=@{role='USER_APPROVED_TEMPORARY_POWER_MODE_NOT_EXPERIMENT_RECEIPT';original=$rflOriginal;
    target=$rflTarget.ToString();watcher_pid=$PID;watcher_start_utc_ticks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks.ToString();
    controller_pid=$rflControllerId;controller_start_utc_ticks=$rflControllerTicks;controller_command=$rflControllerCommand;
    script_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();
    scientific_code_parameters_and_seeds_changed=$false;user_authorization='2026-10-08 可以的: temporary best performance then restore';
    restore_policy='restore on authenticated F1 exit/disappearance or battery<=20; preserve later user setting changes';
    observed_at=[DateTime]::UtcNow.ToString('o')}
Write-RflExclusive 'lease.json' $rflLease
try {
    if(-not (Test-RflController)){throw 'Controller exited before apply'}
    $rflAcCode=[RflPowerMode]::PowerSetUserConfiguredACPowerMode([ref]$rflTarget)
    if($rflAcCode -ne 0){throw "Apply AC failed native=$rflAcCode"}
    $rflDcCode=[RflPowerMode]::PowerSetUserConfiguredDCPowerMode([ref]$rflTarget)
    if($rflDcCode -ne 0){throw "Apply DC failed native=$rflDcCode"}
    $rflAfter=Get-RflPowerState
    if($rflAfter.ac -cne $rflTarget.ToString() -or $rflAfter.dc -cne $rflTarget.ToString()){throw 'Best performance configuration readback differs'}
    Write-RflExclusive 'applied.json' @{status='USER_CONFIGURED_BEST_PERFORMANCE_VERIFIED';ac_native_exit=$rflAcCode;
        dc_native_exit=$rflDcCode;after=$rflAfter;effective_mode_can_be_overridden_by_os=$true;measured_speedup_claimed=$false}
    $rflReason='AUTHENTICATED_F1_CONTROLLER_ENDED_OR_DISAPPEARED'
    while(Test-RflController){
        $rflPower=Get-RflPowerState
        if($rflPower.ac_line_status -eq 0 -and $rflPower.battery_percent -le 20){$rflReason='LOW_BATTERY_SAFETY_RESTORE';break}
        Start-Sleep -Seconds 15
    }
    Restore-RflPower $rflLease $rflReason
    exit 0
} catch {
    $rflError=$_.Exception.Message
    try{Restore-RflPower $rflLease 'POWER_LEASE_OPERATION_ERROR'}catch{$rflError+='; restore error: '+$_.Exception.Message}
    if(-not (Test-Path -LiteralPath (Join-Path $rflFolder 'failure.json'))){
        Write-RflExclusive 'failure.json' @{status='POWER_LEASE_FAILED';error=$rflError;observed_at=[DateTime]::UtcNow.ToString('o')}
    }
    throw $rflError
}
