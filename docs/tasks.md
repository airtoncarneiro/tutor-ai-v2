# Backlog de implementação

O backlog descreve o produto desejado e acompanha a implementação. O MVP
vertical cobre T01–T09 nos limites descritos em verification.md; os itens
explicitamente parciais continuam pendentes. A documentação não comprova
deploy. O smoke real de geração, provisionamento, execução, avaliação e
feedback já foi executado; a validação do segundo cenário adaptativo continua
pendente. Ordem de dependência
obrigatória; nenhuma tarefa implica commit/deploy automático.

## T01 — Fundação e configuração

- [x] Criar módulos conforme architecture.md, Python 3.12, ambiente reproduzível, dependências fixadas e lockfile.
- [x] Configurar .env.example/.gitignore sem segredos e validação de limites/configuração.
- [x] Implementar modelos fechados de runtime_contracts.md e ExerciseContract v2.
- [x] Criar comandos documentados de instalação, migração, testes e abertura do Streamlit.
- Aceite: configuração ausente falha claramente; tipos/enum/campos desconhecidos são rejeitados; import e testes de modelos passam.
- Dependência: nenhuma. Requisitos: base de AC-01/04.

## T02 — Persistência e inicialização local

- [x] Migrações versionadas, base/schemas/papéis e bootstrap idempotente.
- [x] Repositories, singleton profile, unicidade de sessão ativa, FKs, conteúdo imutável e revisions.
- [x] Docker Compose opcional em loopback e instruções para PostgreSQL instalado.
- [x] Validar permissões reais com runner/evaluator, sem uso de superuser na aplicação.
- Aceite: duas aberturas concorrentes não criam duas sessões; credenciais runner não leem tutor_state nem dados ocultos; bootstrap não altera base alheia.
- Dependência: T01. AC-01/02/15.

## T03 — Política e estado pedagógico

- [x] Árvores oficiais/provisórias, resolução de objetivo e declaração de conhecimento.
- [x] Implementar A–F e todos os casos tabulados em tutor_prompt.md, incluindo prioridade global de intervenção sobre revisão.
- [x] Implementar evidence-v1, independência, ajuda, regressão, aging e retenção com relógio injetável.
- [x] Checkpoints deduplicados e troca/encerramento de objetivo preservando perfil.
- Aceite: nenhum estado válido seleciona ações concorrentes; falha isolada rebaixa confiança primeiro; idade não apaga domínio; repetição do mesmo run não fabrica mastered.
- Dependência: T02. AC-08/09/10/19.

## T04 — Compilação e ciclo do ambiente

- [x] Compilar tabelas/tipos/índices/dados parametrizados a partir do contrato.
- [x] Implementar setup atômico de schemas fixos, hashes, grants, lock e reconstrução.
- [x] Validar schema/dados e expor hook transacional de preflight; conectar referência/expected_rows na T06. Até lá nenhum cenário é publicado como ready para aprendizagem.
- [x] Criar fixture local com o contrato de exemplo; não conectar catálogo como caminho principal.
- Aceite: falha no meio do setup reverte e mantém exercício anterior utilizável; retomada reproduz os mesmos dados; não apaga tutor_state.
- Dependência: T02. AC-03/04/09/16.

## T05 — Executor e dialetos

- [x] AST allowlist recursiva, escopos/lineage, funções e tabelas limitadas.
- [x] READ ONLY, rollback, timeout, row/byte limits, SQLSTATE seguro e preview.
- [x] Alias lateral e alias em HAVING normalizados com identidade e rastreabilidade.
- [x] EXPLAIN JSON interno, sem ANALYZE.
- Aceite: SQL legítimo funciona; DML em CTE, SELECT INTO, COPY, locks, funções de host, acesso a state/hidden, múltiplas instruções e schema bypass são recusados. Timeout não penaliza perfil. Alias com coluna de entrada homônima respeita precedência.
- Dependência: T04. AC-05/13/15/16/17.

## T06 — Avaliação determinística

- [x] Comparar resultados completos visível/oculto por multiconjunto ou sequência.
- [x] Tipos, NULL, Decimal, aliases, duplicatas e todas as constraints MVP.
- [x] Classificar learner_sql_error, blocked, inconclusive, invalid_exercise e falha da primary_skill.
- [x] Conectar o preflight de T04: referência sob papel restrito na mesma transação, resultado esperado e constraints passam antes de ready.
- Aceite: queries semanticamente equivalentes passam; CTE morto com janela não satisfaz window_function; resultado divergente após preview não é aprovado; limite produz inconclusive. Reference inválida rejeita exercício.
- Dependência: T05. AC-06/13/14/16.

## T07 — LLM, geração e revisão pedagógica

- [x] Cliente configurável e fake determinístico, sem retry duplicado.
- [x] Operações decompose_goal/select_next/generate_exercise/review_exercise com validação estrita e orçamento limitado.
- [x] Conectar decisões válidas à geração e setup; usar catálogo apenas na contingência.
- [x] Operações assess_response, feedback, chat, reveal_solution e summarize.
- [x] Rubricas com evidência textual, nenhum score inventado; pending_review e Retry Review.
- [x] Catálogo mínimo: um fallback por domínio oficial, mais variantes de aggregation para fluxo completo; ausência de combinação compatível é estado explícito.
- Aceite: contrato LLM não pode mudar política/capacidades; falha de geração não publica dados; feedback não altera nota SQL; erro 401 não repete; JSON inválido esgota orçamento finito.
- Dependência: T03/T06. AC-03/04/08/12/16/18/19.

## T08 — Orquestração e recuperação

- [x] Run/Submit/chat/Hint/Show Solution/Next/Skip/Save Draft/Close/Change Goal/Retry Review como comandos distintos.
- [x] action_id, payload_hash, revision, operação durável, transação de submission+evidence+profile.
- [x] Recuperação de operações e rollback conjunto; resposta LLM tardia é descartada quando a revisão muda.
- [x] Estados de run/feedback/pending_review conforme learning_state.md.
- Aceite: injetar falha após execução e antes/depois de commit; repetir mesma ação aplica zero eventos extras. Nova intenção pode ser nova tentativa. Troca de run durante chamada impede aplicação tardia.
- Dependência: T07. AC-02/05/06/07/09/16/18.

## T09 — Interface Streamlit

- [x] Sem sessão ativa, solicitar objetivo, modo e declaração opcional em en-US; gerar o primeiro exercício pelo LLM/fallback compatível. Sessão ativa é retomada sem regeneração; resumo está implementado.
- [x] Enunciado/schema/amostra, editor SQL, justificativa conforme modalidade e plano real.
- [x] Run SQL e Submit Answer separados, estados busy/erro/sem dados/limite/pending_review.
- [x] Chat socrático, dicas, revelação autorizada, avanço, skip, salvar rascunho e encerramento.
- [x] Progresso por competência, snapshots de run, indicador de LLM remoto/contingência e visualização detalhada das evidências persistidas.
- Aceite: rerun não reenvia ações; resposta de chat não é nota; labels/output conforme idioma; fluxo inteiro executável sem CLI de aprendizagem.
- Dependência: T08. AC-01/05/09/11/12/18.

## T10 — Verificação integrada e entrega

- [x] Executar a matriz abaixo com PostgreSQL real, inclusive papéis restritos; a verificação reproduzível está em `scripts/security_matrix.py`.
- [x] Testes de UI com Streamlit; logs e fronteiras público/privado.
- [x] Validar com provedor real configurado a geração do próximo cenário adaptativo após contrato, provisionamento, exploração, submissão e feedback, usando base temporária descartável.
- [x] Documentar instalação reproduzível, comandos, limitações e resultado de cada teste.
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
