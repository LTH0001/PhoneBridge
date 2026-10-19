$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $repo 'vendor\vb-cable\VBCABLE_Setup_x64.exe'
if (-not (Test-Path -LiteralPath $setup)) {
    $archive = Join-Path $repo 'vendor\VBCABLE_Driver_Pack45.zip'
    Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip' -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $repo 'vendor\vb-cable')
}
$sig = Get-AuthenticodeSignature -FilePath $setup
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'BUREL|Vincent Burel') {
    throw 'VB-CABLE installer signature is not valid'
}
$stage = Join-Path ([IO.Path]::GetTempPath()) 'PhoneBridge-VBCABLE'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -Path (Join-Path (Split-Path $setup -Parent) '*') -Destination $stage -Force
$setup = Join-Path $stage 'VBCABLE_Setup_x64.exe'
# This is an interactive installer the user must see, not a background helper.
Start-Process -FilePath $setup -Verb RunAs -WorkingDirectory (Split-Path $setup -Parent) -WindowStyle Normal
Write-Output 'VB-CABLE setup opened. Choose Install Driver; reboot only when convenient.'
