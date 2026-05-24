# AI-Flow Self-Improve Quickstart

Este fluxo permite que o AI-Flow trabalhe na propria base (`.ai-flow/**`) usando modelos locais.

## Comando inicial

```powershell
python .ai-flow\scripts\ai-flow.py --dry-run self-improve "Melhorar quality gate para detectar risco por pasta"
```

## O que o comando faz

1. Cria um `run_id` e pasta em `.ai-flow/artifacts/runs/<run_id>/`.
2. Gera plano inicial para auto aprimoramento.
3. Registra perfil de modelos locais ativos em `local-model-profile.json`.
4. Registra limites de escopo em `self-improve-scope.json`.
5. Executa checks em modo seguro (`--dry-run` ou `--quick`).

## Guardrails

- Escrita permitida apenas em `.ai-flow/**`.
- Sem commit automatico.
- Arquivos sensiveis exigem aprovacao humana.
- Toda execucao deixa trilha auditavel em artefatos.

## Artefatos esperados

- `request.md`
- `orchestrator.json`
- `plan.md`
- `local-model-profile.json`
- `self-improve-scope.json`
- `tests.md`
- `final-summary.md`
