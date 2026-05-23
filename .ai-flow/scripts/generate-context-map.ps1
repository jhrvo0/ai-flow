# .ai-flow/scripts/generate-context-map.ps1
# Gera o mapa visual do projeto e abre no navegador

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "generate-context-map.py"
$OutputPath = Join-Path (Split-Path (Split-Path $PSScriptRoot)) ".ai-flow\reports\project-context.html"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Flow: Project Context Map" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERRO] Python nao encontrado." -ForegroundColor Red
    exit 1
}

try {
    & $pythonCmd $ScriptPath
    if ($LASTEXITCODE -eq 0 -and (Test-Path $OutputPath)) {
        Write-Host ""
        Write-Host "[OK] Abrindo no navegador..." -ForegroundColor Green
        Start-Process $OutputPath
    }
} catch {
    Write-Host "[ERRO] $_" -ForegroundColor Red
    exit 1
}
