# Matriz de testes

Atualizada em 2026-09-06. Esta matriz separa o que foi demonstrado por testes
deterministicos do que depende de PostgreSQL, AppTest ou navegador. A existencia
de um teste Python nao valida a interface visual.

## Resumo executivo

O nucleo e os testes deterministas cobrem validacao estrita de contrato,
allowlist SQL, comparacao de resultados, politica de evidencia, retry HTTP e os
tres modos de resposta no Streamlit. A aplicacao possui factories injetaveis
para AppTest, e o pytest possui um PostgreSQL descartavel com roles reais para
validar persistencia sem usar o banco de desenvolvimento.

A lacuna deliberadamente mantida e a automacao Playwright do fluxo completo
(item 5). Tambem permanecem cenarios ampliados da matriz que nao fazem parte
desta entrega, como concorrencia repetida, falhas transacionais injetadas e
combinacoes pairwise de constraints.

Legenda: **coberto** = oracle executavel presente; **parcial** = parte do
cenario coberta; **nao coberto** = caso ainda sem teste; **impossivel** = falta
hook, fixture, credencial local ou isolamento.

## Cenarios

### A. Contratos e geracao

| ID | Cenario e oracle deterministico | Camada | Prioridade | Status | Teste/lacuna |
|---|---|---|---|---|---|
| A-01 | Contrato v2 valido passa `validate_contract` | unit | critica | coberto | `tests/test_core.py` |
| A-02 | Campo desconhecido gera `ValidationError` | unit | critica | coberto | `tests/contracts/test_invalid_fields.py` |
| A-03 | Enum, tipo e skill desconhecidos falham explicitamente | unit | critica | coberto | `tests/contracts/test_invalid_fields.py` |
| A-04 | Combinacao `SQL_ONLY` + `EXPLANATION` falha | unit | critica | coberto | `tests/contracts/test_invalid_fields.py` |
| A-05 | Alias de agregado pode ser omitido | unit | alta | coberto | `tests/contracts/test_invalid_fields.py` |
| A-06 | Visible/hidden, aridade, PK, indice e tipos invalidos | unit | alta | parcial | aridade/PK cobertas; limites de dados ainda sem matriz dedicada |
| A-07 | `reference_sql` invalida ou constraint desconhecida nao publica exercicio | unit/integracao | critica | parcial | review rejeita contrato; preflight real fica em PostgreSQL |
| A-08 | Conteudo privado, hash e contrato imutavel | integracao/PostgreSQL | critica | coberto | `tests/test_core.py` e `tests/state/test_repository_lifecycle.py` |
| A-09 | Mesmo id/version com hash igual reutiliza contrato; hash diferente aloca nova versao | PostgreSQL | critica | coberto | PostgreSQL descartavel em `tests/state/test_repository_lifecycle.py` |
| A-10 | Geracao esgota tentativas e usa fallback compativel sem relaxar contrato | unit | critica | coberto | `tests/test_core.py` |

**Pre-condicoes/fixtures:** payload derivado de `example_contract`, contrato
catalogado, double LLM sequencial e, para A-07--A-09, PostgreSQL descartavel.
O oracle e `validate_contract`, `contract_hash`, conteudo persistido e ausencia
de `private` em `public_projection`.

### B. SQL e avaliacao

| ID | Cenario e oracle deterministico | Camada | Prioridade | Status | Teste/lacuna |
|---|---|---|---|---|---|
| B-01 | Consulta correta e semanticamente equivalente passa | unit/integracao | critica | coberto | `tests/sql/test_sql_scenarios.py` |
| B-02 | Alias diferente ou ausente nao falha sem requisito publicado | unit | alta | coberto | `tests/test_core.py` |
| B-03 | GROUP BY exato, funcao/coluna incorreta e coluna extra | unit | critica | coberto | `tests/sql/test_sql_scenarios.py` |
| B-04 | CTE, JOIN ambiguo, window e recursive constraint | unit | alta | parcial | validators individuais existem; pairwise completo pendente |
| B-05 | Ordem, duplicatas, NULL e Decimal preservados | unit | critica | parcial | duplicatas/NULL/ordem cobertos; Decimal real pendente |
| B-06 | Resultado vazio, truncado, byte limit e timeout viram `inconclusive` | PostgreSQL | critica | parcial | resultado incompleto coberto; limites reais dependem de banco |
| B-07 | Erro do aluno difere de erro de infraestrutura | PostgreSQL | critica | parcial | classificacao implementada; matriz de conexao/SQLSTATE pendente |
| B-08 | Dataset visivel e oculto sao avaliados integralmente | PostgreSQL | critica | coberto | submissao correta no PostgreSQL descartavel |

**Estado que muda:** somente `Submit Answer` cria avaliacao/evidencia. **Estado
que nao muda:** `Run SQL` nao altera nota, mastery, confidence ou contadores.
O oracle nao aceita preview truncado como sucesso.

### C. Seguranca PostgreSQL

| ID | Cenario e oracle deterministico | Camada | Prioridade | Status | Teste/lacuna |
|---|---|---|---|---|---|
| C-01 | DML, DDL, DML em CTE e SELECT INTO bloqueados | unit | critica | coberto | `tests/sql/test_sql_scenarios.py` |
| C-02 | COPY, LOCK e multiplas instrucoes bloqueados | unit | critica | coberto | `tests/security/test_sql_security.py` |
| C-03 | schema protegido, `tutor_state`, hidden e search_path bypass bloqueados | unit/PostgreSQL | critica | parcial | AST coberto; grants exigem `scripts/security_matrix.py` |
| C-04 | `pg_sleep`, funcoes de arquivo/rede/admin bloqueadas | unit | critica | parcial | `pg_sleep` coberto; familias completas no script real |
| C-05 | runner so le exercise; evaluator le hidden mas nao tutor_state | PostgreSQL | critica | coberto | `scripts/security_matrix.py` |
| C-06 | rollback obrigatorio apos erro de execucao/setup | PostgreSQL | critica | parcial | smoke real registrado; teste de falha injetada recomendado |

Fixture necessaria: banco dedicado com roles `tutor_runner` e
`tutor_evaluator`, schema limpo e rollback verificavel. Custo alto; nao usar
PostgreSQL compartilhado.

### D. Estado e persistencia

| ID | Cenario e oracle deterministico | Camada | Prioridade | Status | Teste/lacuna |
|---|---|---|---|---|---|
| D-01 | Criacao, retomada e sessao unica | PostgreSQL | critica | coberto | nova instancia retoma os mesmos profile, session e run no banco descartavel |
| D-02 | Troca de objetivo preserva perfil e fecha sessao anterior | PostgreSQL | critica | parcial | implementacao/smoke; teste isolado pendente |
| D-03 | Run, submit, skip, draft, close, hint e reveal sao comandos distintos | integracao | critica | parcial | todos sao despachados no AppTest; Run/Submit tambem usam PostgreSQL real |
| D-04 | Mesmo action_id + mesmo payload e idempotente | PostgreSQL | critica | coberto | replay de Run, Draft e Submit sem duplicacao |
| D-05 | Mesmo action_id + payload diferente falha explicitamente | PostgreSQL | critica | coberto | conflitos de Run e Submit rejeitados |
| D-06 | Rerun, refresh e reinicio nao duplicam operacao | AppTest/PostgreSQL | critica | parcial | rerun e replay cobertos; refresh/reinicio real ficam para a camada de navegador |
| D-07 | pending_review e Retry Review reutilizam submission sem nota inventada | integracao | alta | parcial | smoke real registrado; teste dedicado pendente |
| D-08 | queda antes/depois do commit e resposta tardia/stale | PostgreSQL | critica | parcial | smoke de stale registrado; falhas transacionais pendentes |
| D-09 | dois avancos concorrentes preservam revision/lock | PostgreSQL | critica | parcial | concorrencia registrada; teste repetivel pendente |

Oracles: contagem de submissions/evidence/lifecycle, `revision`, estados
finais e hashes. Nenhum teste deve inferir sucesso apenas por ausencia de
excecao.

### E. LLM e contingencia

| ID | Cenario e oracle deterministico | Camada | Prioridade | Status | Teste/lacuna |
|---|---|---|---|---|---|
| E-01 | FakeLLM valido gera resposta conhecida | unit | alta | coberto | `sql_tutor.llm.FakeLLM`, `tests/test_core.py` |
| E-02 | JSON invalido, schema extra, resposta tardia e timeout | unit | critica | parcial | JSON/retry cobertos; atraso/stale pendentes |
| E-03 | 429/5xx repetem dentro do budget; 401/403 nao repetem | unit | critica | parcial | 429/401 cobertos; 5xx/403 recomendado |
| E-04 | fallback local nao altera skill/modalidade/evidence_kind | unit | critica | coberto | `tests/test_core.py` |
| E-05 | feedback/chat nao alteram nota ou estado pedagogico | unit/integracao | alta | parcial | safe response coberto; persistencia chat pendente |
| E-06 | pending_review tem score null; Retry Review exige rubrica valida | unit/integracao | critica | parcial | evaluator coberto; fluxo persistido pendente |
| E-07 | vazamento de SQL privado, skill nova ou score/mastery inventado | unit | critica | parcial | private SQL/conceito cobertos; mastery em todos envelopes pendente |

Todos os cenarios E usam FakeLLM ou `httpx.post` mockado. Nenhum chama
provedor pago. Smoke real, quando necessaria a AC-20, fica separado e usa
`RUN_REAL_LLM_TESTS=1`, cache local e no maximo uma chamada por cenario.

### F. Streamlit e navegador

| ID | Cenario | Camada | Prioridade | Status | Motivo/oracle |
|---|---|---|---|---|---|
| F-01 | Tela sem sessao, criacao de objetivo e sessao ativa | AppTest | critica | parcial | sessao ativa coberta; tela inicial sem sessao ainda nao possui cenario dedicado |
| F-02 | Retomada, campos, SQL_ONLY, SQL_PLUS_REASONING e EXPLANATION_ONLY | AppTest | critica | coberto | cinco cenarios deterministas em `tests/ui/test_app_test_flow.py` |
| F-03 | Run, Submit, Hint, Chat, Show Solution, Next, Skip, Draft, Close, Retry | AppTest | critica | coberto | cada comando e observado no double da aplicacao |
| F-04 | busy, pending_review, sucesso/erro, dataframe, vazio e truncado | AppTest | alta | parcial | pending_review, sucesso e dataframe cobertos; demais estados aguardam cenarios dedicados |
| F-05 | rerun/refresh preserva valores e nao duplica actions | AppTest | critica | parcial | reruns do AppTest e idempotencia PostgreSQL cobertos; refresh real pertence ao item 5 |
| F-06 | labels/roles, viewport desktop/mobile, CSS, responsividade e screenshots | browser E2E | alta | nao coberto | AppTest nao valida esses aspectos |
| F-07 | console errors, acessibilidade basica e ausencia de chamadas externas | browser E2E | alta | nao coberto | requer servidor FakeLLM local |

`tests/ui/test_app_test_flow.py` roda sem opt-in, com doubles locais e sem rede.
`tests/e2e/test_full_flow.py` permanece explicitamente opt-in. AppTest nao
valida CSS, viewport, responsividade, posicionamento, acessibilidade visual ou
comportamento real do browser.

## Rastreabilidade requisito -> cenario -> teste

| Requisito/aceite | Cenarios | Evidencia atual | Lacuna principal |
|---|---|---|---|
| RF-03 / AC-04 | A-01..A-10 | contratos, review e fallback | preflight parametrizado |
| RF-04/05 / AC-05..07 | B-01..B-08, D-03..D-06 | core/evaluator/repository | ciclo completo PostgreSQL |
| RF-10/11 / AC-15..18 | C-01..C-06, E-01..E-07 | AST, adapter e security script | falhas e envelopes completos |
| RF-01/08/09 / AC-01/02/11/12 | D-01..D-09, F-01..F-05 | smoke e implementacao | AppTest isolado |
| RF-02/07/12 / AC-08..10/19 | D-02/D-08/D-09, testes de policy | `tests/state/test_learning_transitions.py` e core | longa duracao e checkpoints |
| AC-20 | E-03, E-04, B-08, F-06/F-07 | smoke real documentado | executar separado, nunca no default |

## Fixtures e doubles

- `example_contract()` e catalogo sao fontes de contratos validos; mutacoes
  devem ser aplicadas sobre `model_dump(mode="json")`.
- FakeLLM deve expor sequencia deterministica, contador de chamadas, payloads
  invalidos e erros configuraveis. Nao usar a resposta do LLM como oracle.
- `postgres_settings` inicia um PostgreSQL 17.6 descartavel, executa o bootstrap
  de roles e a migration real, publica em porta aleatoria e remove o container
  ao final. Requer Docker/Colima ativo e `RUN_POSTGRES_TESTS=1`.
- AppTest recebe factories de `Settings` e tutor por `sql_tutor.ui_runtime`.
  Em producao, as factories continuam apontando para `Settings.from_env` e
  `TutorApplication`; nos testes, nenhum banco ou LLM remoto e aberto.
- Browser E2E deve apontar `LLM_BASE_URL` para um endpoint local fake, iniciar
  Streamlit em loopback e capturar screenshot, console e requests.

## Ordem e comandos

As suites sao separadas por marcadores; a suite padrao e AppTest nao usam rede
nem API paga. PostgreSQL, navegador e provedor real sao opt-in independentes.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m "not postgres and not browser and not real_llm" -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m apptest -q
RUN_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m postgres -q
RUN_BROWSER_E2E=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m browser -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/smoke_llm.py --full
```

O comando `browser` apenas reserva a camada do item 5 nesta entrega. O marcador
`real_llm` reserva futuros testes pytest do provedor. O smoke LLM e opcional,
pode consumir API paga e nunca faz parte da suite padrao.

## Criterios objetivos de aprovacao

- Todos os cenarios criticos A-01..A-05, A-07..A-10, B-01..B-03, C-01..C-05,
  D-04, E-03, E-06 e F-01..F-05 tem oracle deterministico e passam no ambiente
  declarado.
- SQL truncado, timeout, infraestrutura, pending review e stale nunca reduzem
  mastery nem recebem score inventado.
- Cada submission finalizada tem no maximo um evento por skill e replay do
  action_id nao cria novos eventos.
- O teste PostgreSQL usa roles restritas e rollback verificavel.
- AppTest passa os fluxos das tres modalidades, mas E2E ainda valida browser,
  viewport, console, acessibilidade e requests externos separadamente.
- Smoke com LLM real e PostgreSQL real e evidenciado fora da suite padrao; uma
  suite Python verde sozinha nao declara a interface validada.

## Arquivos de teste recomendados

Ja criados: `tests/contracts/test_invalid_fields.py`,
`tests/sql/test_sql_scenarios.py`, `tests/security/test_sql_security.py`,
`tests/state/test_learning_transitions.py`, `tests/llm/test_http_adapter.py`,
`tests/ui/test_app_test_flow.py` e `tests/e2e/test_full_flow.py`.

Ainda recomendados: `tests/contracts/test_preflight.py`,
`tests/sql/test_postgres_execution.py`, `tests/security/test_role_grants.py`,
`tests/llm/test_protocol_adversarial.py` e, depois desta entrega,
`tests/e2e/test_browser_flow.py` para concluir o item 5.
