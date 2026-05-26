# AI-Flow — Contexto e Prompt Robusto para Auditoria Profunda

## Contexto do último commit analisado

Commit mais recente analisado: `f33dc84b824107cdab329b1118a4ddce321f8920`

Mensagem resumida:
`Switch default to Ollama; UI & model registry updates`

O commit tornou o Ollama o provider padrão, atualizou nomes de modelos para identificadores reais do Ollama, expandiu o mapeamento por agente, atualizou o registry de modelos para v2.0 e fez melhorias visuais no dashboard, incluindo:
- setup recomendado com Ollama no README;
- config.example.json com `default_provider: "ollama"`;
- modelos como `llama3.2:3b`, `phi4-mini:3.8b`, `qwen2.5-coder:3b` e `qwen2.5-coder:7b`;
- hover glow por cor de agente;
- botão de word wrap no editor;
- ajustes no Monaco Editor;
- formatação visual do console;
- destaque de tokens de status como `[OK]`, `[ERRO]`, `[WARN]`;
- syntax highlight em blocos de código;
- badges de chat com ícones;
- atualização de reports e scripts para alinhar com Ollama.

## Diagnóstico inicial

O projeto evoluiu bastante, mas agora precisa de uma auditoria profunda de produto, código e interface.

Pontos positivos:
- O projeto já tem uma direção mais clara: Ollama-first.
- A config agora usa nomes reais do Ollama.
- O dashboard está visualmente mais rico.
- Existe CLI central.
- Existe server local.
- Existe execução de agentes.
- Existe estrutura de artefatos.
- Existe registry de modelos.
- Existe quality gate.

Riscos e problemas prováveis:
- Alguns botões podem ter sido adicionados sem função implementada.
- Alguns fluxos visuais podem existir só na interface, mas sem backend real.
- O dashboard pode ter ações duplicadas ou confusas.
- O servidor pode expor endpoints que não são usados ou botões que chamam endpoints inexistentes.
- O AI-Flow Canvas pode estar mais visual do que funcional.
- O botão de Word Wrap precisa ser validado porque há `onclick="toggleWordWrap()"`, mas é necessário confirmar se a função existe e se funciona no Monaco e no textarea fallback.
- O botão de Commit 1-Click existe e deve ser avaliado com cuidado, porque pode ser perigoso para o fluxo do AI-Flow se fizer commit sem confirmação forte.
- A separação entre artefatos de task, runs legados e reports ainda pode estar confusa.
- O projeto pode ter muitas partes boas, mas sem uma jornada central clara para o usuário.

## Objetivo do próximo ciclo

Fazer uma melhoria completa do AI-Flow, tratando-o como um produto real:

1. auditar todos os botões;
2. auditar todos os endpoints;
3. auditar todos os scripts;
4. auditar todos os fluxos;
5. corrigir botões quebrados;
6. remover ou desativar partes sem sentido;
7. consolidar Ollama-first;
8. melhorar UX do dashboard;
9. melhorar segurança;
10. melhorar artefatos;
11. melhorar qualidade visual;
12. melhorar documentação;
13. criar testes/checklists para impedir regressões.

---

# PROMPT ROBUSTO PARA CODEX / GPT-5.5 XHIGH

Você está trabalhando no repositório `ai-flow`.

Use GPT-5.5 com reasoning effort xhigh.

Este trabalho pode demorar bastante. Faça uma auditoria profunda, não superficial. O objetivo é melhorar o projeto em todos os aspectos: funcionamento real, UX, visual, arquitetura, segurança, organização, consistência, documentação e testes.

## Contexto geral

O AI-Flow é uma ferramenta local de desenvolvimento assistido por IA com múltiplos agentes. Ele deve funcionar como um workspace local com:

- Dashboard visual;
- CLI central;
- Servidor local;
- Execução de agentes com modelos locais;
- Provider principal Ollama;
- LM Studio apenas como fallback opcional;
- Quality Gate;
- Context Map;
- Artefatos por tarefa;
- Agentes com papéis definidos;
- Workflows reutilizáveis;
- Reports;
- Histórico/snapshots;
- Editor integrado;
- AI-Flow Canvas;
- Terminal/logs;
- Integração com Git.

O projeto está em evolução rápida e possui partes que podem estar incompletas, botões que não funcionam, ações duplicadas, fluxos sem sentido ou UI que promete mais do que entrega.

Sua missão é transformar isso em um produto mais coerente, funcional e confiável.

## Regras absolutas

- Não faça commit.
- Não abra PR.
- Não apague suporte a LM Studio; apenas mantenha como secundário.
- Não remova recursos sem justificar.
- Não altere arquivos fora de `.ai-flow/` sem necessidade real.
- Não faça mudanças gigantes sem separar por etapas.
- Não esconda problemas encontrados.
- Não ignore botões quebrados.
- Não deixe UI prometendo algo que não funciona.
- Não deixe endpoints mortos sem documentar ou remover.
- Não deixe ações perigosas sem confirmação.
- Não exponha secrets.
- Não altere `.env`, Dockerfile, docker-compose, CI/CD ou migrations sem confirmação explícita.
- Priorize funcionamento real em vez de só aparência.

## Fase 1 — Auditoria completa do último estado do projeto

Antes de codar, leia e analise:

- `.ai-flow/README.md`
- `.ai-flow/config.example.json`
- `.ai-flow/model-registry.example.json`
- `.ai-flow/dashboard.html`
- `.ai-flow/server.py`
- `.ai-flow/scripts/ai-flow.py`
- `.ai-flow/scripts/llm_client.py`
- `.ai-flow/scripts/run-agent.py`
- `.ai-flow/scripts/generate-dashboard.py`
- `.ai-flow/scripts/generate-context-map.py`
- `.ai-flow/scripts/quality-gate.py`
- `.ai-flow/scripts/check-models.py`, se existir
- `.ai-flow/scripts/select-model.py`, se existir
- `.ai-flow/agents/*.md`
- `.ai-flow/workflows/*`
- `.ai-flow/reports/*`
- testes existentes

Também rode comandos de inspeção seguros:

```powershell
git status --short
git log -3 --oneline
python .ai-flow\scripts\ai-flow.py status
python .ai-flow\scripts\ai-flow.py show-config
python .ai-flow\scripts\ai-flow.py validate-config
python .ai-flow\scripts\run-agent.py --list-agents
```

Se algum comando falhar, registre o erro e corrija se for problema do projeto.

## Fase 2 — Criar relatório de auditoria

Crie ou atualize:

`.ai-flow/reports/full-product-audit.md`

Esse relatório deve conter:

1. resumo do estado atual;
2. o que funciona;
3. o que está quebrado;
4. botões sem função;
5. botões com função perigosa;
6. endpoints sem uso;
7. endpoints chamados por UI mas não implementados;
8. scripts duplicados ou confusos;
9. partes visuais sem utilidade real;
10. inconsistências entre README/config/scripts/dashboard;
11. problemas de fluxo;
12. problemas de UX;
13. problemas de segurança;
14. problemas de arquitetura;
15. plano de correção priorizado.

## Fase 3 — Matriz de botões e ações

Faça uma varredura completa no `dashboard.html`.

Crie:

`.ai-flow/reports/dashboard-button-matrix.md`

Para cada botão, link, ação, `onclick`, listener ou comando da UI, registre:

- texto/ícone do botão;
- localização aproximada;
- função chamada;
- endpoint chamado, se houver;
- status: funcionando / quebrado / perigoso / duplicado / sem sentido / precisa validar;
- ação recomendada;
- prioridade.

Exemplos de verificações obrigatórias:
- `toggleWordWrap()`;
- `commitChanges()`;
- `checkModels()`;
- `openRunAgentDialog()`;
- `runAgentLive()`;
- botões de Quality Gate;
- botões de Context Map;
- botões de Reports;
- botões de salvar arquivo;
- botões de undo/redo/history;
- botões do AI-Flow Canvas;
- botões de executar workflow visual;
- botões de abrir projeto;
- botões de adicionar/remover projeto;
- botões relacionados a agentes/modelos;
- botões de terminal;
- botões de snapshots;
- botões que fazem chamadas a `/api/*`.

Depois de gerar a matriz, corrija os botões quebrados ou torne-os explicitamente desabilitados com tooltip explicando “em desenvolvimento”.

## Fase 4 — Matriz de endpoints

Analise `server.py` e crie:

`.ai-flow/reports/api-endpoint-matrix.md`

Para cada endpoint `/api/...`, registre:

- método GET/POST;
- payload esperado;
- quem chama;
- se existe botão/UI correspondente;
- se o endpoint funciona;
- riscos;
- validações ausentes;
- resposta de erro atual;
- melhoria necessária.

Corrija:
- endpoints sem validação;
- respostas inconsistentes;
- mensagens ruins;
- ações perigosas;
- erros silenciosos;
- chamadas que quebram se faltar parâmetro;
- chamadas que assumem arquivo/projeto existente.

## Fase 5 — Consolidar Ollama-first de verdade

O projeto já começou isso no último commit, mas agora valide profundamente.

Garanta que:

- `config.example.json` usa `ollama` como provider padrão;
- os nomes dos modelos são reais do Ollama;
- `model_for_tester`, `model_for_docs` e `model_for_summary` existem;
- cada agente tem modelo definido;
- LM Studio aparece apenas como fallback;
- `llm_client.py`, `server.py`, `run-agent.py` e `ai-flow.py` usam Ollama por padrão;
- erros de modelo ausente sugerem `ollama pull <modelo>`;
- erros de servidor offline sugerem iniciar Ollama;
- `validate-config` mostra modelos instalados e faltantes;
- dashboard mostra status do Ollama;
- dashboard mostra comandos de instalação/pull quando necessário.

Modelos recomendados:
- `llama3.2:3b`
- `phi4-mini:3.8b`
- `qwen2.5-coder:3b`
- `qwen2.5-coder:7b`
- `gemma3:4b` como alternativa opcional.

## Fase 6 — Melhorar a jornada principal do usuário

Defina uma jornada clara no dashboard:

1. selecionar projeto;
2. verificar Ollama/modelos;
3. criar ou selecionar task;
4. gerar contexto;
5. executar Planner;
6. revisar plano;
7. executar Coder;
8. aplicar patch com preview;
9. rodar Quality Gate;
10. executar Reviewer;
11. executar Tester;
12. gerar Docs/Commit;
13. atualizar Memory.

A UI deve deixar claro:
- onde o usuário está;
- qual é a próxima ação;
- qual agente será executado;
- qual modelo será usado;
- onde o artefato será salvo;
- se há erro;
- se uma ação ainda não está implementada.

## Fase 7 — Melhorias visuais do dashboard

Melhore o visual sem mudar completamente a identidade.

Prioridades visuais:

- painel superior de status do runtime;
- cards de projeto mais limpos;
- badges mais úteis e menos poluídos;
- separação clara entre “projeto”, “task”, “agente”, “modelo” e “reports”;
- botão principal por contexto;
- estados empty/loading/error/success;
- modal real para executar agente, sem `prompt()` nativo do navegador;
- modal real para checar modelos;
- melhoria da área de console;
- melhoria do canvas para mostrar se é funcional ou apenas visual;
- tooltips para ações perigosas;
- desabilitar ações sem projeto selecionado;
- desabilitar ações sem servidor online;
- desabilitar ações que dependem de Ollama se Ollama estiver offline;
- evitar botões espalhados sem hierarquia.

## Fase 8 — Corrigir botões quebrados e partes sem sentido

Para cada item quebrado encontrado:

- implemente a função se fizer sentido;
- conecte ao endpoint correto;
- crie endpoint se necessário;
- ou remova/desabilite se não fizer sentido agora.

Atenção especial:
- Se existe botão de Word Wrap, ele deve funcionar no Monaco e no textarea fallback.
- Se existe botão de Commit 1-Click, ele deve exigir confirmação forte e mostrar diff antes.
- Se existe Executar Agente, deve usar modal próprio e salvar artefato.
- Se existe Canvas, deve ficar claro se ele executa fluxo real ou simula.
- Se existe botão de Reports, deve abrir arquivos reais ou avisar que ainda não existem.
- Se existe Quality Gate, deve atualizar task-state.
- Se existe Context Map, deve atualizar task-state.
- Se existe botão de modelos, deve mostrar modelos instalados e faltantes.

## Fase 9 — Segurança e ações perigosas

Audite principalmente:

- commit automático;
- escrita de arquivos;
- aplicação de patches;
- execução de comandos no terminal;
- endpoints que recebem caminho de arquivo;
- endpoints que escrevem em disco;
- CORS aberto;
- comandos perigosos;
- path traversal;
- edição fora do projeto;
- deleção de arquivos;
- snapshots/undo;
- exposição de arquivos sensíveis.

Melhore:
- validação de caminhos;
- confirmação para ações destrutivas;
- bloqueio de `.env`, secrets, credenciais;
- mensagens claras;
- logs sem dados sensíveis;
- limites de tamanho para leitura/escrita.

## Fase 10 — Artefatos e task-state

Organize o fluxo de artefatos.

Quando houver task ativa:
- respostas de agente devem ir para a pasta da task;
- quality gate deve copiar para a task;
- context map deve referenciar a task;
- task-state deve ser atualizado;
- dashboard deve mostrar a task ativa;
- runs legados devem continuar existindo, mas não ser o caminho principal.

Estrutura desejada:

```txt
.ai-flow/artifacts/YYYY-MM-DD-nome-da-task/
├── 01-context.md
├── 02-plan.md
├── 03-coder-summary.md
├── 04-quality-gate.html
├── 05-review.md
├── 06-tests.md
├── 07-docs-commit.md
├── task-state.json
└── runs/
    ├── planner-response.md
    ├── coder-response.md
    └── reviewer-response.md
```

## Fase 11 — Refatoração controlada

Refatore apenas onde trouxer ganho real.

Prioridades:
- separar funções gigantes do dashboard;
- reduzir duplicação de funções de chat/mensagens;
- centralizar chamada de API;
- centralizar resolução de modelos;
- centralizar rendering de toast/console/status;
- separar lógica de UI e lógica de dados;
- melhorar nomes;
- remover código morto;
- manter compatibilidade.

Se uma refatoração for grande demais, documente como próximo passo em vez de misturar tudo.

## Fase 12 — Testes e validação

Crie ou atualize testes simples, sem dependências desnecessárias.

Cobrir:
- validação de config;
- provider padrão Ollama;
- resolução de modelos por agente;
- parsing de agentes;
- listagem de modelos;
- endpoint matrix básico;
- botões com handlers existentes;
- existência de funções chamadas em `onclick`;
- task-state;
- geração de artefatos;
- quality gate;
- context map.

Crie também:

`.ai-flow/reports/manual-test-checklist.md`

Inclua checklist manual com:
- abrir dashboard;
- verificar servidor online;
- verificar Ollama offline;
- verificar Ollama online;
- listar modelos;
- modelo faltando;
- criar task;
- gerar contexto;
- rodar Planner;
- rodar Coder;
- rodar Quality Gate;
- abrir reports;
- salvar arquivo;
- undo/redo;
- history;
- word wrap;
- canvas;
- executar fluxo visual;
- bloquear commit perigoso;
- abrir artefatos recentes.

## Fase 13 — Documentação final

Atualize README com:

- visão geral real do projeto;
- setup Ollama-first;
- comandos de instalação;
- modelos recomendados;
- como abrir dashboard;
- como usar CLI;
- como criar task;
- como executar agente;
- como usar reports;
- como interpretar artefatos;
- limitações atuais;
- recursos ainda experimentais;
- ações perigosas e proteções.

## Critérios de aceite

A entrega só deve ser considerada boa se:

1. Todos os botões principais forem auditados.
2. Botões quebrados forem corrigidos, removidos ou desabilitados.
3. Todos os endpoints forem auditados.
4. Dashboard tiver uma jornada principal clara.
5. Ollama-first estiver consistente.
6. LM Studio continuar como fallback.
7. `validate-config` for útil de verdade.
8. `run-agent.py` salvar artefatos no lugar certo.
9. Task ativa aparecer de forma compreensível.
10. Quality Gate e Context Map continuarem funcionando.
11. Ações perigosas exigirem confirmação forte.
12. README explicar o uso real.
13. Testes ou checklists forem atualizados.
14. O visual ficar mais coeso e menos cheio de botões soltos.
15. O projeto continuar local-first e simples de rodar no Windows.

## Ordem recomendada de execução

1. Auditoria e relatórios.
2. Corrigir bugs óbvios de botões/funções.
3. Corrigir inconsistências Ollama.
4. Melhorar dashboard/status/modelos.
5. Melhorar execução de agente.
6. Melhorar artefatos/task-state.
7. Melhorar segurança.
8. Refatorar duplicações pequenas.
9. Atualizar README/checklists.
10. Rodar validações finais.

## Resposta final esperada

Ao terminar, responda com:

```txt
## Resumo geral
[explicação curta]

## Arquivos alterados
- arquivo — motivo

## Botões corrigidos
- botão — problema — solução

## Botões desabilitados/removidos
- botão — motivo

## Endpoints corrigidos
- endpoint — problema — solução

## Melhorias visuais
- ...

## Melhorias de fluxo
- ...

## Melhorias de segurança
- ...

## Testes executados
- comando — resultado

## Checklists criados/atualizados
- arquivo

## Limitações restantes
- ...

## Próximos passos recomendados
- ...
```

Não faça commit.
Não abra PR.
Não pare na primeira melhoria visual: o objetivo é tornar o AI-Flow mais funcional, coerente e confiável.
