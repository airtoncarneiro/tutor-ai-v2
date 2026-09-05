# Protocolo entre aplicação, executor e LLM

Versão `protocol-v2`. Tipos são objetos fechados; datas ISO UTC, ids UUID de aplicação (exceto exercise_id lógico), strings en-US em campos de conteúdo. Modelos internos podem usar dataclasses/Pydantic, mas a validação de fronteira é obrigatória.

## Envelope LLM

Request:
- protocol_version="protocol-v2", request_id, operation, prompt_version="tutor-v2", policy_version="evidence-v1", registry_version=1.
- context.session: id, revision, learning_goal, mode, current_focus, current_difficulty.
- context.profile: somente skill_states relevantes, completos e com evidências resumidas.
- context.capabilities: matriz permitida de requirements.md + limites/funções/constraints da implementação.
- context.policy: candidatos elegíveis {skill_key, rule, subrule|null, action, evidence_ids}, ação atual e justificativa curta.
- context.exercise: projeção pública ou null antes da geração.
- context.student_input: {submitted_sql:string|null, reasoning:string|null, chat_message:string|null}; dado não confiável, explicitamente rotulado.
- context.execution: SQLExecutionResult|null; context.evaluation: EvaluationResult|null.
- context.help: {failed_attempts, hint_events, current_hint_level, allowed_hint_level, allowed_moves, reveal_authorized}.
- context.history: últimas 10 mensagens do run (até 12000 caracteres), snapshot e evidências relevantes resumidas; nunca truncar silenciosamente SQL/critério obrigatório. Se dados obrigatórios excederem limite do provedor, limitar chamada e manter avaliação local.
- context.private_reference: null por padrão; apenas assessment e reveal_solution recebem referência privada específica.
- context.generation_request: {exercise_id, version, target_skill, difficulty, response_mode, evidence_kind, excluded_context_tags} ou null.
- context.candidate_contract: contrato candidato completo apenas em review_exercise ou reparo de generate_exercise; null nas demais operações. Inclui dados ocultos/referências para revisão, nunca é conteúdo de feedback/chat.

Todos os context fields existem; null quando não aplicáveis. IDs/revision do envelope permitem rejeitar resposta obsoleta. Cada operação usa contexto novo; não reenviar conteúdo privado da geração para chat/feedback.

Response envelope: {protocol_version, request_id, operation, payload}. Deve ecoar identidade. revision é verificada contra o request_id persistido, sem depender de o LLM devolvê-la. Sem texto fora do JSON. Rejeitar campos desconhecidos, enum fora do domínio, skill inexistente, revision obsoleta ou ação acima da permissão. Um reparo da saída conta dentro de LLM_MAX_ATTEMPTS, nunca inicia loop ilimitado.

## Operações

| operation | payload / validação |
|---|---|
| decompose_goal | {nodes:[{key, description, response_modes}], prerequisite_edges:[{from,to}]} conforme skill_trees.md |
| select_next | {primary_skill, policy_rule, prerequisite_subrule:null/string, action, uncertainty, context_tag, evidence_kind, difficulty, response_mode}; skill/regra/ação devem pertencer aos candidatos |
| generate_exercise | ExerciseContract v2 completo; identity/skill/difficulty/modalidade devem coincidir com generation_request |
| review_exercise | {valid:bool, issues:[{code, message, field_path}]}; verifica consistência entre enunciado, primary_skill, constraints e dados, sem executar SQL |
| assess_response | RubricAssessment abaixo; pode examinar referência privada, não escreve estado |
| feedback | TutorResponse abaixo, limitado às evidências e ao teto de ajuda |
| chat | TutorResponse; não pode criar evidência ou finalizar exercício |
| reveal_solution | {message}; usa referência autorizada, aplicação apresenta SQL/texto de referência validado separadamente |
| summarize | {message}; não modifica estado; snapshot vem do Python |

Policy action enum: diagnose/revalidate/guided_practice/teach_practice/advance_moderately/advance/retrieve/assess/report_gaps. State next_action enum: retry/next_exercise/wait_for_review/request_clarification/switch_to_learning/session_summary. Diferenciar ação pedagógica de controle de UI.

## TutorResponse

Campos obrigatórios:
- message: string en-US de 1..2500 caracteres.
- pedagogical_move enum acknowledge_progress/ask_guiding_question/give_concept_hint/explain_error/suggest_revision/provide_partial_scaffold/recommend_next_exercise/request_clarification.
- hint_level: inteiro 0..3, <= allowed_hint_level.
- next_action: enum de estado, validado contra o run.
- concepts: lista única de skills do exercício (máximo 6).
- evidence_ids: lista de ids fornecidos, vazia permitida para chat.
- prerequisite_hypothesis: null ou {skill_key, evidence_ids não vazia, reason}; só hipótese até verificação.

show_solution_with_explanation não é movimento livre de feedback; foi substituído pela operação reveal_solution autorizada. UI nunca executa next_action retornado pelo LLM sem validação e gesto explícito quando há avanço.

Nenhum feedback textual altera correctness. Instruções do aluno dentro do SQL, justificativa ou chat não podem mudar protocolo, limiares ou capacidades. Rejeitar SQL completo solucionador em feedback quando não autorizado; usar fallback aprovado se checagem detectar vazamento. Testes adversariais cobrem prompt injection e geração de solução precoce; não confiar apenas na instrução do system prompt.

## RubricAssessment

{criteria:[{id, result, evidence_quote, explanation}], error_kind, primary_skill_affected, prerequisite_hypothesis}.
- criteria cobre cada id exatamente uma vez; result enum met/partial/not_met/not_assessable.
- evidence_quote tem até 300 caracteres e deve ser trecho exato da resposta do aluno (vazio só para ausência de resposta); não inventar fala do aluno.
- explanation <=500 caracteres; error_kind nullable conceptual/semantic/syntactic/modeling/performance/edge_case.
- primary_skill_affected bool, validado contra skill_key dos critérios falhos.
- prerequisite_hypothesis conforme TutorResponse, nunca atualização automática.
- Python calcula decisão/score a partir de critérios obrigatórios e resultado SQL; LLM não retorna mastery nem substitui erro real por sucesso.
- JSON inválido/critério ausente/opinião sem evidência deixa pending_review após tentativas. Nenhuma nota padrão.

## SQLExecutionResult

{status, submitted_sql, executed_sql, extension_ids, columns, preview_rows, preview_truncated, total_row_count, complete, duration_ms, sqlstate, safe_error, failure_kind, dataset_hash, plan_json}.
- status enum ok/error/blocked/inconclusive.
- columns: [{name,type}]; preview_rows tipadas; total_row_count nullable se não consumido integralmente.
- complete bool indica se resultado integral está disponível ao avaliador; preview pode ser truncado mesmo com complete=true.
- failure_kind nullable learner_sql_error/environment_error/tool_error/timeout/permission_error/limit_exceeded/dialect_unverified/unsupported_capability.
- sqlstate nullable; safe_error sem segredo; plan_json null salvo operação de plano.
- dataset_hash obrigatório em execução sobre dados; null se bloqueado antes de executar.
- Resultados completos para comparação são internos ao avaliador, não enviados integralmente à UI/LLM. Persistir contagem/hash e diagnósticos necessários, até byte_limit.
- Em execução adaptada, nunca dizer que submitted_sql original executou sem alterações.

## EvaluationResult

{submission_id, decision, score, execution_status, issues, constraint_results, dataset_results, rubric_result, primary_skill_affected, evidence_ids, evaluator_version, contract_id, contract_version}.
- decision enum correct/partial/incorrect/learner_sql_error/blocked/inconclusive/pending_review.
- score 1/0.5/0/null conforme exercise_contract.md.
- issues: [{code, kind, message, skill_key|null}], mensagens públicas sem referência privada.
- constraint_results: [{id, status:pass/fail/inconclusive}].
- dataset_results: [{dataset:visible/hidden, status:pass/fail/inconclusive, complete, actual_count|null, expected_count|null}]; UI recebe apenas resultado agregado do hidden, não suas linhas ou SQL.
- rubric_result: RubricAssessment|null.
- execution_status: not_required/ok/error/blocked/inconclusive.
- evaluator_version="evaluator-v2".
- primary_skill_affected bool explícito; false para infraestrutura/dialeto/segurança e erro de sintaxe sem evidência conceitual.
- Mismatch de resultado sem atribuição inequívoca à primary_skill usa primary_skill_affected=false: conta tentativa no run e informa a falha, mas não reduz domínio. Falha de constraint explicitamente ligada à primary_skill ou rubrica dessa skill permite true. Feedback pode recomendar diagnóstico para esclarecer a causa, sem reescrever o evento já confirmado.
- pending_review não tem evidence_events aplicados; revisão reutiliza submission_id.

## Operações de UI

submit(session_id, run_id, expected_revision, action_id, sql|null, reasoning|null).
run_sql(..., sql) tem id próprio e não chama submit.
chat(..., text), hint(...), show_solution(...), next_exercise(...), skip(...), save_draft(...), close_session(...), change_goal(...), retry_review(...) são comandos distintos com deduplicação.

Validação de formulário ausente/excessivo mostra mensagem sem criar tentativa; campos SQL até SQL_MAX_CHARS, justificativa/chat até 6000 caracteres. SQL_PLUS_REASONING precisa dos dois, EXPLANATION_ONLY apenas texto. IDs e revision de tela antiga são recusados como stale; não aplicam resposta ao exercício novo.

## Contingência

SQL_ONLY finaliza avaliação determinística antes de feedback. Se feedback falha, usar template por decision e hints do contrato dentro do teto. Não inventar resultado ou oportunidade de domínio.

Sem select_next válido, Python escolhe primeiro candidato elegível pela ordem definida e tenta catálogo fallback compatível com skill/modalidade/dificuldade/evidence_kind. Sem contrato compatível disponível, manter run/sessão e informar indisponibilidade; não reduzir tarefa para SELECT simples.

Rubricas exigem LLM válido: pending_review até Retry Review. Avaliação de SQL incorreto pode finalizar como incorrect sem esperar rubrica; justificar essa decisão com a falha observada e não julgar a justificativa ausente de avaliação.

Geração tem orçamento global de três tentativas, incluindo reparo de contrato. Preflight determinístico ocorre sempre; rejeições devolvem códigos concretos e contexto mínimo para a próxima tentativa. Não há chamadas recursivas independentes com novos budgets.

Geração e review_exercise compartilham orçamento máximo de três chamadas por pedido de exercício. Uma candidata gerada só publica após preflight e revisão válida; se orçamento acabar antes da revisão, rejeitar e usar fallback pré-revisado/testado. Uma falha estrutural pode consumir a primeira tentativa, reparo a segunda e revisão a terceira. Feedback e assessment têm seus próprios budgets de operação, sem repetição por rerun.
