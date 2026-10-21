param(
    [string]$Root = 'D:\agentsync-debug',
    [ValidateSet('whpx', 'tcg')][string]$Accelerator = 'whpx'
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath($Root)
if (-not $taskRoot.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The authorized debug environment must remain on D:'
}
$taskExe = Join-Path $taskRoot 'tools\qemu\qemu-system-x86_64.exe'
$taskDisk = Join-Path $taskRoot 'vm\guest.qcow2'
$taskSeed = Join-Path $taskRoot 'vm\seed.iso'
foreach ($taskPath in @($taskExe, $taskDisk, $taskSeed)) {
    if (-not (Test-Path -LiteralPath $taskPath -PathType Leaf)) { throw 'Missing VM input' }
}
foreach ($taskPort in @(22222, 22223)) {
    if (Get-NetTCPConnection -LocalPort $taskPort -State Listen -ErrorAction SilentlyContinue) {
        throw 'A required loopback port is already occupied; no existing process was stopped'
    }
}
$taskAccelOption = if ($Accelerator -eq 'whpx') { 'whpx,kernel-irqchip=off' } else { 'tcg,thread=multi' }
$taskCores = if ($Accelerator -eq 'whpx') { '1' } else { '2' }
$taskArgs = @(
    '-machine', 'q35', '-accel', $taskAccelOption, '-cpu', 'qemu64,svm=off',
    '-smp', $taskCores, '-m', '3072',
    '-drive', "file=$taskDisk,format=qcow2,if=virtio",
    '-drive', "file=$taskSeed,format=raw,media=cdrom,readonly=on",
    '-nic', 'user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:22222-:22',
    '-device', 'virtio-rng-pci', '-display', 'none',
    '-serial', "file:$taskRoot\vm\serial.log",
    '-qmp', 'tcp:127.0.0.1:22223,server=on,wait=off'
)
$taskProcess = Start-Process -FilePath $taskExe -ArgumentList $taskArgs -PassThru `
    -WindowStyle Hidden -WorkingDirectory $taskRoot `
    -RedirectStandardOutput "$taskRoot\vm\qemu.stdout.log" `
    -RedirectStandardError "$taskRoot\vm\qemu.stderr.log"
@{ pid = $taskProcess.Id; executable = $taskExe; accelerator = $Accelerator; disk = $taskDisk } |
    ConvertTo-Json | Set-Content -LiteralPath "$taskRoot\vm\process.json" -Encoding utf8
Write-Output "Started local debug VM process $($taskProcess.Id) ($Accelerator)"
