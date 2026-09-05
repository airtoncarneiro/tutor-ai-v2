# Requisitos e decisões do MVP

Versão normativa: 2. Leia [política](tutor_prompt.md), [estado](learning_state.md), [contrato](exercise_contract.md) e [protocolo](runtime_contracts.md) para as regras operacionais.

## Escopo confirmado

Python + Streamlit em processo local; PostgreSQL local; um aluno; nenhuma autenticação ou API HTTP interna. Interface vinculada a loopback. LLM remoto é permitido, mas estado, banco e execução ficam na máquina. Interação e nomes técnicos em en-US, conforme o prompt aprovado.

Zero sessões ativas é permitido antes de começar e após encerrar; durante o aprendizado há exatamente uma. Trocar de objetivo consolida e encerra a anterior, preserva o perfil e abre outra.

## Capacidades implementadas e reservadas

| Capacidade | MVP |
|---|---|
| Objetivos aggregation, window_functions, recursive_cte | Exercícios de leitura gerados pelo LLM, diagnóstico, prática e progressão |
| query_performance | Explicação conceitual e análise de EXPLAIN JSON real; sem prometer ganho de tempo |
| Objetivo não registrado | Árvore provisória validada, limitada às capacidades presentes |
| GENERAL_ASSESSMENT, FOCUSED_ASSESSMENT, FOCUSED_LEARNING | Todos; modos de avaliação não ensinam automaticamente |
| SQL_ONLY, SQL_PLUS_REASONING, EXPLANATION_ONLY | Todos, com campos de resposta e avaliadores adequados |
| AUTO_SETUP | Criação automática de tabelas, índices btree simples e dados pelo contrato |
| PARTIAL_SETUP, LEARNER_SETUP | Reservados; não gerar exercícios que os exijam no MVP |
| RESULT_EQUIVALENCE, EXPLANATION, PLAN_ANALYSIS | Implementados |
| EXECUTION_SUCCESS para escrita/DDL | Reservado; não gerar exercícios desse tipo |
| EXPLAIN ANALYZE, criação de índices pelo aluno, particionamento físico | Posteriores; conteúdo conceitual pode ser praticado |
| Extensões registradas de alias Redshift | Compatibilidade limitada e explícita descrita na arquitetura |
| Dados ocultos de validação | Um conjunto adicional por exercício SQL, com variáveis pedagógicas declaradas |

Restringir capacidades de execução não remove domínios do core. Quando um pedido exige capacidade reservada, explicar a limitação antes de criar exercício e oferecer uma modalidade compatível; não registrar falha do aluno. Não aceitar configuração declarando uma capacidade como implementada sem executor e testes.

## Requisitos funcionais

- **RF-01 Sessão e objetivo:** informar learning_goal e modo (padrão FOCUSED_LEARNING), declarar conhecimento opcionalmente, consultar perfil antes do primeiro exercício. Mesmo objetivo retoma sessão ativa; troca explícita encerra e abre outra atomicamente.
- **RF-02 Adaptação:** aplicar a árvore A–F em tutor_prompt.md. LLM propõe competência/cenário dentro das ações elegíveis; Python valida prioridade, capacidades e evidência. Guardar regra e evidências usadas. Não retestar pré-requisitos confiáveis preventivamente.
- **RF-03 Geração:** gerar ExerciseContract pelo LLM; validar estrutura, capacidades, semântica e solução de referência; preparar e verificar ambiente antes da apresentação. Falha permite reparo limitado e fallback compatível, nunca publicação de exercício inválido.
- **RF-04 Exploração:** Run SQL executa o editor atual, exibe preview/erro real e registra sql_run. Não cria submission, não chama o tutor nem altera contadores, confidence, mastery ou evidence_status. Quantidade de explorações nunca constitui penalidade.
- **RF-05 Submissão:** Submit Answer cria intenção identificada, coleta SQL/justificativa conforme modalidade, executa quando necessário, avalia e persiste evidência + estado exatamente uma vez. Respostas conceituais não exigem SQL. Mesma resposta pode ser uma nova tentativa apenas com novo clique intencional.
- **RF-06 Conversa:** responder perguntas do tutor e pedir dicas por chat do exercício. Chat não é submissão e não comprova domínio. Somente uma nova Submit Answer atualiza evidência pedagógica. Política de ajuda controla escalonamento e revelação.
- **RF-07 Progresso:** estado por subcompetência, com mastery_score, evidence_status e confidence distintos; preservar competências não afetadas. Exibir evidências, foco, pendências e snapshots.
- **RF-08 Navegação:** um exercício apresentado de cada vez. Após avaliação, Next Exercise executa a próxima decisão; não troca sozinho durante rerun. Skip encerra como skipped sem sucesso/falha, e pede outro cenário. Encerrar gera snapshot sem novo exercício.
- **RF-09 Retomada:** recuperar sessão, contrato imutável, dados, rascunho salvo, feedback, ajuda e operações pendentes. Mesma versão deve reconstruir o mesmo ambiente, sem gerar outro exercício.
- **RF-10 Contingência:** sem LLM, Run SQL e avaliação SQL determinística continuam; feedback usa template. Avaliações conceituais ficam pending_review, sem nota inventada. Catálogo local serve somente fallback validado; sem opção compatível, manter sessão e informar indisponibilidade.
- **RF-11 Honestidade:** distinguir evidência real de interpretação estática e falha de infraestrutura de erro do aluno. Avaliação sobre datasets é evidência limitada, não prova universal de equivalência.
- **RF-12 Checkpoints:** gerar após cinco exercícios finalizados, promoção a validated/mastered, mudança de estratégia/ramo, troca de objetivo ou encerramento; deduplicar eventos simultâneos.

## Aceite obrigatório

| ID | Cenário observável |
|---|---|
| AC-01 | Inicialização local cria estruturas e verifica papéis; Streamlit abre em loopback |
| AC-02 | Solicitar segunda sessão preserva unicidade; troca de objetivo mantém perfil |
| AC-03 | LLM gera contrato e tabelas/dados são preparados antes do enunciado |
| AC-04 | Contrato inválido é reparado/rejeitado; nunca vira exercício ativo |
| AC-05 | Run válido e inválido não alteram nenhuma métrica pedagógica |
| AC-06 | Submit correta/incorreta produz evidência e uma única atualização |
| AC-07 | Reinício/rerun/reclique não duplicam submissão ou progresso |
| AC-08 | Prioridades A–F passam todos os casos em tutor_prompt.md |
| AC-09 | Mudança de objetivo reutiliza competência validada/high sem reteste automático |
| AC-10 | Retenção, regressão e checkpoints seguem learning_state.md |
| AC-11 | UI cobre os três formatos de resposta, chat, dicas e avanço explícito |
| AC-12 | Solução privada só aparece por Show Solution autorizado; não comprova domínio |
| AC-13 | Comparação preserva duplicatas/NULL/ordem declarada; nunca aprova truncamento |
| AC-14 | SQL equivalentes são aceitos; estrutura obrigatória é verificada apenas quando declarada |
| AC-15 | Execução do aluno não alcança state/hidden, escrita, funções proibidas ou recursos do host |
| AC-16 | Queda de LLM, PostgreSQL, timeout e limite não geram falsa evidência negativa |
| AC-17 | Alias autorizado funciona via normalização auditada; limitação não vira erro conceitual |
| AC-18 | EXPLANATION e PLAN_ANALYSIS usam rubrica; ausência de LLM deixa pending_review |
| AC-19 | Árvore provisória não altera registro oficial; capacidades reservadas não são geradas |
| AC-20 | Fluxo completo usa LLM real configurado e PostgreSQL real, além dos testes com fakes |

## Decisões de engenharia desta revisão

- Persistência em PostgreSQL, com schema de estado separado do ambiente descartável; não usar JSON local concorrente como outra fonte de verdade.
- Python 3.12 como baseline; bibliotecas e dependências travadas na fase T01.
- Usar cliente HTTP de chat compatível com configuração de endpoint/modelo, sem exigir fornecedor específico. Fake adapter apenas para testes.
- O core pedagógico continua genérico. Limiares da política de evidência, capacidades e configuração operacional são detalhados nos documentos correspondentes.
- Não entram multiusuário, backend remoto, RAG, microsserviços, DDL livre do aluno ou controle de infraestrutura pelo LLM.
