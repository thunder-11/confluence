$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build the dashboard with scripts/setup.ps1 first.' }
try { $existingService = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2 } catch { $existingService = $null }
if ($existingService.version -eq '1.0.0' -and $existingService.engine) {
    Write-Host 'CONFLUENCE is already running at http://127.0.0.1:8000'
    exit 0
}
& ./.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
