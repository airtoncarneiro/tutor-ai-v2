# Backlog de implementação

Todas as tarefas estão pendentes. A documentação descreve o produto desejado; não comprova código, banco provisionado ou testes executados. Ordem de dependência obrigatória; nenhuma tarefa implica commit/deploy automático.

## T01 — Fundação e configuração

- [ ] Criar módulos conforme architecture.md, Python 3.12, ambiente reproduzível, dependências fixadas e lockfile.
- [ ] Configurar .env.example/.gitignore sem segredos e validação de limites/configuração.
- [ ] Implementar modelos fechados de runtime_contracts.md e ExerciseContract v2.
- [ ] Criar comandos documentados de instalação, migração, testes e abertura do Streamlit.
- Aceite: configuração ausente falha claramente; tipos/enum/campos desconhecidos são rejeitados; import e testes de modelos passam.
- Dependência: nenhuma. Requisitos: base de AC-01/04.

## T02 — Persistência e inicialização local

- [ ] Migrações versionadas, base/schemas/papéis e bootstrap idempotente.
- [ ] Repositories, singleton profile, unicidade de sessão ativa, FKs, conteúdo imutável e revisions.
- [ ] Docker Compose opcional em loopback e instruções para PostgreSQL instalado.
- [ ] Validar permissões reais com runner/evaluator, sem uso de superuser na aplicação.
- Aceite: duas aberturas concorrentes não criam duas sessões; credenciais runner não leem tutor_state nem dados ocultos; bootstrap não altera base alheia.
- Dependência: T01. AC-01/02/15.

## T03 — Política e estado pedagógico

- [ ] Árvores oficiais/provisórias, resolução de objetivo e declaração de conhecimento.
- [ ] Implementar A–F e todos os casos tabulados em tutor_prompt.md, incluindo prioridade global de intervenção sobre revisão.
- [ ] Implementar evidence-v1, independência, ajuda, regressão, aging e retenção com relógio injetável.
- [ ] Checkpoints deduplicados e troca/encerramento de objetivo preservando perfil.
- Aceite: nenhum estado válido seleciona ações concorrentes; falha isolada rebaixa confiança primeiro; idade não apaga domínio; repetição do mesmo run não fabrica mastered.
- Dependência: T02. AC-08/09/10/19.

## T04 — Compilação e ciclo do ambiente

- [ ] Compilar tabelas/tipos/índices/dados parametrizados a partir do contrato.
- [ ] Implementar setup atômico de schemas fixos, hashes, grants, lock e reconstrução.
- [ ] Validar schema/dados e expor hook transacional de preflight; conectar referência/expected_rows na T06. Até lá nenhum cenário é publicado como ready para aprendizagem.
- [ ] Criar fixture local com o contrato de exemplo; não conectar catálogo como caminho principal.
- Aceite: falha no meio do setup reverte e mantém exercício anterior utilizável; retomada reproduz os mesmos dados; não apaga tutor_state.
- Dependência: T02. AC-03/04/09/16.

## T05 — Executor e dialetos

- [ ] AST allowlist recursiva, escopos/lineage, funções e tabelas limitadas.
- [ ] READ ONLY, rollback, timeout, row/byte limits, SQLSTATE seguro e preview.
- [ ] Alias lateral e alias em HAVING normalizados com identidade e rastreabilidade.
- [ ] EXPLAIN JSON interno, sem ANALYZE.
- Aceite: SQL legítimo funciona; DML em CTE, SELECT INTO, COPY, locks, funções de host, acesso a state/hidden, múltiplas instruções e schema bypass são recusados. Timeout não penaliza perfil. Alias com coluna de entrada homônima respeita precedência.
- Dependência: T04. AC-05/13/15/16/17.

## T06 — Avaliação determinística

- [ ] Comparar resultados completos visível/oculto por multiconjunto ou sequência.
- [ ] Tipos, NULL, Decimal, aliases, duplicatas e todas as constraints MVP.
- [ ] Classificar learner_sql_error, blocked, inconclusive, invalid_exercise e falha da primary_skill.
- [ ] Conectar o preflight de T04: referência sob papel restrito na mesma transação, resultado esperado e constraints passam antes de ready.
- Aceite: queries semanticamente equivalentes passam; CTE morto com janela não satisfaz window_function; resultado divergente após preview não é aprovado; limite produz inconclusive. Reference inválida rejeita exercício.
- Dependência: T05. AC-06/13/14/16.

## T07 — LLM, geração e revisão pedagógica

- [ ] Cliente configurável e fake determinístico, sem retry duplicado.
- [ ] Operações decompose_goal/select_next/generate_exercise/review_exercise com schemas e orçamento limitado.
- [ ] Conectar decisões válidas à geração e setup; usar catálogo apenas na contingência.
- [ ] Operações assess_response, feedback, chat, reveal_solution e summarize.
- [ ] Rubricas com evidência textual, nenhum score inventado; pending_review e Retry Review.
- [ ] Catálogo mínimo: um fallback por domínio oficial, mais variantes de aggregation para fluxo completo; ausência de combinação compatível é estado explícito.
- Aceite: contrato LLM não pode mudar política/capacidades; falha de geração não publica dados; feedback não altera nota SQL; erro 401 não repete; JSON inválido esgota orçamento finito.
- Dependência: T03/T06. AC-03/04/08/12/16/18/19.

## T08 — Orquestração e recuperação

- [ ] Run/Submit/chat/Hint/Show Solution/Next/Skip/Save Draft/Close/Change Goal/Retry Review como comandos distintos.
- [ ] action_id, payload_hash, revision, operação durável, transação de submission+evidence+profile.
- [ ] Recuperação antes/depois do commit e descarte de resposta LLM tardia.
- [ ] Estados de run/feedback/pending_review conforme learning_state.md.
- Aceite: injetar falha após execução e antes/depois de commit; repetir mesma ação aplica zero eventos extras. Nova intenção pode ser nova tentativa. Troca de run durante chamada impede aplicação tardia.
- Dependência: T07. AC-02/05/06/07/09/16/18.

## T09 — Interface Streamlit

- [ ] Objetivo, modo, declaração opcional, retomada e resumo em en-US.
- [ ] Enunciado/schema/amostra, editor SQL, justificativa conforme modalidade e plano real.
- [ ] Run SQL e Submit Answer separados, estados busy/erro/sem dados/limite/pending_review.
- [ ] Chat socrático, dicas, revelação autorizada, avanço, skip, salvar rascunho e encerramento.
- [ ] Progresso por três dimensões, evidências, snapshots e indicador de LLM remoto/contingência.
- Aceite: rerun não reenvia ações; resposta de chat não é nota; labels/output conforme idioma; fluxo inteiro executável sem CLI de aprendizagem.
- Dependência: T08. AC-01/05/09/11/12/18.

## T10 — Verificação integrada e entrega

- [ ] Executar a matriz abaixo com PostgreSQL real, inclusive papéis restritos.
- [ ] Testes de UI com Streamlit; logs e fronteiras público/privado.
- [ ] Smoke test com provedor real configurado: gerar contrato, provisionar, explorar, submeter, receber feedback e gerar próximo cenário adaptativo.
- [ ] Documentar instalação reproduzível, comandos, limitações e resultado de cada teste.
- Aceite: AC-01 a AC-20 demonstrados. Sem credencial LLM, registrar smoke real pendente; não declarar MVP integralmente validado com apenas mocks.
- Dependência: T09.

## Matriz de cenários críticos

| Cenário | Evidência exigida |
|---|---|
| Run com SQL correto e errado | Histórico operacional muda; profile/attempt_count continuam idênticos |
| Duas submissões do mesmo action_id | Uma submission e um evento por skill |
| Falha entre submission e mastery | Rollback conjunto, recuperação idempotente |
| Reinício após SQL antes de feedback | Resultado reaparece; feedback retoma sem reaplicar mastery |
| Novo objetivo | Nova sessão ativa, anterior fechada, perfil preservado |
| validated + low + mastery 2 | Regra C, não E1 |
| self_declared + medium + mastery 4 | D1, não avanço |
| mastered após apenas um acerto | Promoção recusada |
| Retenção após sete dias simulados | F só sem intervenções prioritárias; novos contextos |
| Resposta com dica/solução | Sem promoção indevida; reveal só por ação autorizada |
| Primeiras 200 linhas iguais, cauda diferente | incorrect se completo; inconclusive se limite |
| NULL, duplicatas, ordem e Decimal | Sem conversão em set nem tolerância implícita |
| Plan/explanation com LLM indisponível | pending_review, score null, perfil inalterado |
| CTE escrita, função perigosa, schema state/hidden | blocked antes da execução; grants também restringem |
| Alias autorizado e colisão de nome | Normalização auditada ou inconclusive sem penalidade |
| Contrato sem janela para skill window | Rejeitado antes de ready |
| SQL/reasoning contendo instrução de prompt | Sem alteração de política/capacidade/revelação |
| Dataset oculto com requisito não anunciado | Contrato rejeitado/reparado |
| Dois pedidos de preparação simultâneos | Lock + revision preservam um ambiente coerente |
| Capacidades reservadas | Limitação informada antes de gerar; nenhuma falha do aluno |

## Posterior ao MVP

PARTIAL_SETUP/LEARNER_SETUP, escrita/DDL do aluno, EXECUTION_SUCCESS, EXPLAIN ANALYZE, tipos/índices adicionais e novos validators exigem contratos/testes próprios. Multiusuário/serviços remotos não são evolução automática deste escopo.
