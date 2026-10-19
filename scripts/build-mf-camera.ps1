param([string]$Compiler=$env:PHONEBRIDGE_CXX)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$header=Join-Path $repo 'vendor\mfvirtualcamera.h'
if(-not(Test-Path -LiteralPath $header)) {
    Invoke-WebRequest 'https://raw.githubusercontent.com/microsoft/win32metadata/76c04c2021ef4a831a6f1e06d9566002d746139b/generation/WinSDK/RecompiledIdlHeaders/um/mfvirtualcamera.h' -OutFile $header
}
if((Get-FileHash -LiteralPath $header).Hash -ne 'ACF37CDD4BFEA8FCF2B84ADBDEB450351EE1211B0ED00F779F0ACFFC9DFDF2FC'){throw 'Microsoft SDK header hash mismatch'}
$stage=Join-Path ([IO.Path]::GetTempPath()) ('PhoneBridge-mf-build-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
New-Item -ItemType Junction -Path (Join-Path $stage 'repo') -Target $repo | Out-Null
$repo=Join-Path $stage 'repo'
$directory=Join-Path $repo 'native\mf-camera\build'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
if (-not $Compiler) {
    $command=Get-Command g++.exe -ErrorAction SilentlyContinue
    if ($command) { $Compiler=$command.Source } else { $Compiler='C:\msys64\ucrt64\bin\g++.exe' }
}
if (-not (Test-Path -LiteralPath $compiler)) { throw 'MinGW-w64 UCRT C++ compiler required; no system compiler is automatically installed.' }
$argsCommon=@('-std=c++17','-O2','-DUNICODE','-D_UNICODE','-D_WIN32_WINNT=0x0A00','-static','-static-libgcc','-static-libstdc++')
& $compiler @argsCommon '-shared' (Join-Path $repo 'native\mf-camera\source.cpp') '-o' (Join-Path $directory 'PhoneBridgeMF.dll') '-lmfplat' '-lmfuuid' '-lole32' '-lpropsys' '-lshell32' '-ladvapi32' '-luuid'
if ($LASTEXITCODE) { throw 'MF source compilation failed' }
& $compiler @argsCommon '-municode' (Join-Path $repo 'native\mf-camera\register.cpp') '-o' (Join-Path $directory 'PhoneBridgeMFRegister.exe') '-lmfplat' '-lmfuuid' '-lole32' '-luuid'
if ($LASTEXITCODE) { throw 'MF registration helper compilation failed' }
& $compiler @argsCommon '-municode' (Join-Path $repo 'native\mf-camera\probe.cpp') '-o' (Join-Path $directory 'PhoneBridgeMFProbe.exe') '-lmfplat' '-lmfuuid' '-lmf' '-lmfreadwrite' '-lole32' '-luuid'
if ($LASTEXITCODE) { throw 'MF consumer probe compilation failed' }
Write-Output "Built: $directory"
