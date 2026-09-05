# SQL Adaptive Learning Tutor

Especificação de uma aplicação local, single-user, em Python + Streamlit + PostgreSQL. O LLM seleciona cenários pedagógicos e gera exercícios declarativos; a aplicação valida contratos, prepara dados, executa SQL e aplica as regras de estado.

Status: documentação revisada; aplicação ainda não implementada. Todas as tarefas de implementação estão pendentes.

## Invariantes

- No máximo uma sessão ativa; exatamente uma enquanto houver aprendizagem em andamento.
- Perfil permanente do aluno separado do estado operacional de cada objetivo.
- `Run SQL` explora sem avaliar; `Submit Answer` registra uma tentativa avaliada.
- Política adaptativa original, com precedência de confiança sobre domínio.
- Interface, enunciados, feedback e prompt do tutor em en-US; documentação de engenharia em português.
- Processo Streamlit local, PostgreSQL local, sem FastAPI, microsserviços ou autenticação. O provedor LLM pode ser remoto.

## Ordem de leitura

1. [Requisitos e decisões de escopo](docs/requirements.md)
2. [Prompt e política adaptativa](docs/tutor_prompt.md)
3. [Árvores de competências](docs/skill_trees.md)
4. [Estado e transições](docs/learning_state.md)
5. [Contrato de exercício e avaliação](docs/exercise_contract.md)
6. [Protocolo de chamadas e respostas](docs/runtime_contracts.md)
7. [Arquitetura, segurança e recuperação](docs/architecture.md)
8. [Tarefas e critérios de aceite](docs/tasks.md)

Cada assunto tem uma fonte normativa indicada acima. Exemplos devem obedecer aos contratos; não são regras alternativas. Alterações que afetem outro documento exigem atualização conjunta. [AGENTS.md](AGENTS.md) orienta o agente implementador.

## Origem

Conversa de referência: `6a9bdf10-1f64-83e9-a95d-b0d61fe5fc7d`, originalmente “Criar tutor adaptativo SQL”. Esta revisão substitui a primeira especificação, que omitiu partes do comportamento aprovado. A política foi consolidada a partir das decisões e trechos recuperados, incluindo versões anteriores completas para checkpoints e retenção. Não é uma transcrição literal integral do último prompt, cujo retorno estava truncado.

Limites numéricos, mecanismos transacionais, desempates, esquemas de mensagens e limiares de evidência são decisões de engenharia desta revisão. Não são apresentados como texto original da conversa.
