param([switch]$Elevated)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    if($Elevated){throw 'Administrator approval required'}
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Elevated') -Verb RunAs -WindowStyle Hidden
    Write-Output 'Requested administrator approval for the native Media Foundation camera.'
    exit 0
}
$directory=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'PhoneBridge\MFCamera'
$frames=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'PhoneBridge\CameraFrames'
foreach($path in @((Split-Path $directory -Parent),$directory,(Split-Path $frames -Parent),$frames)) {
    if((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Refusing redirected camera installation path'}
    if(-not(Test-Path -LiteralPath $path)){New-Item -ItemType Directory -Path $path | Out-Null}
}
$log=Join-Path $directory 'setup.log'
try {
    foreach($path in @($directory,$frames)) {
        $acl=New-Object Security.AccessControl.DirectorySecurity
        $acl.SetAccessRuleProtection($true,$false)
        $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
        foreach($sid in @('S-1-5-18','S-1-5-32-544','S-1-5-32-545','S-1-5-19')) {
            $rights=if($sid -in @('S-1-5-18','S-1-5-32-544')){'FullControl'}else{'ReadAndExecute'}
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),$rights,'ContainerInherit,ObjectInherit','None','Allow')))
        }
        if($path -eq $frames) {
            # Only the installing user's ordinary host writes pixel data. No
            # executable, IPC command or camera permission is exposed here.
            $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'Modify','ContainerInherit,ObjectInherit','None','Allow')))
        }
        Set-Acl -LiteralPath $path -AclObject $acl
    }
    $source=Join-Path $repo 'native\mf-camera\build\PhoneBridgeMF.dll'
    $hash=(Get-FileHash -LiteralPath $source).Hash.ToLower()
    $dll=Join-Path $directory ('PhoneBridgeMF-'+$hash.Substring(0,12)+'.dll')
    if(-not(Test-Path -LiteralPath $dll)){Copy-Item -LiteralPath $source -Destination $dll}
    if((Get-FileHash -LiteralPath $dll).Hash.ToLower() -ne $hash){throw 'Installed MF source hash mismatch'}
    $helper=Join-Path $directory 'PhoneBridgeMFRegister.exe'
    Copy-Item -LiteralPath (Join-Path $repo 'native\mf-camera\build\PhoneBridgeMFRegister.exe') -Destination $helper -Force
    if(Test-Path -LiteralPath (Join-Path $repo 'vendor\mf-camera-reference\LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $repo 'vendor\mf-camera-reference\LICENSE') -Destination (Join-Path $directory 'REFERENCE-LICENSE.txt') -Force
    }
    $data=Join-Path $frames 'frame.bin'
    if(-not(Test-Path -LiteralPath $data)) {
        $stream=[IO.File]::Open($data,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
        try{$stream.SetLength(64+1280*720*4)}finally{$stream.Dispose()}
    } elseif((Get-Item -LiteralPath $data).Length -ne (64+1280*720*4)){throw 'Unexpected frame buffer size; refusing overwrite'}
    $registration=Start-Process -FilePath "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @('/s',('"'+$dll+'"')) -Wait -PassThru -WindowStyle Hidden
    if($registration.ExitCode){throw "Media source COM registration failed: $($registration.ExitCode)"}
    $output=& $helper 2>&1
    if($LASTEXITCODE){throw "Virtual camera creation failed: $output"}
    "SUCCESS: PhoneBridge native MF camera registered for all users. DLL=$dll; $output" | Set-Content -LiteralPath $log -Encoding utf8
} catch {$_.Exception.Message | Set-Content -LiteralPath $log -Encoding utf8;throw}
