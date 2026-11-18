$ErrorActionPreference = 'Stop'
$pilotRoot = 'D:\agentsync-debug\m6-protocol-diagnostic-20261112'
$authPath = Join-Path $pilotRoot 'private-home\auth.json'
if (Test-Path -LiteralPath (Join-Path $pilotRoot 'attempt.json')) {
    $resultPath = Join-Path $pilotRoot 'result.json'
    if (-not (Test-Path -LiteralPath $resultPath)) {
        throw 'Inspect owned process status before temporary authentication cleanup.'
    }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if ($result.attempts[0].parent_ended -ne $true) {
        throw 'Owned process termination is not confirmed. Inspect before cleanup.'
    }
}
if (Test-Path -LiteralPath $authPath) {
    $authItem = Get-Item -LiteralPath $authPath -Force
    if ($authItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Unexpected reparse point; preserve for manual inspection.'
    }
    if ($authItem.FullName -ne $authPath) { throw 'Unexpected authentication path.' }
    Remove-Item -LiteralPath $authPath
}
if (Test-Path -LiteralPath $authPath) { throw 'Temporary authentication still exists.' }
Write-Output 'Temporary authentication absent; original file was not touched.'
