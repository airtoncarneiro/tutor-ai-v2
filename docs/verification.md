# Verificação do MVP

Última verificação: 2026-09-06. Este documento não substitui os critérios de
aceite; registra a fronteira entre comportamento comprovado e trabalho ainda
necessário.

## Comprovado localmente

- Configuração obrigatória, URLs PostgreSQL e correspondência de senhas são
  validadas sem imprimir segredos.
- Dependências da aplicação estão fixadas no `pyproject.toml`,
  `requirements.txt` e `requirements.lock` para Python 3.12.
- Bootstrap/migração usa o owner somente em `python -m sql_tutor`; a UI não
  executa migrações nem usa `DATABASE_ADMIN_URL`.
- Migração idempotente, singleton profile, unicidade global de sessão ativa,
  FKs de sessão/run/operação/submissão/evidência e recuperação de operações
  pendentes.
- Provisionamento declarativo em `exercise` e `exercise_validation`, com
  lock, grants reaplicados, preflight da referência e rollback que preserva o
  ambiente anterior quando o preflight falha.
- Runner acessa somente `exercise`; evaluator acessa `exercise` e
  `exercise_validation`, sem acesso a `tutor_state`.
- Parser AST rejeita múltiplos statements, DML/DDL, `SELECT INTO`, locks,
  schemas protegidos e funções não permitidas.
- Aliases registrados de `HAVING` e referências laterais simples são
  normalizados para PostgreSQL, mantendo `submitted_sql`, `executed_sql` e
  identificadores de extensão separados.
- Execução read-only com timeout, lock timeout, limite de linhas/bytes,
  preview e classificação de erro.
- Comparação determinística com duplicatas, ordem declarada, `NULL` e
  `Decimal`; referência e constraints são pré-validadas.
- A constraint de agregado valida função, argumento e agrupamento, mas não
  obriga alias de saída quando o contrato não o declara; qualificação de tabela
  continua sendo exigida somente quando necessária para resolver ambiguidade.
- `Run SQL` não cria submissão nem altera métricas; `Submit Answer` persiste
  operação, avaliação, estado de skill e evidência de forma transacional.
- Replay do mesmo `action_id` não duplica operação, submissão, evidência ou
  dica.
- Fallback determinístico do tutor, feedback persistido e chat sem efeito
  pedagógico; transporte HTTP remoto e retry finito estão implementados.
- Contratos determinísticos de `EXPLANATION_ONLY` e `PLAN_ANALYSIS`, avaliação
  rubricada com verificação de evidência textual e EXPLAIN JSON real foram
  validados.
- `Retry Review` reutiliza a submissão pendente e só aplica tentativa/evidência
  quando uma revisão válida termina.
- `Save Draft` e `Close Session` são operações persistidas e idempotentes; o
  encerramento gera snapshot/checkpoint.
- O fluxo real `pending_review` → `Retry Review` foi validado com PostgreSQL e
  um double LLM: uma submissão e um evento de evidência foram persistidos.
- Falhas e dicas persistidas foram recuperadas em uma nova instância da
  aplicação; `Show Solution` respeitou os contadores recuperados.
- Streamlit inicia em loopback e expõe o fluxo básico de objetivo, modo,
  exercício, Run, Submit, Hint, chat, solução, avanço, skip, draft e
  encerramento.
- A tela foi inspecionada no navegador local e confirmou os controles e campos
  principais; o comando direto `streamlit run sql_tutor/app.py` também foi
  reiniciado após a correção dos imports.
- O `streamlit.testing.v1.AppTest` possui injeção determinística de configuração
  e aplicação. Cinco cenários cobrem `SQL_ONLY`, `SQL_PLUS_REASONING`,
  `EXPLANATION_ONLY`, separação Run/Submit, dataframe, comandos da tela e
  `pending_review`/`Retry Review`, sem PostgreSQL e sem rede.
- Uma fixture pytest iniciou PostgreSQL 17.6 descartável com as roles reais,
  aplicou a migration e removeu o contêiner ao final. O cenário confirmou
  criação e retomada da mesma sessão, persistência de rascunho, Run/Submit
  separados, avaliação visível/oculta, idempotência, conflito de payload e
  versionamento imutável de contratos usando `FakeLLM`.
- Compose usa a convenção escolhida `dataforge-ai-lab`/`SQL_MENTOR_*` e mantém
  compatibilidade com nomes `TUTOR_*` já existentes.
- Duas aberturas concorrentes foram executadas contra o PostgreSQL real e
  retomaram o mesmo identificador de sessão ativa.
- O catálogo agora inclui fallbacks v2 para agregação, window functions e CTE
  recursiva, explicação e análise de plano; os cenários SQL e o plano foram
  provisionados e avaliados no PostgreSQL real.
- Índices declarados no contrato são compilados no schema do exercício, e a
  publicação remove tabelas antigas que não pertencem ao novo contrato.
- Resumo de sessão possui operação própria, fallback local e não altera o
  estado pedagógico; respostas de feedback/chat são rejeitadas quando excedem
  o teto de dicas, introduzem skills não declaradas ou vazam SQL privado.
- O formato shorthand observado no provedor LLM possui adaptador explícito
  para v2; a conversão continua sujeita à validação estrita do contrato e do
  preflight antes de qualquer publicação.
- O smoke real de geração foi executado com o modelo configurado e retornou
  contrato aceito (`sales_by_customer`).
- O smoke real completo passou com código 0 nos estágios geração →
  provisionamento → execução visível/oculta → avaliação correta → feedback;
  o fixture padrão foi restaurado ao final.
- O smoke adaptativo passou em uma base temporária: submissão correta,
  atualização de evidência, chamada do LLM real e criação de contrato/run
  independente para o próximo exercício; a base temporária foi removida.
- Um probe independente confirmou que o endpoint configurado retorna JSON
  compatível com Structured Outputs para um schema estrito mínimo.
- O cliente LLM passou a enviar JSON Schema estrito nas operações com modelos
  fechados e, no OpenRouter, exige um provedor que declare suporte aos
  parâmetros estruturados.
- A UI informa se há modelo remoto configurado e mantém explícita a
  disponibilidade do fallback local.
- As operações `decompose_goal`, `select_next` e `review_exercise` possuem
  implementação determinística limitada ao registro oficial do MVP; elas não
  publicam contratos nem alteram o estado por si mesmas.
- O script `scripts/smoke_llm.py` fornece verificações reproduzíveis da
  geração remota e, com `--full`, do fluxo de provisionamento, execução,
  avaliação e feedback, sem imprimir credenciais ou payloads privados.
- Resultados incompletos por limite e erros de permissão/infraestrutura no
  dataset oculto são classificados como `inconclusive`, sem penalizar o aluno.
- Rascunho salvo é recarregado na retomada; a UI exibe progresso por
  competência e oferece resumo de sessão sem alterar o estado pedagógico.
- A UI aceita e persiste declaração opcional de conhecimento na sessão ativa e
  exibe evidências recentes filtradas pelo perfil correto.
- A UI exibe detalhes de cada evidência recente, incluindo exercício, contexto,
  origem, assistência, SQL/resposta enviada, avaliação e estados da skill antes
  e depois do evento.
- Sem sessão ativa, a UI solicita o objetivo antes de criar a sessão e gera o
  primeiro exercício pelo LLM (ou fallback compatível); com sessão ativa,
  retoma o exercício persistido sem regenerá-lo.
- Submissões têm rollback conjunto comprovado no PostgreSQL real após falha
  injetada; `Next Exercise` também rejeita resposta LLM tardia quando a revisão
  da sessão mudou.
- Os fluxos de rascunho e revelação respeitam `EXPLANATION_ONLY`, sem perder a
  resposta textual nem tentar renderizar um SQL inexistente.

## Comandos e resultados

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m "not postgres and not browser and not real_llm" -q
65 passed

PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m apptest -q
5 passed

RUN_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m postgres -q
1 passed

.venv/bin/python -m sql_tutor
Database initialized.

Streamlit /_stcore/health
ok
```

Também foram executados smoke tests no PostgreSQL real para submissão correta,
idempotência, persistência de evidência, troca de exercício, limites de
permissão e rollback do preflight.

Os três comandos pytest acima não fizeram chamadas a uma API LLM paga. A suíte
de navegador/Playwright não foi executada nem ampliada nesta entrega porque
corresponde ao item 5, explicitamente adiado.

A matriz reproduzível `scripts/security_matrix.py` também foi executada contra o
PostgreSQL real: ownership de provisionamento do papel `app`, grants/denials
dos papéis restritos `runner` e `evaluator`, bloqueios do AST e execução
separada dos datasets visível e oculto passaram. O papel `app` não é usado para
executar SQL do aluno; por ser proprietário dos objetos, ele consegue ler os
schemas de exercício durante o provisionamento.

## Limitações explícitas

- A política A–F está implementada no núcleo puro e a transição para o próximo
  exercício já considera prioridade global, aging, competência elegível,
  dificuldade e tipo de evidência; ainda não há uma bateria completa de
  cenários de longa duração na UI.
- A normalização de extensões de dialeto e lineage completo de aliases ainda é
  uma capacidade reservada.
- `EXPLANATION_ONLY` e `SQL_PLUS_REASONING` têm cobertura AppTest; a automação
  de navegador real para todas as modalidades permanece no item 5.
- A seleção global e os parâmetros de transição também são cobertos por testes
  determinísticos; a transição real foi validada pelo smoke adaptativo em base
  descartável.
- Não foi feita automação de interação completa no navegador; o healthcheck do
  Streamlit comprova inicialização, não todos os cliques da UI.
