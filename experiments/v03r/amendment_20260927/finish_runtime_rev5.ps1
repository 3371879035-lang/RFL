param(
    [Parameter(Mandatory=$true)][int]$BenchmarkProcessId,
    [Parameter(Mandatory=$true)][long]$ExpectedStartUtcTicks
)

# One-shot dependent job: wait for this exact benchmark, then verify its outputs.
# No rerun, scientific seed draw, Git mutation, or source edit occurs here.
# After verified timing, only the existing source-bound review can finalize a NEW
# manifest candidate. Stage runners still require committed bytes before use.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$python = 'D:\python\python.exe'
$inspector = Join-Path $PSScriptRoot 'inspect_runtime_rev5.py'
$receipt = Join-Path $PSScriptRoot 'runtime_completion_verified.json'
Set-Location -LiteralPath $root
try {
    $benchmark = Get-Process -Id $BenchmarkProcessId -ErrorAction SilentlyContinue
    if ($null -ne $benchmark) {
        if ($benchmark.StartTime.ToUniversalTime().Ticks -ne $ExpectedStartUtcTicks) {
            throw 'Benchmark PID was reused; refusing to wait on another process.'
        }
        Write-Output ('WAITING ' + [DateTime]::UtcNow.ToString('o') + ' pid=' + $BenchmarkProcessId)
        $benchmark.WaitForExit()
    }
    Write-Output ('VERIFYING ' + [DateTime]::UtcNow.ToString('o'))
    & $python $inspector --verify --output $receipt
    $verifyExit = $LASTEXITCODE
    Write-Output ('FINISHED ' + [DateTime]::UtcNow.ToString('o') + ' verifier_exit=' + $verifyExit)
    if ($verifyExit -eq 0) {
        & $python (Join-Path $root 'scripts/f0_manifest.py') --finalize --runtime (Join-Path $root 'experiments/v03r/f0_runtime_rev5/runtime.json') --review (Join-Path $PSScriptRoot 'source_bound_review.json') --output (Join-Path $PSScriptRoot 'f0_manifest_rev5.json')
        $finalizeExit = $LASTEXITCODE
        Write-Output ('MANIFEST_CANDIDATE ' + [DateTime]::UtcNow.ToString('o') + ' finalize_exit=' + $finalizeExit + ' committed=false scientific_stages_started=false')
        exit $finalizeExit
    }
    exit $verifyExit
} catch {
    Write-Error -ErrorAction Continue $_
    exit 2
}
