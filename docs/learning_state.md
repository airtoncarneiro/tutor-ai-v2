# Estado, evidências e transições

Fonte normativa do estado e da política numérica `evidence-v1`. As prioridades para escolher ações permanecem em [tutor_prompt.md](tutor_prompt.md).

## Modelos persistentes

UUIDs para entidades; timestamps UTC; JSONB validado por modelos Pydantic. FKs e CHECKs no banco reforçam invariantes. Não apagar registros históricos por cascade no encerramento.

| Tabela em tutor_state | Campos obrigatórios além de id e created_at |
|---|---|
| student_profiles | singleton_key=1 UNIQUE, updated_at |
| skill_states | profile_id, skill_key, mastery_score, evidence_status, confidence, successful_attempts, failed_attempts, hints_required, last_result nullable, last_seen nullable, retrieval_due_at nullable, declared_level nullable, recurring_errors JSONB, revision, policy_version; UNIQUE(profile_id, skill_key) |
| learning_sessions | profile_id, learning_goal, mode, status, current_run_id nullable, current_focus nullable, current_difficulty, completed_count, finalized_since_checkpoint, next_action, provisional_tree nullable, prerequisite_return_focus nullable, revision, ended_at nullable |
| exercise_contracts | exercise_id, version, contract_json, content_hash, source=llm/catalog, prompt_version, registry_version; UNIQUE(exercise_id, version), conteúdo imutável |
| exercise_runs | session_id, contract_id FK exata, state, dataset_hash, attempt_count, failed_count, hint_level, hint_events, solution_revealed, draft_sql, draft_reasoning, context_tag, evidence_kind, finalized_at nullable |
| operations | action_id UNIQUE, session_id, run_id nullable, kind, payload_json, payload_hash, expected_revision, status, error_code nullable, updated_at |
| sql_runs | operation_id UNIQUE, run_id, submitted_sql, executed_sql nullable, execution_json; não possuem avaliação pedagógica |
| submissions | operation_id UNIQUE, run_id, submitted_sql nullable, reasoning nullable, hint_level_at_submit, evaluation_json, status, feedback_status, finalized_at nullable |
| evidence_events | submission_id, skill_key, result, independent, assisted, source, error_kind nullable, before_state, after_state, policy_version; UNIQUE(submission_id, skill_key) |
| lifecycle_events | session_id nullable, skill_key nullable, operation_id nullable, kind, dedup_key UNIQUE, before_state, after_state; aging, declaração, ajuda, modo e ciclo sem submission |
| tutor_messages | session_id, run_id nullable, submission_id nullable, request_id, role, content, prompt_version, model_id nullable; deduplicação (request_id, role) |
| checkpoints | session_id, trigger_event_id UNIQUE, reasons JSONB, state_snapshot, summary |

session current_run deve pertencer à própria sessão, validado em toda transação. JSONB não substitui schema de aplicação. Revisões incrementam em mutação operacional/pedagógica, não em mera consulta. Tabelas de eventos podem manter mais campos diagnósticos sem mudar semântica.

Índice único parcial em constante para learning_sessions WHERE status='active'. Singleton profile nunca é substituído na troca de objetivo. Listas validated/mastered são projeções de skill_states, não cópias independentes.

## Estados e navegação

- Sessão: active -> closed. Sessão fechada não reabre; iniciar mesmo objetivo depois cria nova sessão com o mesmo perfil. Sessão ativa sobrevive a reinício.
- Run: preparing -> ready -> awaiting_answer -> retry ou completed. ready vira awaiting_answer quando publicado. retry -> completed/retry após nova submissão.
- Falha de setup: preparing -> setup_failed; não altera run atual publicado.
- Skip: awaiting_answer/retry -> skipped; Show Solution autorizado -> revealed; fechar sessão com exercício pendente -> abandoned.
- completed/skipped/revealed/abandoned são finais. Next Exercise cria novo run; contrato histórico não muda.
- Submission: pending -> pending_review (se depende de rubrica) -> finalized; ou pending -> finalized em SQL_ONLY. Inconclusive finaliza a operação, mantém run para nova ação sem evidência.
- Operation: pending -> running -> completed/failed/stale. Failed é retryable somente com mesmo payload e estado compatível. Pending_review não é falha da operação de coleta.
- Estado transient de envio da UI nunca é fonte do domínio.

Nova sessão: foco null, dificuldade 1, contadores zero, histórico operacional vazio; consultar profile, aplicar política e só então gerar. Troca/encerramento: snapshot e consolidação de eventos já confirmados, sem reaplicá-los.

Next Exercise só após run final; em retry o aluno pode continuar ou Skip. Pending_review bloqueia avanço até revisar ou Skip; skip fecha avaliações ainda pendentes como inconclusive/stale, sem efeito tardio.

## Domínio

- mastery_score inteiro 0..5: unknown, superficial, assisted, independent, consistent, advanced.
- evidence_status enum ordenado unknown < self_declared < observed < validated < mastered.
- confidence enum low < medium < high.
- Estado inicial: mastery=0, evidence=unknown, confidence=medium, contadores=0. Medium indica confiança na classificação “ainda não observado”, não domínio.
- Declaração salva declared_level opcional 0..5; evidence passa de unknown para self_declared, sem promoção de domínio. Nunca rebaixa estado observado/validado.

Uma submission finalized com decisão pedagógica atribuível ao aluno aumenta attempt_count do run; incorrect/partial/learner_sql_error aumentam failed_count do run. No perfil, correct aumenta successful_attempts da primary_skill; incorrect/partial aumentam failed_attempts somente quando primary_skill_affected=true. learner_sql_error não altera a competência conceitual sem evidência específica. Inconclusive, blocked, pending_review, falha de ambiente e chat não incrementam tentativas pedagógicas.

Run SQL não altera quaisquer desses campos nem last_seen. Mensagens e ações de ajuda têm contadores próprios; não entram em failed_attempts.

## Independência e atualização

Reaplicar evento é proibido pela chave única. Cada evento guarda origem deterministic/rubric_llm e evidências. Só primary_skill é atualizada numericamente no MVP.

Independência exige novo run com contrato/dataset distintos (content_hash), contexto semântico diferente ou evidence_kind diferente, e ausência de solução revelada. Trocar UUID/nomes superficiais não cria independência: LLM declara context_tag e propósito; Python compara hash e tag, trata repetição como não independente. Sucesso após erro no mesmo run pode demonstrar aprendizagem, mas conta no máximo uma evidência positiva daquele run.

Ajuda: hint_level >= 1 ou solução torna resposta assisted; somente resposta correta sem ajuda e sem feedback corretivo anterior no run é unassisted. A definição é conservadora para promoção. Tentativas repetidas continuam registradas.

Aplicar regras na ordem:
1. Sem resultado pedagógico confiável: não mudar skill_state.
2. Erro isolado conceitual/semântico da primary_skill em estado validated/mastered: baixar confidence um nível; manter mastery/evidence.
3. Segundo erro independente consecutivo (sem sucesso intermediário): confidence=low, mastery=max(1, mastery-1), evidence um nível abaixo com piso observed. Repetições no mesmo run não rebaixam várias vezes.
4. Erro em unknown/self_declared vira observed, mastery=1, confidence=medium. Em observed, falha mantém mastery no máximo 2; preservar histórico.
5. Correct assisted: ao menos observed e mastery=2 se antes <2; não reduz estado superior, não promove validated/mastered, não recupera confiança rebaixada.
6. Primeiro sucesso unassisted independente: ao menos observed, mastery>=3, confidence=max(confidence atual, medium); sucesso não reduz confiança alta.
7. Dois sucessos unassisted independentes desde a última contradição: evidence>=validated, mastery>=3, confidence=high.
8. Terceiro sucesso independente, incluindo outro contexto e uma tarefa composed: mastery>=4, evidence>=validated, confidence=high.
9. Mastered exige também sucesso delayed_retrieval ocorrido pelo menos sete dias após a promoção a validated, além de isolated + transfer + composed anteriores: mastery=5, evidence=mastered, confidence=high.

Sucesso unassisted durante revalidação mantém mastery/evidence superiores existentes; primeiro restabelece confidence=medium, segundo independente=high. Não apaga falhas antigas; elas permanecem no histórico e saem apenas da janela “desde última contradição”. Se regressão reduziu evidência, promoções precisam de novos sucessos conforme as regras 6–9.

Todas as evidências podem ser de resultado SQL ou rubrica válida. Rubrica tem proveniência LLM visível; não é observação de runtime. Uma resposta partial conta como falha da primary_skill apenas se critério obrigatório dessa skill falhou. SQL incorreto por requisito secundário mantém lacuna a investigar e não rebaixa automaticamente a primary_skill.

## Retenção e checkpoints

Após mastery>=4, agendar retrieval_due_at=agora+7 dias. Revisão bem-sucedida agenda +14 dias, próxima +30, depois +30. Datas são estado, não automações externas. Só oferecer quando aluno abrir sessão e política F permitir.

Após 90 dias sem observação de skill previously observed, reduzir confidence um nível uma vez por intervalo de 90 dias; registrar aging_event com intervalo para deduplicação. Não apagar domínio/evidence. Aging aplica apenas às skills relevantes antes da seleção e pode acionar C.

Persistir aging_event em lifecycle_events. Datas de promoção, sucessos independentes, última contradição e número de retenções são derivados dos evidence_events; manter cache em skill_states é opcional, com recomputação testada. Atualizar last_seen somente em evidência pedagógica atribuível à skill, nunca em acesso à tela, aging ou Run SQL. hints_required conta eventos de ajuda exibida, deduplicados por action_id; uma hint mostrada em rerun não conta de novo.

Checkpoint em cinco runs finalized (completed/skipped/revealed, não abandoned), promoção de evidence, mudança de estratégia/ramo, modo, objetivo ou encerramento. Deduplicar por evento e acumular reasons. completed_count só conta completed; finalized_since_checkpoint conta os três finais citados. Snapshot inclui goal/focus/difficulty, listas validated/developing/review_required, next_action e revision. Perfil é atualizado por eventos, snapshot não o substitui.

## Ajuda e solução

FOCUSED_LEARNING:
- failed_count=0: ajuda automática 0; pedido explícito Hint pode autorizar nível 1.
- primeira falha avaliada: nível máximo 1; segunda 2; terceira+ 3.
- níveis: 0 pergunta sem pista da solução, 1 conceito, 2 estrutura, 3 trecho parcial, 4 solução.
- Um Hint explícito aumenta teto em um sobre o último hint_level, limitado a 3 e max_hint_level do contrato; não exige erro fabricado.
- Show Solution é permitido só por ação explícita após três falhas avaliadas OU duas ações Hint, se allow_solution_reveal=true. É nível 4 separado do teto de dicas; não ocorre por escolha autônoma do LLM.
- Revelação fecha run como revealed, salva evento de ajuda e não promove domínio. Próximo exercício deve ser independente.
- LLM recebe teto calculado; resposta acima do teto/fora de allowed_moves é rejeitada. Fallback usa pistas privadas aprovadas previamente pelo contrato.

Assessment: hint_level=0 e solução desabilitada; UI oferece mudança explícita para FOCUSED_LEARNING. Falta de dados, limite e erro de infraestrutura nunca desbloqueiam solução como se fossem tentativas erradas.
