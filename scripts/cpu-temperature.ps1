param([int]$OwnerPid, [switch]$Elevated, [switch]$InstallDriver)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ($OwnerPid -le 0) { throw 'Specify the PhoneBridge process ID with -OwnerPid' }
$owner = Get-Process -Id $OwnerPid
$ownerStarted = $owner.StartTime.ToUniversalTime().Ticks
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    if ($Elevated) { throw 'Administrator approval required' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Elevated','-OwnerPid',$OwnerPid)
    if ($InstallDriver) { $arguments += '-InstallDriver' }
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden
    Write-Output 'Requested administrator approval for read-only CPU temperature sampler.'
    exit 0
}
$root = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'PhoneBridge'
$destination = Join-Path $root 'Telemetry'
foreach ($path in @($root,$destination)) {
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a redirected installation path' }
    } else { New-Item -ItemType Directory -Path $path | Out-Null }
    # Do not allow ordinary processes to modify elevated executables or data.
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach ($sid in @('S-1-5-18','S-1-5-32-544','S-1-5-32-545')) {
        $rights = if ($sid -eq 'S-1-5-32-545') { 'ReadAndExecute' } else { 'FullControl' }
        $rule = New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),$rights,'ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $path -AclObject $acl
}
$log = Join-Path $destination 'setup.log'
try {
    $driverKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO'
    if (-not (Test-Path $driverKey)) {
        if (-not $InstallDriver) { throw 'PawnIO driver is not installed; explicitly use -InstallDriver for first setup' }
        $installer = Join-Path $repo 'vendor\PawnIO_setup.exe'
        if ((Get-FileHash -LiteralPath $installer).Hash -ne '1F519A22E47187F70A1379A48CA604981C4FCF694F4E65B734AAA74A9FBA3032') { throw 'PawnIO 2.2.0 hash mismatch' }
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=namazso.eu,') { throw 'PawnIO official signature verification failed' }
        # Official LHM installer uses -install; no unrestricted driver option.
        $installed = Start-Process -FilePath $installer -ArgumentList '-install' -Wait -PassThru -WindowStyle Hidden
        if ($installed.ExitCode -eq 3010) { throw 'PawnIO installation requires a reboot; no automatic reboot performed' }
        if ($installed.ExitCode -ne 0) { throw "PawnIO installer failed: $($installed.ExitCode)" }
        if (-not (Test-Path $driverKey)) { throw 'PawnIO installer did not register the driver' }
    }
    $executable = Join-Path $destination 'PhoneBridgeCpu.exe'
    $running = Get-CimInstance Win32_Process -Filter "Name='PhoneBridgeCpu.exe'" | Where-Object ExecutablePath -EQ $executable
    if ($running) { 'Sampler already running; no second instance started.' | Set-Content -LiteralPath $log; exit 0 }
    $archive = Join-Path $repo 'vendor\LibreHardwareMonitor-v0.9.6.zip'
    if ((Get-FileHash -LiteralPath $archive).Hash -ne '086D9F1B5A99E643EDC2CFAAAC16051685B551E4C5AC0B32A57C58C0E529C001') { throw 'LHM 0.9.6 hash mismatch' }
    # Extract the verified archive afresh into the admin-only install directory.
    Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
    $licenses = Join-Path $repo 'vendor\temperature-licenses'
    if (Test-Path -LiteralPath $licenses) { Copy-Item -LiteralPath $licenses -Destination (Join-Path $destination 'licenses') -Recurse -Force }
    $source = Join-Path $destination 'CpuTemperature.cs'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'CpuTemperature.cs') -Destination $source
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    $result = & $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$executable" /r:System.Web.Extensions.dll "/r:$(Join-Path $destination 'LibreHardwareMonitorLib.dll')" $source 2>&1
    if ($LASTEXITCODE -ne 0) { throw "CPU sampler compile failed: $result" }
    $process = Start-Process -FilePath $executable -ArgumentList @($OwnerPid,$ownerStarted) -WorkingDirectory $destination -PassThru -WindowStyle Hidden
    "SUCCESS: sampler PID=$($process.Id), owner PID=$OwnerPid; CPU-only, no hardware settings changed." | Set-Content -LiteralPath $log
} catch { $_.Exception.Message | Set-Content -LiteralPath $log; throw }
