# Configuração e smoke test do LLM

O LLM é opcional para o funcionamento do fluxo `SQL_ONLY`: PostgreSQL,
execução restrita, avaliação determinística e fallback local continuam
disponíveis sem credencial remota.

Para usar OpenRouter, configure no `.env`:

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=<modelo-com-suporte-a-structured-outputs>
LLM_API_KEY=<sua-chave>
```

O modelo configurado precisa oferecer suporte a Structured Outputs. O cliente
envia JSON Schema estrito e rejeita qualquer contrato que não passe a validação
v2 e o preflight PostgreSQL. O fornecedor, o nome do modelo e o mecanismo de
roteamento ficam a critério da configuração local, desde que o endpoint seja
compatível com o protocolo documentado.

Execute o smoke test com PostgreSQL disponível:

```bash
.venv/bin/python scripts/smoke_llm.py
```

Para validar o fluxo completo, incluindo provisionamento, execução, avaliação
e feedback:

```bash
.venv/bin/python scripts/smoke_llm.py --full
```

Sucesso exige `contract accepted`. No modo `--full`, o smoke também deve
registrar provisionamento, execução, avaliação e feedback. Uma saída
`generation unavailable` não penaliza o aluno: indica que o catálogo/fallback
deverá ser usado e que a validação remota correspondente permanece pendente.
