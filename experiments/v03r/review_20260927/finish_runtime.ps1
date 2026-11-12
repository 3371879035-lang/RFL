param(
    [Parameter(Mandatory=$true)][int]$BenchmarkProcessId,
    [Parameter(Mandatory=$true)][long]$ExpectedStartUtcTicks
)

# One-shot dependent job: wait for this exact benchmark, then verify its outputs.
# No rerun, seed draw, F0 approval, Git mutation, or source edit occurs here.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$python = 'D:\python\python.exe'
$inspector = Join-Path $PSScriptRoot 'inspect_runtime.py'
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
    exit $verifyExit
} catch {
    Write-Error -ErrorAction Continue $_
    exit 2
}
