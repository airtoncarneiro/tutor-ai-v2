#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set by the official PostgreSQL image}"
: "${POSTGRES_DB:?POSTGRES_DB must be set by the official PostgreSQL image}"
: "${TUTOR_APP_PASSWORD:?TUTOR_APP_PASSWORD must be set}"
: "${TUTOR_RUNNER_PASSWORD:?TUTOR_RUNNER_PASSWORD must be set}"
: "${TUTOR_EVALUATOR_PASSWORD:?TUTOR_EVALUATOR_PASSWORD must be set}"

psql_args=(
  --username "$POSTGRES_USER"
  --dbname "$POSTGRES_DB"
  --no-password
  --set ON_ERROR_STOP=1
)

ensure_login_role() {
  local role_name="$1"
  local role_password="$2"
  local role_exists

  role_exists="$(psql "${psql_args[@]}" --tuples-only --no-align \
    --command "SELECT 1 FROM pg_roles WHERE rolname = '$role_name'")"

  if [ "$role_exists" = "1" ]; then
    psql "${psql_args[@]}" \
      --set role_name="$role_name" \
      --set role_password="$role_password" <<'SQL'
ALTER ROLE :"role_name"
  WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'role_password';
SQL
  else
    psql "${psql_args[@]}" \
      --set role_name="$role_name" \
      --set role_password="$role_password" <<'SQL'
CREATE ROLE :"role_name"
  WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'role_password';
SQL
  fi
}

ensure_login_role tutor_app "$TUTOR_APP_PASSWORD"
ensure_login_role tutor_runner "$TUTOR_RUNNER_PASSWORD"
ensure_login_role tutor_evaluator "$TUTOR_EVALUATOR_PASSWORD"

psql "${psql_args[@]}" \
  --set db_name="$POSTGRES_DB" \
  --set owner_name="$POSTGRES_USER" <<'SQL'
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO tutor_app, tutor_runner, tutor_evaluator;
REVOKE TEMPORARY ON DATABASE :"db_name" FROM PUBLIC, tutor_runner, tutor_evaluator;

CREATE SCHEMA IF NOT EXISTS tutor_state AUTHORIZATION :"owner_name";
CREATE SCHEMA IF NOT EXISTS exercise AUTHORIZATION tutor_app;
CREATE SCHEMA IF NOT EXISTS exercise_validation AUTHORIZATION tutor_app;

REVOKE ALL ON SCHEMA public, tutor_state, exercise, exercise_validation FROM PUBLIC;

GRANT USAGE ON SCHEMA tutor_state TO tutor_app;
GRANT USAGE, CREATE ON SCHEMA exercise TO tutor_app;
GRANT USAGE, CREATE ON SCHEMA exercise_validation TO tutor_app;
GRANT USAGE ON SCHEMA exercise TO tutor_runner, tutor_evaluator;
GRANT USAGE ON SCHEMA exercise_validation TO tutor_evaluator;

GRANT tutor_evaluator TO tutor_app;

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_name" IN SCHEMA tutor_state
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tutor_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_name" IN SCHEMA tutor_state
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO tutor_app;

ALTER DEFAULT PRIVILEGES FOR ROLE tutor_app IN SCHEMA exercise
  GRANT SELECT ON TABLES TO tutor_runner, tutor_evaluator;
ALTER DEFAULT PRIVILEGES FOR ROLE tutor_app IN SCHEMA exercise_validation
  GRANT SELECT ON TABLES TO tutor_evaluator;
SQL

echo "PostgreSQL roles and schemas bootstrapped."

