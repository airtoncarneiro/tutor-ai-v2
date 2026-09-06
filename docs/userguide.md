# User Guide — SQL Adaptive Tutor

Este guia mostra como instalar e abrir a aplicação localmente.

## Pré-requisitos

- macOS, Linux ou Windows com Docker Desktop;
- Python 3.12;
- Git;
- uma chave de um provedor LLM compatível com Structured Outputs, se quiser
  usar geração e feedback remotos. A aplicação também possui fallback local.

## 1. Clonar o projeto

```bash
git clone <URL_DO_REPOSITORIO> tutor-ai-v2
cd tutor-ai-v2
```

## 2. Criar o arquivo de configuração

```bash
cp .env.example .env
```

O `.env.example` já possui valores simples adequados para uma instalação local.
As URLs usam interpolação simples e reutilizam os valores definidos no início
do arquivo. Assim, cada senha, banco e porta é alterado uma única vez. Em geral,
você pode usar o arquivo sem editar as senhas. Abra `.env` apenas se precisar
trocar a porta, usar outro banco ou configurar um provedor LLM.

As URLs do banco já vêm preenchidas de forma consistente com o Compose. Altere
as quatro URLs `DATABASE_*_URL` somente se mudar a base, a porta ou os usuários.

Para habilitar o tutor remoto, defina:

- `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY` para habilitar o tutor remoto.

O modelo informado em `LLM_MODEL` precisa oferecer suporte a Structured
Outputs. Nunca publique ou versione o arquivo `.env`.

## 3. Iniciar o PostgreSQL

```bash
docker compose up -d --wait postgres
```

O banco fica disponível somente na máquina local. O volume `postgres_data`
preserva os dados entre reinicializações.

Também é possível usar o `Makefile` para executar as operações mais comuns:

```bash
make start          # inicia o PostgreSQL
make init           # inicia e prepara o banco
make run            # inicia o banco, prepara e abre o Streamlit
make status         # mostra o estado do container
make restart        # reinicia preservando os dados
make reset          # apaga o banco e começa novamente do zero
```

O `make reset` solicita confirmação antes de remover o volume. Para executar
sem a pergunta interativa, use `make reset CONFIRM=1`.

## 4. Instalar a aplicação

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Para instalar exatamente as versões registradas no projeto:

```bash
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e .
```

## 5. Preparar o banco

```bash
.venv/bin/python -m sql_tutor
```

Esse comando aplica as migrações e prepara o exercício inicial. Execute-o
novamente se precisar apenas confirmar que o banco está inicializado.

## 6. Abrir a aplicação

```bash
.venv/bin/streamlit run sql_tutor/app.py
```

Abra o endereço mostrado pelo Streamlit, normalmente
`http://127.0.0.1:8501`.

## 7. Usar a aplicação

1. Informe o objetivo de aprendizagem, se quiser alterá-lo.
2. Leia o exercício e o schema apresentado.
3. Use **Run SQL** para testar a consulta sem registrar uma tentativa.
4. Use **Submit Answer** para enviar a resposta à avaliação.
5. Consulte o feedback, as evidências e o progresso da competência.
6. Avance para o próximo exercício quando a aplicação liberar o botão.

Na primeira abertura sem uma sessão ativa, a aplicação pede o objetivo antes de
mostrar o exercício. O primeiro cenário é gerado para esse objetivo pelo LLM;
se o LLM não estiver disponível, um cenário compatível do catálogo local é
usado. Se já existir uma sessão ativa, a aplicação retoma o exercício salvo
automaticamente.

`Run SQL` e `Submit Answer` têm finalidades diferentes: executar uma consulta
para explorar não altera o domínio ou a confiança do aluno.

As ações principais aparecem na ordem **Run SQL**, **Submit Answer** e **Hint**.
Após uma execução, a tela informa o status, a quantidade de linhas e que o
resultado ainda não foi submetido. O apoio ao aluno fica separado do exercício:
é possível perguntar ao tutor e avançar progressivamente por **Show Hint**,
**Show Explanation** e **Show Full Solution**, quando a política autorizar.
Controles de sessão, como trocar objetivo, salvar rascunho, avançar, pular e
encerrar, ficam no painel lateral **Session controls**.

## Verificações opcionais

Suíte determinística padrão, sem PostgreSQL descartável, navegador ou API LLM:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m "not postgres and not browser and not real_llm" -q
```

Camadas separadas:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m apptest -q
RUN_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m postgres -q
RUN_BROWSER_E2E=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m browser -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/security_matrix.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/smoke_llm.py --full
```

AppTest usa doubles locais; a camada PostgreSQL cria e remove um contêiner
próprio. A camada de navegador está reservada para o item 5. O `smoke_llm.py`
exige um LLM real configurado e pode consumir API paga. O smoke adaptativo
abaixo também usa o provedor real:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/smoke_adaptive.py
```

## Parar o ambiente

Para fechar a aplicação, interrompa o processo do Streamlit. Para parar o
PostgreSQL:

```bash
docker compose stop postgres
```

Os dados permanecem no volume local.

## Reset completo do ambiente

Para reiniciar somente o PostgreSQL e preservar sessões, exercícios e demais
dados persistidos:

```bash
docker compose restart postgres
```

Para começar novamente do zero, removendo o container, o volume
`postgres_data`, as sessões, evidências e demais dados do banco:

```bash
docker compose down -v --remove-orphans
docker compose up -d --wait postgres
.venv/bin/python -m sql_tutor
```

Depois, abra a aplicação novamente:

```bash
.venv/bin/streamlit run sql_tutor/app.py
```

O comando `docker compose down -v` é destrutivo para os dados do PostgreSQL.
Ele não remove o arquivo `.env`. As roles e senhas serão recriadas usando os
valores atuais do `.env`; confirme as URLs `DATABASE_*_URL` antes de executar o
reset.

## Solução rápida de problemas

- **Erro de conexão:** confirme que o PostgreSQL está saudável e que as URLs
  `DATABASE_*_URL` apontam para a base correta.
- **Erro de senha:** confirme que a senha na URL corresponde à senha da role.
- **Tutor remoto indisponível:** confirme `LLM_BASE_URL`, `LLM_MODEL` e
  `LLM_API_KEY`; o fallback local continua disponível para o fluxo SQL.
- **Porta ocupada:** altere `SQL_MENTOR_POSTGRES_PORT` no `.env` e atualize as
  URLs do PostgreSQL para a mesma porta.
