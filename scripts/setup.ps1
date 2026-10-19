param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repo
try {
    & $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'
    if ($LASTEXITCODE) { throw 'Python 3.12+ required' }
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE) { throw 'Python venv failed' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE) { throw 'Dependency installation failed' }
    Write-Output 'Python dependencies ready. See docs/DEPENDENCIES.md for optional tools; run start.bat.'
} finally { Pop-Location }
