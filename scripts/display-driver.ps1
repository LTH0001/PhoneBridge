param(
    [ValidateSet('install','enable','disable','status','configure')][string]$Action = 'status',
    [switch]$Elevated
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo 'runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$log = Join-Path $runtime 'display-driver.log'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Action -ne 'status' -and -not $isAdmin) {
    if ($Elevated) { throw 'Administrator approval required' }
    $argsList=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Action',$Action,'-Elevated')
    Start-Process -FilePath 'powershell.exe' -ArgumentList $argsList -Verb RunAs -WindowStyle Hidden
    Write-Output 'Requested Windows administrator approval. Result: runtime/display-driver.log'
    exit 0
}
try {
    function Get-PhoneBridgeDisplayDevice {
        Get-PnpDevice -FriendlyName 'Virtual Display Driver' -ErrorAction SilentlyContinue | Where-Object {
            $ids = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_HardwareIds' -ErrorAction SilentlyContinue).Data
            $ids -icontains 'Root\MttVDD'
        }
    }
    $devices = @(Get-PhoneBridgeDisplayDevice)
    if ($Action -eq 'status') { $devices | Select-Object InstanceId,Status,FriendlyName | ConvertTo-Json; exit 0 }
    $devcon = Join-Path $repo 'vendor\vdd-package\Dependencies\devcon.exe'
    $driverSource = Join-Path $repo 'vendor\vdd-package\SignedDrivers\x86\VDD'
    foreach($path in @($devcon,(Join-Path $driverSource 'MttVDD.dll'),(Join-Path $driverSource 'mttvdd.cat'))) {
        if ((Get-AuthenticodeSignature -FilePath $path).Status -ne 'Valid') { throw "Invalid signed display component: $path" }
    }
    if ($Action -eq 'install') {
        if ($devices.Count) { throw 'Virtual Display Driver already exists; reuse it rather than installing another device' }
        $installDir = 'C:\ProgramData\PhoneBridge\DisplayDriver'
        if (Test-Path -LiteralPath (Join-Path $installDir 'MttVDD.inf')) { throw 'Display backend files already exist; inspect runtime/display-driver.log before retrying' }
        $reg = 'HKLM:\SOFTWARE\MikeTheTech\VirtualDisplayDriver'
        if (Test-Path $reg) { throw 'An existing VirtualDrivers configuration must be preserved; configure/reuse it manually' }
        New-Item -ItemType Directory -Path $installDir -Force | Out-Null
        Copy-Item -Path (Join-Path $driverSource '*') -Destination $installDir
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'vdd_settings.xml') -Destination (Join-Path $installDir 'vdd_settings.xml') -Force
        New-Item -Path $reg -Force | Out-Null
        New-ItemProperty -Path $reg -Name 'VDDPATH' -Value $installDir -PropertyType String -Force | Out-Null
        & $devcon install (Join-Path $installDir 'MttVDD.inf') 'Root\MttVDD' 2>&1 | Tee-Object -FilePath $log
        if ($LASTEXITCODE -gt 1) { throw "Driver installation failed: $LASTEXITCODE (publisher confirmation or signing may be required)" }
    } elseif ($Action -eq 'configure') {
        if ($devices.Count -ne 1) { throw 'Expected exactly one MttVDD device' }
        $configuredDir = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\MikeTheTech\VirtualDisplayDriver').VDDPATH
        if ([IO.Path]::GetFullPath($configuredDir).TrimEnd('\') -ne 'C:\ProgramData\PhoneBridge\DisplayDriver') {
            throw 'Refusing to modify a display backend not managed by PhoneBridge'
        }
        $settings = Join-Path $configuredDir 'vdd_settings.xml'
        $backup = Join-Path $configuredDir ('vdd_settings.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.xml')
        Copy-Item -LiteralPath $settings -Destination $backup
        [xml]$currentSettings = Get-Content -LiteralPath $settings -Raw
        [xml]$phoneSettings = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'vdd_settings.xml') -Raw
        foreach ($mode in $phoneSettings.vdd_settings.resolutions.resolution) {
            $found = @($currentSettings.vdd_settings.resolutions.resolution | Where-Object { $_.width -eq $mode.width -and $_.height -eq $mode.height })
            if (-not $found.Count) { [void]$currentSettings.vdd_settings.resolutions.AppendChild($currentSettings.ImportNode($mode,$true)) }
        }
        $currentSettings.Save($settings)
        & $devcon restart ('@'+$devices[0].InstanceId) 2>&1 | Tee-Object -FilePath $log
        if ($LASTEXITCODE -gt 1) { Copy-Item -LiteralPath $backup -Destination $settings -Force; throw 'Virtual display restart failed; original XML restored' }
        "Phone aspect modes added. Backup: $backup" | Add-Content -LiteralPath $log
    } else {
        if ($devices.Count -ne 1) { throw 'Expected exactly one MttVDD device' }
        & $devcon $Action ('@'+$devices[0].InstanceId) 2>&1 | Tee-Object -FilePath $log
        if ($LASTEXITCODE -gt 1) { throw "Driver $Action failed: $LASTEXITCODE" }
    }
    Get-PhoneBridgeDisplayDevice | Select-Object InstanceId,Status,FriendlyName | ConvertTo-Json | Add-Content -LiteralPath $log
} catch {
    $_.Exception.Message | Add-Content -LiteralPath $log
    throw
}
