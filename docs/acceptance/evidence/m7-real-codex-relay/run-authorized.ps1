$ErrorActionPreference = 'Stop'
$taskRoot = 'D:\agentsync-debug\m7-two-codex-live-20261112'
$taskSource = 'C:\Users\JayChan\.codex\auth.json'
$taskTargets = @(Join-Path $taskRoot 'worker-0\private-home\auth.json'; Join-Path $taskRoot 'worker-1\private-home\auth.json')
if (Test-Path -LiteralPath (Join-Path $taskRoot 'attempt.json')) { throw 'Possible earlier execution; no retry.' }
$taskSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
foreach ($taskPath in @($taskRoot, $taskSource, (Join-Path $taskRoot 'worker-0'), (Join-Path $taskRoot 'worker-1'), (Join-Path $taskRoot 'worker-0\private-home'), (Join-Path $taskRoot 'worker-1\private-home'))) {
    $taskItem = Get-Item -LiteralPath $taskPath -Force
    if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected reparse point.' }
    if ($taskPath -ne $taskSource) {
        foreach ($taskAce in (Get-Acl -LiteralPath $taskPath).Access) {
            $taskAceSid = $taskAce.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
            if ($taskAce.AccessControlType -eq 'Allow' -and $taskAceSid -notin @($taskSid, 'S-1-5-18')) { throw 'Unexpected private-directory access.' }
        }
    }
}
foreach ($taskPath in $taskTargets) {
    if (Test-Path -LiteralPath $taskPath) { throw 'Preserve existing credential.' }
    if ([IO.Path]::GetFullPath($taskPath) -ne $taskPath -or -not $taskPath.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected cleanup target.' }
}
$taskOriginalHash = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash
$taskCopied = 0
$taskExit = $null
try {
    foreach ($taskPath in $taskTargets) {
        Copy-Item -LiteralPath $taskSource -Destination $taskPath
        $taskCopied++
        if ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash -ne $taskOriginalHash) { throw 'Copy mismatch.' }
    }
    $env:PYTHONPATH = 'F:\syuc\amadeus-m6-single\src'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & 'D:\agentsync-debug\continuation-cc30ed21\windows-py312-venv\Scripts\python.exe' -X utf8 (Join-Path $taskRoot 'relay.py') execute-once *> (Join-Path $taskRoot 'execution-host.log')
    $taskExit = $LASTEXITCODE
} finally {
    if (Test-Path -LiteralPath (Join-Path $taskRoot 'attempt.json')) {
        $taskResultPath = Join-Path $taskRoot 'result.json'
        if (-not (Test-Path -LiteralPath $taskResultPath)) { throw 'Unknown process state: inspect before credential cleanup.' }
        $taskResult = Get-Content -LiteralPath $taskResultPath -Raw | ConvertFrom-Json
        if ($taskResult.start_requests -ne $taskResult.captures_returned -or @($taskResult.private_capture_metadata).Count -ne $taskResult.captures_returned) { throw 'Capture accounting unknown: inspect before cleanup.' }
        foreach ($taskCapture in $taskResult.private_capture_metadata) {
            if ($taskCapture.parent_ended -ne $true) { throw 'Parent termination unknown: inspect before cleanup.' }
        }
    }
    foreach ($taskPath in $taskTargets) {
        if (Test-Path -LiteralPath $taskPath) {
            $taskItem = Get-Item -LiteralPath $taskPath -Force
            if ($taskItem.FullName -ne $taskPath -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected cleanup item.' }
            Remove-Item -LiteralPath $taskPath
        }
    }
    $taskCleanup = @{
        time_utc = [DateTimeOffset]::UtcNow.ToString('o')
        temporary_copies_created = $taskCopied
        temporary_copies_absent = @($taskTargets | ForEach-Object { -not (Test-Path -LiteralPath $_) })
        original_auth_unchanged = ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash -eq $taskOriginalHash)
        host_exit_code = $taskExit
    }
    $taskCleanup | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot 'cleanup.json') -Encoding utf8
    $taskCleanup | ConvertTo-Json
}
Get-Content -LiteralPath (Join-Path $taskRoot 'execution-host.log') -Tail 3
