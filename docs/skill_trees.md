# Skill tree registry

Registro v1, separado do core. Identificadores usam caminhos dot-separated; rótulos SQL preservam nomes usuais. A organização abaixo consolida árvores recuperadas da conversa, com identificadores normalizados para implementação.

```yaml
skill_tree_registry:
  aggregation: appendix_a
  window_functions: appendix_b
  recursive_cte: appendix_c
  query_performance: appendix_d
```

## appendix_a — aggregation

Folhas em ordem de desempate:
- aggregate_functions.count, aggregate_functions.sum, aggregate_functions.avg, aggregate_functions.min, aggregate_functions.max
- null_behavior
- grouping.group_by, grouping.multiple_columns, grouping.grouping_granularity
- filtering.where_before_aggregation, filtering.having_after_aggregation
- conditional_aggregation
- distinct_aggregation
- analytical_problems

Prefixar cada folha com aggregation. Exemplo: `aggregation.grouping.group_by`.

NULL e linhas repetidas entram apenas se a competência exigir ou se forem declarados no cenário. SUM não exige comportamento de NULL por acidente. Aliases autorizados não geram lacuna conceitual.

## appendix_b — window_functions

Folhas: over, partition_by, order_by, row_number, rank, dense_rank, lag, lead, aggregate_windows, frames. Prefixo `window_functions.`.

Empates devem ter intenção explícita; row_number determinístico exige critério de desempate quando a ordem exata for avaliada. Se primary_skill exige janela em tarefa SQL, o contrato precisa de constraint window_function sobre resultado efetivamente usado; SELECT simples não pode satisfazer essa competência.

## appendix_c — recursive_cte

Folhas:
- recursive_structure.anchor_member, recursive_structure.recursive_member, recursive_structure.recursive_reference
- iteration_semantics.working_set, iteration_semantics.result_accumulation
- set_semantics.union_vs_union_all
- termination.termination_condition, termination.depth_limiting
- cycle_handling.cycle_detection, cycle_handling.path_tracking
- traversal_patterns.hierarchical_traversal, traversal_patterns.graph_traversal

Prefixo `recursive_cte.`. Ciclos só são inseridos quando termination/cycle_handling fizer parte da evidência esperada. Timeout protege toda execução, mas não vira requisito oculto de avaliação. Conceitos que exigem arrays/CYCLE ainda fora da allowlist podem usar EXPLANATION_ONLY. Não gerar sintaxe não suportada como tarefa executável.

## appendix_d — query_performance

Folhas:
- execution_plan_analysis.node_types, execution_plan_analysis.cost_estimation
- indexing_strategies.btree, indexing_strategies.partial, indexing_strategies.expression, indexing_strategies.composite_ordering
- join_strategies.nested_loop, join_strategies.hash_join, join_strategies.merge_join
- memory_and_spill
- data_distribution.cardinality, data_distribution.selectivity, data_distribution.data_skew, data_distribution.table_size
- partitioning.partition_pruning, partitioning.partition_key_selection, partitioning.partition_granularity
- bottleneck_identification

Prefixo `query_performance.`. No MVP usar EXPLANATION ou PLAN_ANALYSIS. Índices parciais/de expressão, spill medido e particionamento físico são conceituais; não exigir que o provisionador os crie. Plano estimado não comprova tempo ou spill real.

## Relevância e pré-requisitos

Árvore representa conteúdo, não ordem obrigatória de reteste. Possíveis relações: grouping pode apoiar aggregate_windows; order_by pode apoiar rank; anchor_member pode apoiar recursive_member. O LLM só ativa prerequisite_blocking com evidência de submissão que nomeie a lacuna e como bloqueia a tarefa. Hipótese sem evidência concreta não altera perfil.

No MVP, observações sobre secondary_skills geram hipótese a verificar; somente primary_skill recebe atualização numérica. Ao confirmar bloqueio, criar diagnóstico focado no pré-requisito e, depois, retomar o foco salvo.

## Árvores provisórias

Para objetivo desconhecido, operação decompose_goal retorna no máximo 20 folhas únicas, descrição, response_modes e prerequisite_edges acíclicas. Validar IDs `[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*`, máximo 120 caracteres, nomes em inglês e capacidades existentes.

Guardar árvore somente na learning_session; namespace interno `provisional:<session_id>:<path>`. Não promover automaticamente a oficial nem mapear por semelhança textual para skill conhecida. Reutilização entre sessões provisórias só por mapeamento explícito salvo e revisado; perfis oficiais permanecem intactos.

GENERAL_ASSESSMENT usa as folhas oficiais suportadas. Ordem de amostragem e intervenção seguem tutor_prompt.md; registro não duplica política.
