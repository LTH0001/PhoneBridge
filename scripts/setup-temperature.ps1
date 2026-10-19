# Download official, pinned sensor dependencies. This script does not install drivers.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$vendor=Join-Path $repo 'vendor'
New-Item -ItemType Directory -Path $vendor -Force | Out-Null
$downloads=@(
    @('LibreHardwareMonitor-v0.9.6.zip','https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip','086D9F1B5A99E643EDC2CFAAAC16051685B551E4C5AC0B32A57C58C0E529C001'),
    @('PawnIO_setup.exe','https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe','1F519A22E47187F70A1379A48CA604981C4FCF694F4E65B734AAA74A9FBA3032')
)
foreach ($item in $downloads) {
    $file=Join-Path $vendor $item[0]
    if (-not (Test-Path -LiteralPath $file)) { Invoke-WebRequest $item[1] -OutFile $file }
    if ((Get-FileHash -LiteralPath $file).Hash -ne $item[2]) { throw "Dependency hash mismatch: $($item[0]); inspect the existing file before replacement" }
}
$signature=Get-AuthenticodeSignature -LiteralPath (Join-Path $vendor 'PawnIO_setup.exe')
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=namazso.eu,') { throw 'Invalid PawnIO official signature' }
$licenses=Join-Path $vendor 'temperature-licenses'
New-Item -ItemType Directory -Path $licenses -Force | Out-Null
Invoke-WebRequest 'https://raw.githubusercontent.com/LibreHardwareMonitor/LibreHardwareMonitor/v0.9.6/LICENSE' -OutFile (Join-Path $licenses 'LHM-LICENSE.txt')
Invoke-WebRequest 'https://raw.githubusercontent.com/LibreHardwareMonitor/LibreHardwareMonitor/v0.9.6/THIRD-PARTY-NOTICES.txt' -OutFile (Join-Path $licenses 'LHM-THIRD-PARTY-NOTICES.txt')
Invoke-WebRequest 'https://raw.githubusercontent.com/namazso/PawnIO/master/COPYING' -OutFile (Join-Path $licenses 'PawnIO-COPYING.txt')
Write-Output 'Verified LHM 0.9.6 and signed PawnIO 2.2.0. To enable sensors, use the PhoneBridge GUI CPU temperature button.'
