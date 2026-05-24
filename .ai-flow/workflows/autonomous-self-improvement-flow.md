# Workflow: Autonomous Self-Improvement Flow

Objetivo: permitir que o AI-Flow evolua a si mesmo usando apenas modelos locais, com trilha auditavel e aprovacao humana antes de qualquer escrita sensivel.

1. Orchestrator classifica pedido como `self-improve` e calcula risco.
2. Context Engineer analisa:
   - scripts em `.ai-flow/scripts/`
   - agentes em `.ai-flow/agents/`
   - workflows em `.ai-flow/workflows/`
   - config e memoria.
3. Planner gera:
   - plano humano
   - plano executavel por fases pequenas
   - checklist de rollback.
4. Architect valida acoplamento e evita overengineering.
5. Aprovacao humana obrigatoria para implementar.
6. Coder propõe patch focado somente em `.ai-flow/**`.
7. Patch Applier bloqueia arquivos sensiveis sem confirmacao explicita.
8. Reviewer + Security revisam regressao, safety e riscos.
9. Tester executa checks do proprio AI-Flow.
10. Docs/Commit gera changelog e resumo tecnico.
11. Memory registra decisao e aprendizado do ciclo.

Guardrails:
- Sem commit automatico.
- Sem alteracoes fora de `.ai-flow/**` neste modo.
- Sem alteracao em `.env`, CI/CD, docker, migrations sem confirmacao humana.
- Todo run gera artefatos em `.ai-flow/artifacts/runs/<run_id>/`.
