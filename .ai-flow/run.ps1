# .ai-flow/run.ps1
# Inicia o servidor AI-Flow e abre o dashboard no navegador

$ErrorActionPreference = "Stop"
$ServerScript = Join-Path $PSScriptRoot "server.py"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Flow: Iniciando servidor..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERRO] Python nao encontrado." -ForegroundColor Red
    exit 1
}

python $ServerScript
