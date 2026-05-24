# Guia de Uso de Modelos e Convenções Multiagente

## Cadeia de Trabalho

```
Usuário → Planner → Coder → Reviewer → Tester → Docs & Commit
                ↑__________|______________|        |
                |         (feedback loop)          |
                └──────────────────────────────────┘
```

- **Planner**: Analisa e planeja. Nunca edita código.
- **Coder**: Implementa baseado no plano. Único que edita código.
- **Reviewer**: Valida o código do Coder contra o plano. Nunca edita.
- **Tester**: Executa verificações automatizadas. Nunca edita sem autorização.
- **Docs & Commit**: Gera documentação e mensagens de commit. Nunca edita código.

## Modelos Recomendados por Papel

| Agente | Modelo Principal | Provider | Temp | Fallback |
|--------|-----------------|----------|------|----------|
| Planner | `huihui-qwen3-4b-instruct-2507` | LM Studio | 0.3 | `qwen2.5-coder-7b-instruct` |
| Coder | `qwen2.5-coder-7b-instruct` | LM Studio/Ollama | 0.2 | `qwen2.5-coder-7b-instruct` |
| Reviewer | `qwen2.5-coder-7b-instruct` | LM Studio/Ollama | 0.1 | `qwen2.5-coder-7b-instruct` |
| Tester | `llama-3.2-3b-instruct` | LM Studio/Ollama | 0.2 | `huihui-qwen3-4b-instruct-2507` |
| Docs & Commit | `llama-3.2-3b-instruct` | LM Studio/Ollama | 0.4 | `llama-3.2-3b-instruct` |

## Regras Compartilhadas

- **Nenhum agente faz commit automático.** Commits são manuais e deliberados.
- **Nenhum agente edita arquivos fora do escopo definido.**
- **Sempre verifique `git diff` antes de começar e depois de concluir.**
- **Arquivos bloqueados** (não alterar sem permissão explícita): `migrations/`, `.env*`, `docker-compose.yml`, `Dockerfile`, `secrets/`, configs de CI/CD.
- **Nunca exponha tokens, chaves ou segredos** em saídas, logs ou arquivos.

## Comandos de Verificação

| Comando | Finalidade |
|---------|-----------|
| `npm test` / `npx vitest run` | Testes unitários |
| `npm run lint` / `npx eslint .` | Linting |
| `npx tsc --noEmit` | Typecheck |
| `npm run build` | Build |
| `npx prettier --check .` | Formatação |