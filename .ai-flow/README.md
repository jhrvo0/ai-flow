# AI-Flow — Fluxo de Desenvolvimento Assistido por IA

Estrutura reutilizável com múltiplos agentes para criação, revisão, correção e validação de código usando modelos locais via **Ollama** (provider principal, com fallback para LM Studio).

## Setup recomendado com Ollama

Provider padrão: **Ollama** (http://127.0.0.1:11434/v1). LM Studio mantido como fallback opcional.

### 1. Instalar Ollama

Baixe e instale o [Ollama](https://ollama.ai). Verifique a instalação:

```powershell
ollama --version
```

### 2. Baixar os modelos recomendados

Para máquina com **16 GB RAM e sem GPU**, baixe estes modelos (leves + 7B para coding):

```powershell
ollama pull llama3.2:3b
ollama pull phi4-mini:3.8b
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b
```

> Modelos 14B+ (como `qwen2.5-coder:14b`) **não são recomendados** para 16 GB sem GPU — podem causar swap excessivo.

### 3. Validar configuração

```powershell
python .ai-flow\scripts\ai-flow.py validate-config
```

### 4. Iniciar o servidor local da API

```powershell
python .ai-flow\server.py
```

### 5. Abrir o dashboard

```powershell
python .ai-flow\scripts\ai-flow.py dashboard
```

## Fluxo mínimo recomendado

```powershell
python .ai-flow\server.py
python .ai-flow\scripts\ai-flow.py dashboard
```

Depois:

1. verificar o status de Server e Ollama na barra superior;
2. selecionar o projeto ativo;
3. checar providers e modelos locais;
4. abrir um arquivo do projeto;
5. usar o Composer com contexto explícito;
6. revisar e aplicar o patch proposto;
7. rodar o Quality Gate e abrir o report.

## Pré-requisitos

- **Git** — para rastrear alterações via `git diff`
- **Python 3** — para executar scripts (sem dependências externas)
- **Ollama** rodando (`ollama serve` ou aplicativo aberto)

### Modelos recomendados (setup típico)

| Agente | Modelo Ollama | Motivo |
|--------|---------------|--------|
| **Planner/Architect** | `phi4-mini:3.8b` | Leve, análise geral |
| **Coder** | `qwen2.5-coder:7b` | Melhor para código |
| **Reviewer/Security** | `qwen2.5-coder:7b` | Rigor na detecção de bugs |
| **Tester** | `llama3.2:3b` | Rápido para validação |
| **Docs/Summarizer** | `llama3.2:3b` | Rápido para resumos |
| **Patch Applier** | `qwen2.5-coder:3b` | Leve e rápido |
| **Memory/Orchestrator** | `llama3.2:3b` | Tarefas leves |

## Dashboard central (entry point)

Abra o **dashboard.html** para ver **todos os seus projetos** em um só lugar:

```powershell
.ai-flow\dashboard.ps1                          # atalho
.ai-flow\scripts\run-dashboard.ps1              # ou
python .ai-flow\scripts\generate-dashboard.py   # ou só abrir o HTML
```

O dashboard:
- Escaneia a pasta atual e subpastas procurando repositórios Git
- Mostra **cards de projetos** com: nome, branch, status, último commit
- Destaque visual para projetos com **alterações pendentes**
- **Links diretos** para: abrir projeto, contexto, quality gate, workflows e relatórios recentes
- **Botões "Gerar"** para rodar o context map e quality gate de cada projeto
- **Busca e filtros** (todos / com alterações / com AI-Flow)
- Projetos com `.ai-flow/` recebem badge **⚡ AI-Flow**
- O card de cada projeto mostra **artefatos recentes** e sinais de relatórios gerados

## CLI central do AI-Flow

Use o entry point principal para operar o fluxo sem depender apenas de prompts e documentação:

```powershell
python .ai-flow\scripts\ai-flow.py status
python .ai-flow\scripts\ai-flow.py context
python .ai-flow\scripts\ai-flow.py quality
python .ai-flow\scripts\ai-flow.py dashboard
python .ai-flow\scripts\ai-flow.py init-task "minha-tarefa"
python .ai-flow\scripts\ai-flow.py list-tasks
python .ai-flow\scripts\ai-flow.py show-config
python .ai-flow\scripts\ai-flow.py validate-config
```

O comando `init-task` cria a pasta de artefatos da tarefa e os arquivos-base para acompanhar contexto, estado e qualidade.

## Mapas individuais de cada projeto

### 1. Mapa do fluxo de agentes (estático)

```powershell
.ai-flow\reports\context-map.html
```

Pipeline dos agentes, cards com modelo/função/restrições, diagrama SVG, regras de segurança.

### 2. Mapa do projeto (dinâmico — gerado por script)

```powershell
python .ai-flow\scripts\generate-context-map.py
.ai-flow\scripts\generate-context-map.ps1
```

Contém: árvore de diretórios, arquivos modificados destacados, branch, commits, status Git, arquitetura, quadro de tarefas Kanban.
Também passa a destacar stack provável, manifestos, scripts, testes, CI/CD, Docker e riscos do contexto atual.

## Estrutura

```
.ai-flow/
  README.md              # Este arquivo
  config.example.json    # Configuração dos modelos e comandos
  dashboard.ps1          # Atalho: abre o dashboard central
  dashboard.html         # Dashboard central (gerado) — ENTRY POINT
  agents/
    00-orchestrator.md    # Orquestração do fluxo
    01-context-engineer.md  # Coleta e organiza contexto
    02-planner.md         # Planejamento
    03-architect.md       # Arquitetura
    04-coder.md           # Implementação
    05-patch-applier.md   # Aplicação de patches
    06-reviewer.md        # Revisão de qualidade
    07-tester.md          # Validação e testes
    08-security.md        # Revisão de segurança
    09-docs-commit.md     # Documentação e commit
    10-memory.md          # Atualização de memória
    planner.md            # Alias legado
    coder.md              # Alias legado
    reviewer-quality-gate.md  # Alias legado
    tester.md             # Alias legado
    docs-commit.md        # Alias legado
  workflows/
    feature-flow.md      # Fluxo completo para nova funcionalidade
    bugfix-flow.md       # Fluxo para correção de bugs
    review-flow.md       # Fluxo apenas para revisão
  artifacts/
    current-task.json     # Tarefa ativa e ponteiros de contexto
    task-state.json       # Estado da tarefa em andamento
  scripts/
    quality-gate.py               # Análise estática do diff (gera HTML)
    run-quality-gate.ps1          # Atalho: quality gate + navegador
    generate-context-map.py       # Escaneia projeto e gera mapa visual
    generate-context-map.ps1      # Atalho: context map + navegador
    generate-dashboard.py         # Escaneia projetos e gera dashboard
    run-dashboard.ps1             # Atalho: dashboard + navegador
  reports/
    quality-gate.html             # Relatório de qualidade (gerado)
    context-map.html              # Mapa estático do fluxo de agentes
    project-context.html          # Mapa dinâmico do projeto (gerado)
```

## Ciclo completo (feature)

```powershell
# 1. Criar branch
git checkout -b feature/minha-feature

# 2. Pedir planejamento (copiar prompt do planner.md para o chat)
#    -> O Planner analisa e propõe um plano

# 3. Aprovar o plano manualmente

# 4. Pedir implementação (copiar prompt do coder.md para o chat)
#    -> O Coder implementa o plano aprovado

# 5. Rodar quality gate
python .ai-flow\scripts\quality-gate.py
#   ou
.ai-flow\scripts\run-quality-gate.ps1

# 6. Revisar relatório + git diff pelo Reviewer
#    (copiar prompt do reviewer-quality-gate.md e colar o diff)

# 7. Se houver problemas, reenviar ao Coder com as correções
#    Repetir passos 5-7 até qualidade aceitável

# 8. Rodar testes
#    (copiar prompt do tester.md)

# 9. Gerar mensagem de commit
#    (copiar prompt do docs-commit.md)

# 10. Commit manual (NUNCA automático)
git add .
git diff --cached   # revisar antes
git commit -m "feat(escopo): descrição"
```

## Como rodar o Quality Gate

```powershell
# Opção 1: direto
python .ai-flow\scripts\quality-gate.py

# Opção 2: atalho (roda e abre o navegador)
.ai-flow\scripts\run-quality-gate.ps1
```

O relatório HTML será gerado em `.ai-flow/reports/quality-gate.html` com:

- Nota geral de 0 a 10
- Resumo de arquivos e linhas alteradas
- Alertas críticos, importantes e melhorias
- Comandos perigosos, dependências novas e ausência de testes
- Preview do diff
- Prompt pronto para copiar e reenviar ao Coder

## Primeiro prompt para iniciar uma feature

```
Atue como **Planner** (arquivo .ai-flow/agents/planner.md).

Preciso implementar a seguinte funcionalidade no projeto:

[DESCREVA A FUNCIONALIDADE AQUI]

Analise o projeto, identifique os arquivos afetados,
avalie riscos e proponha um plano de implementação detalhado.
Nao edite nenhum arquivo.
```

## Regras de segurança (aplicam-se a todos os agentes)

| Regra | Descrição |
|-------|-----------|
| **Sem commit automático** | Nenhum agente faz commit. O commit é sempre manual. |
| **Arquivos grandes (>100KB)** | Nunca apagar sem confirmação explícita. |
| **Configs sensíveis** | Nunca alterar `.env`, migrations, `docker-compose.yml`, configs de CI/CD sem perguntar. |
| **Escopo restrito** | Nunca modificar arquivos fora do escopo sem justificar por escrito. |
| **Diff visível** | Sempre mostrar o diff/resumo antes da etapa final. |
| **Mudanças pequenas** | Sempre priorizar mudanças pequenas e revisáveis. |
| **Problema único** | Sempre preferir corrigir apenas o problema pedido, sem refatorações extras. |
| **Secrets** | Nunca expor tokens, senhas ou chaves no código ou no diff. |

## Fluxos disponíveis

- **feature-flow.md** — Criar nova funcionalidade (10 etapas)
- **bugfix-flow.md** — Corrigir bug (8 etapas, minimalista)
- **review-flow.md** — Apenas revisar código existente (3 etapas)

## Limitações

- O quality gate faz análise **estática simples** — não substitui uma revisão humana profunda
- A detecção de funções longas é aproximada (baseada em chaves `{}`)
- A detecção de duplicação é por linha exata, não por similaridade semântica
- Modelos locais menores (<7B) podem cometer erros em tarefas muito complexas
- O fluxo assume que o projeto usa Git — sem Git o quality gate não funciona
- O script quality-gate.py não detecta todos os padrões de segurança; é uma camada inicial
