param([switch]$Integration)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Check failed with exit code $LASTEXITCODE" } }
Push-Location (Join-Path $projectRoot 'backend')
try {
    $pythonExe = Join-Path $PWD '.venv/Scripts/python.exe'
    if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }
    & $pythonExe -m ruff check . ../scripts
    Check-Exit
    & $pythonExe -m ruff format --check . ../scripts
    Check-Exit
    & $pythonExe -m mypy app
    Check-Exit
    if ($Integration) {
        if (-not $env:TEST_DATABASE_URL) { throw 'Set TEST_DATABASE_URL to a migrated PostgreSQL database first.' }
        & $pythonExe -m pytest
    } else { & $pythonExe -m pytest -m 'not integration' }
    Check-Exit
} finally { Pop-Location }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    npm.cmd run lint
    Check-Exit
    npm.cmd run format:check
    Check-Exit
    npm.cmd run typecheck
    Check-Exit
    npm.cmd test
    Check-Exit
    npm.cmd run build
    Check-Exit
} finally { Pop-Location }
