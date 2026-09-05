# Arquitetura e operação local

## Estrutura de implementação

Um processo Streamlit chama serviços Python. Os componentes abaixo são módulos, não servidores.

```text
sql_tutor/
  app.py
  config.py
  models.py
  application.py
  sessions.py
  policy.py
  tutor.py
  llm.py
  exercises.py
  database.py
  dialects.py
  evaluator.py
  repositories.py
migrations/
catalog/
tests/
```

app.py renderiza interface; application.py orquestra casos de uso. policy.py implementa a política normativa; tutor.py compõe prompts e valida propostas. llm.py encapsula transporte. exercises.py valida/compila contratos; database.py provisiona/executa; dialects.py normaliza extensões. evaluator.py compara resultados e valida rubricas. repositories.py concentra persistência.

Stack: Python 3.12, Streamlit, Pydantic v2, psycopg 3, SQLGlot para AST com validação de escopos, pytest. Migrações SQL numeradas com tabela de versões e checksum; sem ORM obrigatório. T01 fixa versões compatíveis e lockfile. Nenhuma versão “latest” fica sem pin no ambiente reprodutível.

## Banco, papéis e inicialização

Uma base dedicada local com schemas:
- `tutor_state`: perfil, sessões, contratos privados, evidências e operações.
- `exercise`: cenário visível atual, descartável.
- `exercise_validation`: dados ocultos, só avaliador.

Papéis separados sem herança automática de privilégios entre logins:
- `tutor_owner`: migrações e criação dos schemas; credencial só no comando de inicialização, fora da UI.
- `tutor_app`: DML em tutor_state; proprietário dos objetos de exercise e exercise_validation para provisionamento. Sem superuser, CREATEDB, CREATEROLE ou privilégios de host.
- `tutor_runner`: USAGE + SELECT somente em exercise; sem CREATE, TEMP, propriedade ou escrita.
- `tutor_evaluator`: USAGE + SELECT em exercise e exercise_validation; sem acesso a tutor_state.

tutor_app lê o contrato e passa apenas SQL/estrutura necessários ao evaluator. SQL do aluno nunca usa tutor_app. Revogar acessos implícitos de PUBLIC na base dedicada (incluindo TEMP e CREATE no public) e conceder explicitamente o necessário. Novos objetos recebem os grants explícitos durante setup.

Exceção controlada de membership: tutor_app pode assumir tutor_evaluator via SET ROLE, sem herança automática. Durante o preflight dentro da transação de setup, usar a mesma conexão com SET LOCAL ROLE tutor_evaluator para que as tabelas ainda não confirmadas sejam visíveis sob privilégios restritos. Retornar ao papel original antes de salvar estado. Não usar outra conexão para validar tabelas não confirmadas. Esse preflight tem AST/timeout e apenas referência gerada validada; SQL do aluno continua exclusivamente nas conexões restritas de execução.

A aplicação não cria uma instância PostgreSQL. Fornecer configuração local por Docker Compose opcional, com porta vinculada a 127.0.0.1, volume próprio, e procedimento equivalente para instância já instalada. Inicialização pede conexão administrativa da base dedicada, cria papéis/migrações e verifica conexões restritas; não altera outras bases.

## Executor

Validar uma instrução AST de leitura, incluindo todas as CTEs/subqueries, tabelas, funções e escopos. Recusar DML em CTE, SELECT INTO, locks, COPY, CALL, comandos administrativos, referências a schemas externos e consultas de catálogo. Apenas tabelas declaradas no contrato e relações derivadas delas; SELECT de constantes é permitido, mas não satisfaz restrições pedagógicas sozinho.

Permitir funções iniciais: count, sum, avg, min, max, coalesce, nullif, abs, round, lower, upper, length, substring, date_trunc, extract, row_number, rank, dense_rank, lag, lead, first_value, last_value, nth_value. A sintaxe AST de cada uma deve ser tratada explicitamente; sem chamada dinâmica, funções de usuário ou resolução por search_path não controlado. Novas funções exigem registro/teste. Negar pg_sleep, funções de arquivos, rede, sequência e administração, mesmo dentro de SELECT.

Permitir operadores aritméticos/comparação/booleanos, CASE, IS NULL, IN/EXISTS, casts para tipos autorizados, UNION/UNION ALL, JOIN, GROUP BY/HAVING, DISTINCT, ORDER BY, LIMIT e janelas/CTEs de leitura dentro dos mesmos controles. Não confundir CASE ou CAST com função externa. SELECT * é expandido com schema conhecido na análise de lineage. Tipos/operadores fora do registro falham unsupported_capability sem evidência negativa.

Execução em conexão restrita, transação READ ONLY, timeouts locais e rollback obrigatório; conexão com erro é limpa/descartada. search_path fixo e AST qualificada pela aplicação. SELECT/CTE aprovado não implica segurança por si só. A transação read-only é uma camada adicional de proteção, conforme [PostgreSQL SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html).

Preview: buscar no máximo display_row_limit + 1; mostrar apenas display_row_limit e indicar truncamento. Avaliação: consumir integralmente até evaluation_row_limit + 1 e byte_limit; exceder qualquer limite gera inconclusive, nunca correct. Não injetar LIMIT na consulta avaliada, não comparar somente preview.

EXPLAIN é operação interna `EXPLAIN (FORMAT JSON)` sobre SELECT validado. MVP não executa EXPLAIN ANALYZE. Persistir o plano real, configurações relevantes e hash do dataset; não inferir desempenho medido apenas do custo estimado.

## Ciclo do ambiente

1. Policy + LLM produzem decisão e contrato candidato sem mudar exercício atual.
2. Validar JSON e capacidades; compilar nomes/tipos usando identificadores seguros e inserir dados com parâmetros.
3. Em transação local, obter lock global de operação e verificar versão da sessão.
4. Substituir SOMENTE exercise e exercise_validation, ambos schemas fixos da base dedicada; criar tabelas/índices/dados e grants. Nunca aceitar nome de schema de saída do LLM.
5. Validar solução de referência e resultados esperados nos dois datasets; referência deve passar os mesmos checks estruturais obrigatórios.
6. Marcar ready e vincular contrato/run/sessão na mesma transação; commit antes de apresentar.
7. Falha faz rollback: manter ambiente anterior e registrar erro de preparação separadamente.

Schema reset nunca toca tutor_state. Não resetar ao Run, Submit, chat ou rerun. Novo setup ocorre apenas no avanço, skip com sucessor pronto, ou reconstrução verificada na retomada. Toda reconstrução usa dados salvos, nunca aleatoriedade nova ou LLM.

Apenas uma operação executa no banco por vez: advisory lock de sessão mantido numa conexão dedicada do começo ao fim da execução/provisionamento. Operações de ciclo não correm em paralelo com SQL. Ao perder a conexão do lock, abortar a operação. Chamadas LLM acontecem fora desse lock; respostas tardias são descartadas usando session revision.

## Submissão e recuperação

- A UI gera action_id UUID por clique intencional, persiste a intenção e reutiliza o id no rerun/retry. Botões ficam desabilitados enquanto pendentes.
- Inserir operation pending com action_id UNIQUE, payload_hash e versão da sessão/run. Conflito com mesmo hash retorna operação existente; hash diferente falha explicitamente.
- Executar sob lock e coletar evidência. Em uma transação de estado, salvar avaliação, aplicar eventos pedagógicos, atualizar sessão/run e concluir operação. Unique por submission no evento impede dupla atualização.
- Submissão + evento + alteração de perfil devem confirmar juntos. Queda antes do commit permite retomar a mesma intenção; depois do commit apenas recarrega.
- Feedback LLM é posterior a esse commit em SQL_ONLY. Estado de feedback pending/ready/fallback/failed é independente; retry não reexecuta avaliação concluída.
- Em modalidades com rubrica, salvar evidência e pending_review primeiro. Após avaliação LLM válida, finalizar estado atomicamente. Queda/JSON inválido não inventa nota.
- Reinício converte operations running sem dono vivo em pending; nova execução read-only é permitida se contrato/dataset/revision não mudaram. Operações antigas de sessão encerrada viram stale sem efeito.
- Uma intenção concluída pode ser consultada por action_id. Rascunho salvo via Save Draft e em Run/Submit/chat; digitação não salva pode ser perdida.
- Corrigir contrato exige nova versão; nunca reavaliar histórico silenciosamente.

Persistência e máquinas de estado: [learning_state.md](learning_state.md).

## Extensões de dialeto autorizadas

Registro fechado: `redshift.lateral_alias_reference` e `redshift.having_alias_reference`. O segundo separa tecnicamente o exemplo de HAVING que a conversa agrupou sob o primeiro. Não assumir suporte ao dialeto Redshift inteiro.

Normalizador determinístico AST:
- Expandir referência a alias anterior da mesma lista SELECT, respeitando escopo; coluna de entrada com mesmo nome tem precedência, conforme [AWS SELECT list](https://docs.aws.amazon.com/redshift/latest/dg/r_SELECT_list.html).
- Expandir alias de agregado em HAVING no mesmo bloco, conforme o caso documentado em [AWS HAVING](https://docs.aws.amazon.com/redshift/latest/dg/r_HAVING_clause.html).
- Suportar identificadores simples, expressões determinísticas permitidas e aliases únicos; impedir expansão cíclica, forward reference e explosão acima de sql_max_chars.
- Casos ambíguos ou não suportados produzem dialect_unverified/inconclusive sem falha pedagógica; não alegar equivalência nem execução do texto original.
- Salvar submitted_sql, executed_sql, extension_ids e nota de adaptação. Mostrar ao aluno quando a forma compatível foi executada. Não exigir reescrita quando normalização segura existe.
- Consulta PostgreSQL nativa válida não deve ser modificada desnecessariamente. Validar AST novamente após normalização.
- Só erro comprovadamente do SQL do aluno é learner_sql_error. Falha da transformação é limitação da aplicação.

## Configuração e limites default

| Variável | Padrão / obrigação |
|---|---|
| DATABASE_APP_URL, DATABASE_RUNNER_URL, DATABASE_EVALUATOR_URL | Obrigatórias, destinos locais |
| DATABASE_ADMIN_URL | Somente bootstrap/migração; não carregada pela UI |
| LLM_BASE_URL, LLM_MODEL, LLM_API_KEY | Configuração do adaptador; segredo opcional só se endpoint dispensar |
| LLM_TIMEOUT_SECONDS | 30 por tentativa |
| LLM_MAX_ATTEMPTS | 3 totais por operação, incluindo reparo de contrato ou JSON |
| SQL_TIMEOUT_MS, SQL_LOCK_TIMEOUT_MS | 3000, 1000 |
| SQL_MAX_CHARS | 20000 |
| DISPLAY_ROW_LIMIT, EVALUATION_ROW_LIMIT | 200, 2000 |
| RESULT_BYTE_LIMIT | 2097152 por execução |
| MAX_TABLES, MAX_COLUMNS, MAX_SEED_ROWS | 5, 20 por tabela, 1000 por dataset |
| STREAMLIT_SERVER_ADDRESS | 127.0.0.1 |

Retries LLM apenas timeout/conexão/429/5xx ou resposta inválida; backoff 1s/2s dentro de no máximo três tentativas. 401/403/configuração falham sem retry. Sem retry aninhado no cliente HTTP. Não fazer chamada LLM a cada rerun.

## Privacidade e logs

Texto do aluno é dado não confiável; saída LLM também. Sem HTML não sanitizado no Streamlit. Mensagens públicas não recebem contrato privado por serialização genérica. A projeção pública é allowlist.

Chamadas remotas contêm enunciado, schema/dados sintéticos necessários, SQL submetido, justificativa, evidência limitada e perfil relevante; sem credenciais, tabelas internas ou histórico completo. Informar o destino configurado na UI.

Logs JSON com action/session/run/submission ids, estágio, duração, tipo de falha e versões. Sem credenciais, payload completo ou solução por padrão. SQL completo fica no histórico local protegido; feedback não inclui erro bruto de conexão. Não limpar histórico automaticamente. Segredos fora do Git; documentar .env.example e .gitignore na implementação.
