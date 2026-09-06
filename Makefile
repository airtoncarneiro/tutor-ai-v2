.DEFAULT_GOAL := help
.SHELL := /bin/sh

.PHONY: help start init run stop restart reset status test test-ui test-postgres

# These variables can remain exported by an old shell session. Removing them
# from each process makes Docker Compose and python-dotenv read the current
# .env consistently. The explicit env -u form is portable on macOS BSD Make.
CLEAN_ENV = env \
	-u DATABASE_ADMIN_URL -u DATABASE_APP_URL -u DATABASE_RUNNER_URL \
	-u DATABASE_EVALUATOR_URL -u SQL_MENTOR_POSTGRES_USER \
	-u SQL_MENTOR_POSTGRES_DB -u SQL_MENTOR_POSTGRES_PORT \
	-u SQL_MENTOR_POSTGRES_PASSWORD -u SQL_MENTOR_APP_PASSWORD \
	-u SQL_MENTOR_SANDBOX_PASSWORD -u SQL_MENTOR_EVALUATOR_PASSWORD \
	-u TUTOR_POSTGRES_OWNER_USER -u TUTOR_POSTGRES_DB \
	-u TUTOR_POSTGRES_PORT -u TUTOR_POSTGRES_OWNER_PASSWORD \
	-u TUTOR_APP_PASSWORD -u TUTOR_RUNNER_PASSWORD \
	-u TUTOR_EVALUATOR_PASSWORD

help: ## Show available sessions
	awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

start: ## Start PostgreSQL and wait until it is healthy
	$(CLEAN_ENV) docker compose up -d --wait postgres

init: start ## Start PostgreSQL and initialize migrations/fixture
	$(CLEAN_ENV) .venv/bin/python -m sql_tutor

run: init ## Start PostgreSQL, initialize it and open Streamlit
	$(CLEAN_ENV) .venv/bin/streamlit run sql_tutor/app.py

stop: ## Stop PostgreSQL and preserve its volume
	docker compose stop postgres

restart: ## Restart PostgreSQL and preserve its volume
	docker compose restart postgres

reset: ## Destroy PostgreSQL data, recreate it and initialize the application
	@if [ "$(CONFIRM)" != "1" ]; then \
		printf 'This removes all PostgreSQL data. Continue? [y/N] '; \
		read answer; \
		case "$$answer" in \
			y|Y|yes|YES) ;; \
			*) echo 'Reset cancelled.'; exit 1 ;; \
		esac; \
	fi
	$(CLEAN_ENV) docker compose down -v --remove-orphans
	$(CLEAN_ENV) docker compose up -d --wait postgres
	$(CLEAN_ENV) .venv/bin/python -m sql_tutor

status: ## Show PostgreSQL container and health status
	docker compose ps postgres

test: ## Run deterministic tests, including AppTest
	PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m 'not postgres and not browser and not real_llm' -q

test-ui: ## Run deterministic Streamlit AppTest scenarios
	PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m apptest -q

test-postgres: ## Run tests with a disposable PostgreSQL container
	RUN_POSTGRES_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m postgres -q
