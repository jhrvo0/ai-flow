# .ai-flow/scripts/run-dashboard.ps1
# Gera o dashboard e abre no navegador

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "generate-dashboard.py"
$OutputPath = Join-Path (Split-Path $PSScriptRoot) "dashboard.html"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Flow: Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERRO] Python nao encontrado." -ForegroundColor Red
    exit 1
}

try {
    & $pythonCmd $ScriptPath
    if ($LASTEXITCODE -eq 0 -and (Test-Path $OutputPath)) {
        Write-Host "[OK] Abrindo dashboard..." -ForegroundColor Green
        Start-Process $OutputPath
    }
} catch {
    Write-Host "[ERRO] $_" -ForegroundColor Red
    exit 1
}
