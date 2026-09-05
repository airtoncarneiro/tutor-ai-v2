# ExerciseContract v2

Fonte normativa para exercício, provisionamento e avaliação. LLM retorna JSON; catálogo pode usar YAML equivalente. Pydantic deve usar extra=forbid, enums fechados e rejeitar campos/tipos desconhecidos em qualquer nível. Nada de DDL bruto de provisionamento.

## Tipos e campos

Todos os campos abaixo são obrigatórios salvo indicação explícita de null/default. Identificadores de tabela/coluna/index/alias: ASCII snake_case, regex `^[a-z][a-z0-9_]{0,47}$`, sem nomes reservados de schemas. Skill keys seguem skill_trees.md.

- schema_version: inteiro literal 2.
- exercise_id: identificador lógico atribuído pelo aplicativo; resposta LLM deve ecoar o valor fornecido.
- version: inteiro >=1 atribuído pelo aplicativo.
- task: title/statement em en-US (1..200 / 1..6000 caracteres), primary_skill existente, secondary_skills lista única (0..5), difficulty inteiro 1..5, response_mode enum, context_tag identificador, evidence_kind enum isolated/transfer/composed/delayed_retrieval, expected_evidence lista não vazia de frases testáveis, hidden_variables lista de objetos {name, purpose}.
- environment: null em EXPLANATION; caso contrário objeto descrito abaixo.
- validation: união discriminada por mode.
- pedagogy: max_hint_level inteiro 0..3, allow_solution_reveal bool.
- private: objeto por modalidade descrito abaixo.

Compatibilidades:
| response_mode | validation.mode | environment | Entradas avaliadas |
|---|---|---|---|
| SQL_ONLY | RESULT_EQUIVALENCE | AUTO_SETUP | SQL |
| SQL_PLUS_REASONING | RESULT_EQUIVALENCE | AUTO_SETUP | SQL + rubrica de justificativa |
| EXPLANATION_ONLY | EXPLANATION | null | Texto |
| SQL_PLUS_REASONING | PLAN_ANALYSIS | AUTO_SETUP | SQL executável + justificativa do plano observado |
| EXPLANATION_ONLY | PLAN_ANALYSIS | AUTO_SETUP | Texto sobre plano real de uma consulta fornecida |

Outras combinações falham unsupported_capability. EXECUTION_SUCCESS, PARTIAL_SETUP e LEARNER_SETUP não são valores aceitos em contratos MVP; constam apenas do roadmap de capacidades.

## Environment

Objeto {engine: PostgreSQL, mode: AUTO_SETUP, tables, visible_data, hidden_data}.
- tables: 1..5 objetos {name, columns, primary_key, indexes}.
- columns: 1..20 objetos {name, type, nullable}; type enum integer/bigint/numeric/text/boolean/date. numeric é NUMERIC(18,2); nenhuma expressão de tipo arbitrária.
- primary_key: lista de nomes existentes, vazia permitida; colunas PK devem ser NOT NULL.
- indexes: lista (0..5 por tabela) de {name, columns}; só btree simples não-unique, colunas existentes. Índices não possuem expressão, predicate ou DDL.
- visible_data/hidden_data: mapas com exatamente as tabelas declaradas. Cada valor é lista de linhas posicionais na ordem de columns; 0..1000 linhas somadas por dataset.
- integer/bigint: JSON integer dentro do alcance correspondente; numeric: string decimal com até duas casas; boolean: JSON bool; date: ISO YYYY-MM-DD válida; text: string até 1000 caracteres; NULL só em colunas nullable.
- Linhas atendem PK e aridade. Dois datasets independentes, não concatenação. hidden_data só obrigatório/não vazio para RESULT_EQUIVALENCE; para PLAN_ANALYSIS usar mapas vazios de linhas.
- Não aceitar objetos de banco, schemas, extensões, SQL de seed ou comandos de host por texto.
- Os dados ocultos devem manter semântica e hidden_variables do enunciado. Nome “hidden_variables” designa fatores pedagógicos explicitamente controlados, não permissão para requisitos secretos.

Provisionamento usa schema fixo controlado pelo aplicativo. Não há mais target_fixture que dependa de dados previamente preparados. Hash do contrato inclui dados e referências privadas e é calculado pelo aplicativo.

## RESULT_EQUIVALENCE

validation:
- mode: RESULT_EQUIVALENCE.
- output_columns: lista ordenada não vazia de {name, type}; tipos integer/numeric/text/boolean/date. bigint pertence à família integer; aliases são requisitos publicados.
- order_sensitive: bool.
- numeric_tolerance: literal 0 no MVP. Decimal exato; tolerância não zero é rejeitada até existir comparador específico.
- constraints: lista de restrições obrigatórias suportadas.
- reasoning_rubric: [] em SQL_ONLY; lista não vazia em SQL_PLUS_REASONING.

private:
- reference_sql: SELECT PostgreSQL validado, 1..20000 caracteres.
- expected_visible_rows / expected_hidden_rows: linhas tipadas na ordem de output_columns; ambas presentes. Validar com a própria reference_sql antes de publicar.
- hints: exatamente três strings em en-US, níveis conceitual/estrutural/parcial; sem solução completa.
- solution_explanation: explicação pública autorizável em en-US.
- rubric_notes: string opcional apenas para avaliador, default "".

A query de referência usa nomes lógicos, que o aplicativo qualifica para o schema visível/oculto. Nunca interpolar nomes livres. SQL do aluno para dataset oculto passa pela mesma resolução AST: remapear apenas tabelas autorizadas para exercise_validation e executar com tutor_evaluator. O aluno não escolhe schema oculto.

### Comparação

Comparar quantidades e famílias de colunas, aliases declarados e valores em ordem de colunas. integer/numeric são comparáveis por Decimal exato; boolean não é inteiro. Textos/capitalização/espaços são exatos, sem strip/casefold. Datas normalizadas como ISO. NULL equivale somente a NULL.

order_sensitive=false compara multiconjunto de linhas, preservando multiplicidade; nunca set simples. true compara sequência inteira e o enunciado deve exigir ordenação total, inclusive desempates. Empty vs empty é correto só se os demais checks passarem; geração deve incluir ao menos um resultado não vazio em algum dataset.

Todos os datasets precisam de resultado completo. Excesso de linhas/bytes ou timeout -> inconclusive; não corrigir consulta do aluno adicionando LIMIT. Erro/limite na referência é invalid_exercise e nunca erro do aluno.

Não exigir forma textual igual à referência. Uma constraint estrutural só pode tornar a resposta incorreta se for exigência explícita do enunciado/objetivo público. Estilo, legibilidade e eficiência são sugestões se não houver critério anunciado.

## Restrições estruturais MVP

Objeto base {id, type, ...campos}, id único. Todas são required; não existe severity com semântica indefinida. output_columns é parte da validação, não uma constraint duplicada.

| type | Campos adicionais | Semântica |
|---|---|---|
| uses_table | table | Existe referência à tabela autorizada no caminho que alimenta o resultado |
| grouped_aggregate | function (count/sum/avg/min/max), argument (table.column ou * só count), group_by (lista table.column), output_alias | Saída indicada deriva da agregação declarada, sem OVER, com conjunto exato de chaves de agrupamento |
| window_function | function (row_number/rank/dense_rank/lag/lead/sum/avg/count/min/max), output_alias | Saída indicada depende dessa função com OVER |
| recursive_cte | cte_name nullable | Há CTE recursiva autorreferente que alimenta a saída; se nome fornecido, corresponde a ela |

Resolver aliases, escopos e lineage em CTE/subconsulta usados pelo resultado; presença textual em comentário/CTE morto não satisfaz restrição. Não é necessário resolver equivalência algébrica geral. AST suportada mas lineage inconclusiva -> inconclusive, nunca falha conceitual automática. Tipo de constraint desconhecido -> invalid_contract/unsupported_constraint na geração.

filter, join, result_predicate e required_columns não são tipos aceitos nesta versão: comportamento pode ser avaliado por resultados; se a estrutura específica for objetivo e não houver validator, usar EXPLANATION ou informar capacidade ausente. Não gerar constraint genérica sem implementação.

Regras de coerência: janela como primary_skill em SQL executável exige window_function; recursão como objetivo estrutural exige recursive_cte; grouped_aggregate não pode apontar coluna/tabela inexistente. Reference_sql deve satisfazer todas as constraints.

## EXPLANATION e PLAN_ANALYSIS

Rubrica: lista de 1..6 objetos {id, criterion, required, skill_key}. criterion é requisito público em en-US; pelo menos um required deve referir primary_skill. Cada critério avaliado como met/partial/not_met/not_assessable e acompanhado de evidência curta da resposta.

EXPLANATION:
- validation = {mode: EXPLANATION, rubric: [...]}
- environment=null.
- private={reference_explanation, hints, solution_explanation}; hints mantém três strings.
- Nenhuma execution fact pode ser inventada. Não usar SELECT de referência desnecessário.

PLAN_ANALYSIS:
- validation = {mode: PLAN_ANALYSIS, rubric: [...], supplied_query: string|null}.
- Para EXPLANATION_ONLY, supplied_query é obrigatório e público; obter EXPLAIN JSON antes de mostrar o exercício.
- Para SQL_PLUS_REASONING, supplied_query=null; plano vem do SQL validado do aluno. Critérios avaliam o plano obtido, não um plano ideal inventado.
- private={reference_sql, reference_explanation, hints, solution_explanation}. Reference_sql é a query de referência do cenário e passa preflight.
- Não obrigar índice específico/tempo sem garantia verificável no ambiente. Opções do plano podem variar; rubrica deve avaliar interpretação da evidência real.

## Resultado agregado

EvaluationResult está em runtime_contracts.md. Decisão:
- SQL_ONLY: correct se todos os datasets/constraints passam; incorrect se algum requisito obrigatório falha de modo comprovado.
- SQL_PLUS_REASONING + RESULT_EQUIVALENCE: SQL incorrect prevalece sobre opinião LLM; SQL correct exige todos os critérios required da rubrica met para correct. Algum partial -> partial; not_met -> incorrect.
- EXPLANATION/PLAN_ANALYSIS: todos required met -> correct; algum not_met -> incorrect; caso contrário algum partial -> partial.
- required not_assessable, LLM indisponível/inválido ou evidência insuficiente -> pending_review; sem atualização até revisão válida.
- SQL com erro atribuível ao aluno -> learner_sql_error; acesso/operação proibida -> blocked. Falha de provisionamento/infraestrutura/transformação -> inconclusive.
- score de submissão: correct=1, partial=0.5, incorrect=0; demais null. Não confundir score com mastery_score.

## Exemplo completo executável de contrato

```json
{
  "schema_version": 2,
  "exercise_id": "sales_by_customer",
  "version": 1,
  "task": {
    "title": "Sales totals by customer",
    "statement": "Using GROUP BY and SUM, return customer_id and total_sales for each customer. Each row is a sale, and a customer may have multiple sales. Row order does not matter.",
    "primary_skill": "aggregation.grouping.group_by",
    "secondary_skills": ["aggregation.aggregate_functions.sum"],
    "difficulty": 1,
    "response_mode": "SQL_ONLY",
    "context_tag": "retail_sales_totals",
    "evidence_kind": "isolated",
    "expected_evidence": ["Group sale rows at customer granularity."],
    "hidden_variables": [{"name": "repeated_customer", "purpose": "Require grouping multiple sales per customer."}]
  },
  "environment": {
    "engine": "PostgreSQL",
    "mode": "AUTO_SETUP",
    "tables": [{
      "name": "sales",
      "columns": [
        {"name": "sale_id", "type": "integer", "nullable": false},
        {"name": "customer_id", "type": "integer", "nullable": false},
        {"name": "amount", "type": "numeric", "nullable": false}
      ],
      "primary_key": ["sale_id"],
      "indexes": []
    }],
    "visible_data": {"sales": [[1, 101, "500.00"], [2, 101, "300.00"], [3, 205, "900.00"]]},
    "hidden_data": {"sales": [[1, 7, "10.00"], [2, 7, "20.00"], [3, 8, "40.00"]]}
  },
  "validation": {
    "mode": "RESULT_EQUIVALENCE",
    "output_columns": [{"name": "customer_id", "type": "integer"}, {"name": "total_sales", "type": "numeric"}],
    "order_sensitive": false,
    "numeric_tolerance": 0,
    "constraints": [{
      "id": "grouped_sum",
      "type": "grouped_aggregate",
      "function": "sum",
      "argument": "sales.amount",
      "group_by": ["sales.customer_id"],
      "output_alias": "total_sales"
    }],
    "reasoning_rubric": []
  },
  "pedagogy": {"max_hint_level": 3, "allow_solution_reveal": true},
  "private": {
    "reference_sql": "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id",
    "expected_visible_rows": [[101, "800.00"], [205, "900.00"]],
    "expected_hidden_rows": [[7, "30.00"], [8, "40.00"]],
    "hints": [
      "Think about which entity should occupy one output row.",
      "The grouping key identifies the customer; aggregate the amounts inside each group.",
      "Start with SELECT customer_id and add the aggregate expression before grouping."
    ],
    "solution_explanation": "GROUP BY creates one group per customer; SUM combines the amounts in each group.",
    "rubric_notes": ""
  }
}
```

## Público, privado e validação da geração

Projeção pública allowlist: id/version, task.title/statement/primary_skill/secondary_skills/difficulty/response_mode/expected_evidence, schema com tipos, dados visíveis, requisitos de output/ordem/constraints, rubrica pública e supplied_query/plano quando cabíveis. Não serializar contrato inteiro nem private, hidden_data, expected_hidden_rows, notas, solução e thresholds internos.

Exceção: Show Solution autorizado monta resposta separada com reference_sql ou reference_explanation e solution_explanation; não altera projeção pública habitual.

Preflight verifica campos, limites, capacidades, habilidade/constraint, coerência de dados, referências, resultado esperado e enunciado. Pedagogical review pelo LLM pode apontar inconsistência de semântica; Python garante as verificações estruturais e execução, mas não prova intenção de negócio universalmente. Usar revisão estruturada na geração dentro do limite global de tentativas; problema não resolvido -> rejeição/fallback.

Catálogo fallback passa o mesmo preflight. Contrato inválido nunca é convertido silenciosamente em exercício mais simples.
