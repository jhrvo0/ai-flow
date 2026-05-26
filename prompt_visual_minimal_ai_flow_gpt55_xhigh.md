Você está trabalhando no repositório local `ai-flow`.

Use GPT-5.5 com reasoning effort xhigh.

Objetivo deste ciclo:
Fazer uma melhoria visual e funcional profunda do AI-Flow Dashboard, deixando a interface mais minimalista, limpa, focada e profissional, com uma experiência inspirada em ferramentas modernas de desenvolvimento agentic como Codex, Cursor e Antigravity — sem copiar marcas, layouts proprietários ou identidade visual específica. Use apenas como referência de princípios: foco, clareza, poucos elementos visíveis por vez, ótima hierarquia, comandos rápidos, painéis bem organizados e aparência de editor moderno.

Contexto:
O último commit adicionou muitos recursos funcionais importantes:
- modais novos para Run Agent, Self-Improve, Confirm Commit, Canvas Flow Goal, Models Status e prompts/confirms reutilizáveis;
- melhorias no AI-Flow Canvas;
- fluxo de confirmação de commit;
- UI para checagem de modelos locais;
- word-wrap toggle;
- restore de snapshots;
- validações e melhorias de UX;
- server.py com validação de caminhos, proteção em operações de arquivo/projeto/Git, endpoint de restore e atualização de task-state.

Isso foi bom funcionalmente, mas a interface pode ter ficado mais carregada, cheia de botões, estilos inline, modais diferentes entre si, badges demais, brilho demais e hierarquia visual confusa.

A tarefa agora NÃO é adicionar mais recursos grandes. A tarefa é lapidar o produto.

## Antes de alterar qualquer coisa

1. Analise o último commit.
2. Leia:
   - `.ai-flow/dashboard.html`
   - `.ai-flow/server.py`
   - `.ai-flow/README.md`
   - `.ai-flow/config.example.json`
   - `.ai-flow/scripts/ai-flow.py`
   - `.ai-flow/scripts/run-agent.py`
   - `.ai-flow/scripts/llm_client.py`
   - `.ai-flow/reports/full-product-audit.md`, se existir
   - `.ai-flow/reports/dashboard-button-matrix.md`, se existir
   - `.ai-flow/reports/api-endpoint-matrix.md`, se existir
3. Rode apenas comandos seguros de diagnóstico:
   - `git status --short`
   - `python .ai-flow\scripts\ai-flow.py status`
   - `python .ai-flow\scripts\ai-flow.py validate-config`
4. Identifique quais mudanças do último commit melhoraram funcionalmente o projeto e quais deixaram a UI mais complexa.

## Entregável de diagnóstico visual

Crie ou atualize:

`.ai-flow/reports/dashboard-visual-audit.md`

O relatório deve conter:

1. resumo do estado visual atual;
2. problemas de excesso visual;
3. botões redundantes;
4. áreas que competem por atenção;
5. modais inconsistentes;
6. excesso de estilos inline;
7. problemas de hierarquia;
8. problemas de densidade;
9. problemas de UX no fluxo principal;
10. oportunidades de simplificação;
11. plano visual de melhoria;
12. checklist de aceitação visual.

## Direção visual desejada

A interface deve parecer:

- minimalista;
- escura;
- técnica;
- discreta;
- focada em produtividade;
- com poucos acentos de cor;
- sem excesso de glow;
- sem excesso de badges;
- sem excesso de botões visíveis ao mesmo tempo;
- com layout de workspace/editor moderno;
- com boa hierarquia entre sidebar, editor, agente/chat e terminal;
- com estados claros: idle, loading, success, warning, error.

Use como referência conceitual:
- Command center de editor moderno;
- Sidebar compacta;
- Painéis colapsáveis;
- Modais limpos;
- Botões com prioridade clara;
- Toasts discretos;
- Paleta neutra com um acento principal;
- Tipografia e espaçamento consistentes;
- “menos UI, mais foco”.

Não copie visual específico de nenhuma ferramenta. Busque a sensação: simples, moderno, agentic, profissional.

## Regras visuais

1. Reduzir estilos inline sempre que possível.
2. Criar/organizar classes CSS reutilizáveis.
3. Centralizar tokens visuais:
   - cores;
   - radius;
   - sombras;
   - spacing;
   - fonte;
   - bordas;
   - estados.
4. Reduzir glow agressivo.
5. Reduzir variação de cores.
6. Diminuir poluição de badges.
7. Priorizar cinzas, preto, bordas suaves e um acento principal.
8. Usar cor forte apenas para status ou ação primária.
9. Evitar botões coloridos demais.
10. Tornar ações secundárias mais discretas.
11. Tornar ações perigosas claramente marcadas, mas sem exagero.
12. Melhorar responsividade.
13. Garantir legibilidade em telas menores.

## Regras funcionais

Não quebre recursos adicionados no último commit.

Preservar e melhorar:
- Run Agent modal;
- Self-Improve modal;
- Confirm Commit modal;
- Canvas Flow Goal modal;
- Models Status modal;
- custom confirm/prompt;
- word-wrap toggle;
- snapshot restore;
- path validation do server;
- task-state update;
- Ollama-first;
- Quality Gate;
- Context Map;
- Canvas;
- terminal/logs;
- editor Monaco e textarea fallback.

Se algo estiver quebrado, corrija.
Se algo ainda não estiver pronto, deixe visualmente claro que está em beta ou desabilitado.

## Fase 1 — Reorganizar a hierarquia do dashboard

Melhore a estrutura visual para ter uma jornada principal clara:

1. topo: status compacto do runtime/projeto;
2. esquerda: explorer/projetos/git de forma limpa;
3. centro: editor/canvas;
4. direita ou inferior: agente/chat/terminal/reports;
5. ações primárias contextualizadas.

Evite deixar todos os botões sempre visíveis.

Sugestão:
- Uma ação primária por área.
- Ações secundárias em menu “mais”.
- Ações perigosas agrupadas e com confirmação.
- Botões que dependem de projeto/servidor/modelo devem ficar desabilitados até o pré-requisito existir.

## Fase 2 — Minimalizar header e cards

Melhore:
- header principal;
- cards de projeto;
- badges;
- botões de ação;
- status de Git;
- status do Ollama;
- seção de artefatos recentes.

Objetivo:
Cards mais calmos, menos brilhantes e mais fáceis de escanear.

Em cards de projeto, mostrar só:
- nome;
- branch;
- status Git;
- último commit;
- badges essenciais;
- 2 ou 3 ações principais.

Mover ações secundárias para menu ou área de detalhes.

## Fase 3 — Padronizar modais

Os modais adicionados no último commit são bons funcionalmente, mas devem ficar visualmente consistentes.

Padronize:
- largura;
- padding;
- header;
- footer;
- labels;
- inputs;
- textarea;
- checkbox;
- botões;
- estados de erro;
- estados loading;
- textos de ajuda.

Modais obrigatórios:
- Run Agent;
- Self-Improve;
- Confirm Commit;
- Canvas Flow Goal;
- Models Status;
- Custom Confirm;
- Custom Prompt.

Melhorias específicas:
- Run Agent deve mostrar agente, modelo automático, provider e pasta de artefato.
- Models Status deve mostrar faltantes de forma compacta e copiar comando `ollama pull`.
- Confirm Commit deve ser mais seguro e exigir revisão do diff/arquivos.
- Self-Improve deve deixar claro se é dry-run.
- Canvas Flow Goal deve explicar se executa fluxo real ou experimental.

## Fase 4 — Melhorar o painel de modelos

O painel de modelos deve ser minimalista e útil.

Mostrar:
- Provider ativo;
- Ollama HTTP: online/offline;
- Ollama CLI: disponível/indisponível;
- LM Studio: fallback online/offline;
- Modelos instalados;
- Modelos recomendados faltando;
- Comando de instalação por modelo.

Evitar cards grandes demais.
Usar lista compacta com status.

## Fase 5 — Melhorar o fluxo de agente

Melhore visualmente e funcionalmente o fluxo de execução de agente:

- mostrar agente selecionado;
- mostrar modelo que será usado;
- mostrar provider;
- mostrar se Git context será incluído;
- mostrar se será salvo em artifacts;
- mostrar output em área clara;
- mostrar loading enquanto executa;
- mostrar erro acionável;
- salvar e mostrar link do artefato gerado.

Evite prompt nativo do navegador.
Use modal próprio.

## Fase 6 — Melhorar console/terminal

O console deve ficar mais legível e menos chamativo.

Melhorias:
- timestamps discretos;
- `[OK]`, `[ERRO]`, `[WARN]` destacados com moderação;
- evitar excesso de text-shadow;
- diferenciar comando, resposta e erro;
- botão limpar discreto;
- auto-scroll controlado;
- opção de copiar saída;
- mensagens de erro com próxima ação sugerida.

## Fase 7 — Melhorar AI-Flow Canvas

O canvas deve ficar mais minimalista.

Melhorias:
- reduzir glow;
- melhorar nodes;
- melhorar conexões;
- melhorar empty state;
- melhorar toolbar;
- deixar claro se execução é real/experimental;
- reduzir textos longos;
- padronizar cores de agentes;
- usar legenda discreta;
- melhorar seleção/hover;
- melhorar inspector lateral.

Se o Canvas ainda for experimental, exibir badge discreto:
“experimental”.

## Fase 8 — Limpar CSS e estilos inline

Faça uma limpeza progressiva:

- mover estilos inline repetidos para classes;
- criar classes para modal, cards, badges, form controls, status dots, model rows, action groups;
- manter compatibilidade com HTML atual;
- não fazer uma reescrita total se não for necessário;
- remover CSS morto se tiver certeza.

Crie uma seção organizada no CSS do dashboard:
- tokens;
- layout;
- buttons;
- cards;
- modals;
- forms;
- badges/status;
- console;
- canvas;
- responsive.

## Fase 9 — Melhorias funcionais pequenas

Enquanto ajusta o visual, corrija pequenas falhas funcionais encontradas.

Obrigatório verificar:
- todos os botões principais ainda funcionam;
- `toggleWordWrap()` funciona;
- `checkModels()` funciona;
- `submitRunAgent()` funciona;
- `submitSelfImprove()` funciona;
- `submitCommit()` exige confirmação;
- restore de snapshot chama `/api/file/restore`;
- Canvas flow goal modal inicia o fluxo;
- menu de workflows salva/carrega;
- botões desabilitam quando não há projeto ativo;
- botões desabilitam quando server está offline;
- botões de agente/modelo desabilitam quando Ollama está offline.

## Fase 10 — Documentação visual

Atualize ou crie:

`.ai-flow/reports/visual-improvement-summary.md`

Inclua:
- antes/depois conceitual;
- decisões visuais;
- classes criadas;
- componentes padronizados;
- botões reorganizados;
- limitações restantes;
- próximas melhorias.

Se alterar README, adicione apenas uma seção curta:
“Dashboard e fluxo visual”.

## Critérios de aceite

A entrega só é boa se:

1. A UI ficar mais limpa e menos poluída.
2. Botões principais continuarem funcionando.
3. Modais ficarem consistentes.
4. Dashboard tiver hierarquia mais clara.
5. Menos ações ficarem espalhadas.
6. O visual parecer mais próximo de um editor agentic moderno.
7. Ollama-first continuar consistente.
8. Ações perigosas continuarem protegidas.
9. O canvas ficar mais discreto e compreensível.
10. O console ficar mais legível.
11. Não houver regressão funcional evidente.
12. Relatórios visuais forem criados/atualizados.

## Testes manuais obrigatórios

Crie/atualize checklist em:

`.ai-flow/reports/manual-visual-test-checklist.md`

Inclua testes para:
- abrir dashboard com server online;
- abrir dashboard com server offline;
- selecionar projeto;
- abrir Models Status;
- abrir Run Agent;
- executar agente em dry/simple task;
- abrir Self-Improve;
- confirmar commit sem mensagem;
- confirmar commit com mensagem;
- cancelar commit;
- alternar word wrap;
- abrir histórico/snapshots;
- restaurar snapshot;
- abrir canvas;
- salvar/carregar fluxo;
- executar canvas flow;
- abrir reports;
- testar responsividade.

## Ao final, responda com

1. resumo geral;
2. arquivos alterados;
3. melhorias visuais;
4. melhorias funcionais;
5. componentes/classes criadas;
6. botões ou áreas reorganizadas;
7. testes executados;
8. limitações restantes;
9. próximos passos.

Não faça commit.
Não abra PR.
Não transforme o dashboard em algo mais complexo.
A meta é: menos ruído, mais foco, visual mais minimalista, funcionamento mais claro.
