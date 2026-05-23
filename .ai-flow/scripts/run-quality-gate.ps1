# .ai-flow/scripts/run-quality-gate.ps1
# Executa o quality gate e abre o relatório no navegador padrão

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ScriptPath = Join-Path $PSScriptRoot "quality-gate.py"
$OutputPath = Join-Path $ProjectRoot ".ai-flow\reports\quality-gate.html"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI-Flow: Quality Gate" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar se Python está disponível
$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERRO] Python não encontrado. Instale Python 3 e tente novamente." -ForegroundColor Red
    exit 1
}

# Verificar se está em um repositório Git
$gitCheck = git rev-parse --is-inside-work-tree 2>$null
if (-not $gitCheck) {
    Write-Host "[ERRO] Diretório atual não é um repositório Git." -ForegroundColor Red
    Write-Host "  O quality gate precisa de um repositório Git para analisar o diff."
    exit 1
}

# Verificar se há mudanças
$hasChanges = git diff --quiet 2>$null
$hasStaged = git diff --cached --quiet 2>$null
$hasCommits = git log --oneline -1 2>$null

if ($hasChanges -and $hasStaged -and (-not $hasCommits)) {
    Write-Host "[AVISO] Nenhuma alteração detectada no working tree ou staged." -ForegroundColor Yellow
    Write-Host "  O quality gate analisará o último commit (se existir)." -ForegroundColor Yellow
}

Write-Host "[INFO] Executando quality-gate.py..." -ForegroundColor Gray

try {
    & $pythonCmd $ScriptPath
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0 -and (Test-Path $OutputPath)) {
        Write-Host ""
        Write-Host "[OK] Relatório gerado em:" -ForegroundColor Green
        Write-Host "     $OutputPath" -ForegroundColor White
        Write-Host ""
        Write-Host "[INFO] Abrindo no navegador..." -ForegroundColor Gray

        # Abrir no navegador padrão
        Start-Process $OutputPath

        Write-Host "[OK] Navegador aberto." -ForegroundColor Green
    }
    else {
        Write-Host ""
        Write-Host "[ERRO] Falha ao gerar relatório. Código de saída: $exitCode" -ForegroundColor Red
        exit $exitCode
    }
}
catch {
    Write-Host ""
    Write-Host "[ERRO] Exceção ao executar o script:" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Quality Gate concluído!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
