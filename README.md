# SQL Adaptive Learning Tutor

Especificação de uma aplicação local, single-user, em Python + Streamlit + PostgreSQL. O LLM seleciona cenários pedagógicos e gera exercícios declarativos; a aplicação valida contratos, prepara dados, executa SQL e aplica as regras de estado.

Status: MVP vertical implementado e validado localmente; funcionalidades avançadas do backlog permanecem pendentes.

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

## Banco local para desenvolvimento

O PostgreSQL pode ser iniciado antecipadamente pelo Compose para que o agente
encontre o banco disponível durante a implementação:

```bash
cp .env.example .env
# edite as senhas do arquivo .env
docker compose up -d --wait postgres
```

O arquivo `.env` é ignorado pelo Git. O script
`docker/postgres/init/01-bootstrap-roles.sh` cria as roles, schemas e permissões
iniciais exigidos pela arquitetura. Esses scripts são executados pelo PostgreSQL
somente quando o volume `postgres_data` está vazio; mudanças posteriores no
bootstrap exigem uma migração explícita ou a recriação deliberada do ambiente
local.

Para configurar e verificar um provedor LLM remoto, consulte
[docs/llm_setup.md](docs/llm_setup.md).

O agente deve usar as URLs `DATABASE_*_URL` do `.env` conforme a operação:
estado da aplicação, execução restrita de SQL, avaliação ou administração/migração.
O usuário da aplicação não deve ser substituído pelo usuário proprietário do
cluster.

## Executar a aplicação

Com Python 3.12 instalado:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sql_tutor
.venv/bin/streamlit run sql_tutor/app.py
```

Para reproduzir as versões do ambiente validado, use `.venv/bin/pip install -r
requirements.lock` e instale o projeto em modo editável separadamente.

Testes automatizados:

```bash
.venv/bin/pytest
```

Matriz de segurança contra o PostgreSQL real:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/security_matrix.py
```

Smoke adaptativo com base temporária e LLM real:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/smoke_adaptive.py
```

O comando `python -m sql_tutor` aplica as migrações idempotentes e prepara o
fixture declarativo de demonstração. O banco deve estar saudável antes desse
comando.

O MVP atual cobre configuração, fixture declarativo, provisionamento dos dois
datasets, execução restrita, comparação determinística, persistência de
sessão/submissão, política adaptativa, recuperação de operações, os três
formatos pedagógicos e a interface Run/Submit. O fluxo real de geração,
provisionamento, execução, avaliação e feedback já foi validado. Permanecem
como validações finais a matriz completa de segurança e a geração real de um
segundo cenário adaptativo; veja [verification.md](docs/verification.md).

## Origem

Conversa de referência: `6a9bdf10-1f64-83e9-a95d-b0d61fe5fc7d`, originalmente “Criar tutor adaptativo SQL”. Esta revisão substitui a primeira especificação, que omitiu partes do comportamento aprovado. A política foi consolidada a partir das decisões e trechos recuperados, incluindo versões anteriores completas para checkpoints e retenção. Não é uma transcrição literal integral do último prompt, cujo retorno estava truncado.

Limites numéricos, mecanismos transacionais, desempates, esquemas de mensagens e limiares de evidência são decisões de engenharia desta revisão. Não são apresentados como texto original da conversa.
