param([switch]$Elevated)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$log = Join-Path $repo 'runtime\camera-system.log'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    if ($Elevated) { throw 'Administrator approval required' }
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Elevated') -Verb RunAs -WindowStyle Hidden
    Write-Output 'Requested administrator approval. Result: runtime/camera-system.log'
    exit 0
}
try {
    New-Item -ItemType Directory -Path (Join-Path $repo 'runtime') -Force | Out-Null
    $source = Join-Path $repo 'vendor\softcam.dll'
    $cameraDir = 'C:\ProgramData\PhoneBridge\Camera'
    $dll = Join-Path $cameraDir 'softcam64.dll'
    New-Item -ItemType Directory -Path $cameraDir -Force | Out-Null
    if (Test-Path -LiteralPath $dll) {
        if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $dll).Hash) {
            throw 'A different system camera DLL already exists; it must be inspected before replacement'
        }
    } else { Copy-Item -LiteralPath $source -Destination $dll }
    $process = Start-Process -FilePath "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @('/s',('"'+$dll+'"')) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode) { throw "Camera COM registration failed: $($process.ExitCode)" }
    # Existing HKCU COM registration takes precedence in merged HKCR; this DLL's
    # FilterMapper consequently writes its category back to HKCU even elevated.
    # Promote only this known filter's verified metadata, never other cameras.
    $cameraClsid = '{7CE53ADD-BFF6-4B6F-8E16-1F9C6F9189C2}'
    $classRelative = 'SOFTWARE\Classes\CLSID\' + $cameraClsid
    $userClass = 'HKCU:\' + $classRelative
    $machineClass = 'HKLM:\' + $classRelative
    $userServer = (Get-Item -LiteralPath ($userClass+'\InprocServer32')).GetValue('')
    if ([IO.Path]::GetFullPath($userServer) -ne [IO.Path]::GetFullPath($dll)) { throw 'Unexpected Softcam COM server path; refusing to promote registration' }
    New-Item -Path ($machineClass+'\InprocServer32') -Force | Out-Null
    Set-Item -LiteralPath $machineClass -Value 'PhoneBridge Camera'
    Set-Item -LiteralPath ($machineClass+'\InprocServer32') -Value $dll
    $threading = (Get-Item -LiteralPath ($userClass+'\InprocServer32')).GetValue('ThreadingModel')
    if ($threading) { New-ItemProperty -LiteralPath ($machineClass+'\InprocServer32') -Name ThreadingModel -Value $threading -PropertyType String -Force | Out-Null }
    $categoryRelative = 'SOFTWARE\Classes\CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance\AWC Virtual Cam'
    $userCategory = Get-Item -LiteralPath ('HKCU:\'+$categoryRelative)
    if ($userCategory.GetValue('CLSID') -ne $cameraClsid) { throw 'Unexpected camera class ID' }
    $filterData = $userCategory.GetValue('FilterData')
    if ($filterData -isnot [byte[]]) { throw 'Missing DirectShow filter metadata' }
    $machineCategory = 'HKLM:\'+$categoryRelative
    New-Item -Path $machineCategory -Force | Out-Null
    New-ItemProperty -LiteralPath $machineCategory -Name CLSID -Value $cameraClsid -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $machineCategory -Name FilterData -Value $filterData -PropertyType Binary -Force | Out-Null
    New-ItemProperty -LiteralPath $machineCategory -Name FriendlyName -Value 'PhoneBridge Camera' -PropertyType String -Force | Out-Null
    Set-ItemProperty -LiteralPath ('HKCU:\'+$categoryRelative) -Name FriendlyName -Value 'PhoneBridge Camera'
    "SUCCESS: PhoneBridge Camera registered system-wide (64-bit DirectShow). DLL=$dll; 32-bit/Media Foundation not installed." | Set-Content -LiteralPath $log -Encoding utf8
} catch { $_.Exception.Message | Set-Content -LiteralPath $log -Encoding utf8; throw }
