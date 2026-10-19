$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE) { throw 'Python 3.12+ required' }
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE) { throw 'Dependency installation failed' }
}
$env:PYTHONUTF8 = '1'
& $python -m phonebridge
if ($LASTEXITCODE) { throw 'PhoneBridge exited with an error' }
