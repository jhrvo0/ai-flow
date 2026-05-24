# Workflow: Autonomous Feature Flow

1. Orchestrator classifica tarefa e risco.
2. Context Engineer gera contexto minimo.
3. Planner gera plano humano + executavel.
4. (Opcional) Architect valida plano em risco medio/alto.
5. Aprovacao humana obrigatoria.
6. Coder propõe patch.
7. Patch Applier aplica patch no escopo permitido.
8. Reviewer + Security Reviewer validam diff.
9. Tester roda validacoes.
10. Docs/Commit + Memory geram artefatos finais.
