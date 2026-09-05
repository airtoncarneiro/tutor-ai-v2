CREATE SCHEMA IF NOT EXISTS tutor_state;
CREATE TABLE IF NOT EXISTS tutor_state.schema_migrations (
  version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tutor_state.student_profiles (
  id uuid PRIMARY KEY, singleton_key integer NOT NULL UNIQUE CHECK (singleton_key=1),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tutor_state.learning_sessions (
  id uuid PRIMARY KEY, profile_id uuid NOT NULL REFERENCES tutor_state.student_profiles(id),
  learning_goal text NOT NULL, mode text NOT NULL, status text NOT NULL DEFAULT 'active',
  current_run_id uuid, current_focus text, current_difficulty integer NOT NULL DEFAULT 1 CHECK (current_difficulty BETWEEN 1 AND 5),
  completed_count integer NOT NULL DEFAULT 0, revision integer NOT NULL DEFAULT 0, ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_learning_session ON tutor_state.learning_sessions (status) WHERE status='active';
CREATE TABLE IF NOT EXISTS tutor_state.skill_states (
  id uuid PRIMARY KEY, profile_id uuid NOT NULL REFERENCES tutor_state.student_profiles(id), skill_key text NOT NULL,
  mastery_score integer NOT NULL DEFAULT 0 CHECK (mastery_score BETWEEN 0 AND 5),
  evidence_status text NOT NULL DEFAULT 'unknown', confidence text NOT NULL DEFAULT 'medium',
  successful_attempts integer NOT NULL DEFAULT 0, failed_attempts integer NOT NULL DEFAULT 0,
  hints_required integer NOT NULL DEFAULT 0, last_result text, revision integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(profile_id, skill_key)
);
CREATE TABLE IF NOT EXISTS tutor_state.exercise_contracts (
  id uuid PRIMARY KEY, exercise_id text NOT NULL, version integer NOT NULL, contract_json jsonb NOT NULL,
  content_hash text NOT NULL, source text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(exercise_id, version)
);
CREATE TABLE IF NOT EXISTS tutor_state.exercise_runs (
  id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES tutor_state.learning_sessions(id), contract_id uuid NOT NULL REFERENCES tutor_state.exercise_contracts(id),
  state text NOT NULL DEFAULT 'ready', attempt_count integer NOT NULL DEFAULT 0, failed_count integer NOT NULL DEFAULT 0,
  hint_level integer NOT NULL DEFAULT 0, hint_events integer NOT NULL DEFAULT 0, draft_sql text, draft_reasoning text, context_tag text NOT NULL, evidence_kind text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), finalized_at timestamptz
);
ALTER TABLE tutor_state.exercise_runs ADD COLUMN IF NOT EXISTS hint_events integer NOT NULL DEFAULT 0;
ALTER TABLE tutor_state.skill_states ADD COLUMN IF NOT EXISTS last_seen timestamptz;
ALTER TABLE tutor_state.skill_states ADD COLUMN IF NOT EXISTS retrieval_due_at timestamptz;
ALTER TABLE tutor_state.skill_states ADD COLUMN IF NOT EXISTS declared_level integer;
ALTER TABLE tutor_state.skill_states ADD COLUMN IF NOT EXISTS recurring_errors jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE tutor_state.skill_states ADD COLUMN IF NOT EXISTS policy_version text NOT NULL DEFAULT 'evidence-v1';
ALTER TABLE tutor_state.learning_sessions ADD COLUMN IF NOT EXISTS finalized_since_checkpoint integer NOT NULL DEFAULT 0;
ALTER TABLE tutor_state.learning_sessions ADD COLUMN IF NOT EXISTS knowledge_declaration text;
ALTER TABLE tutor_state.learning_sessions ADD COLUMN IF NOT EXISTS next_action text;
ALTER TABLE tutor_state.learning_sessions ADD COLUMN IF NOT EXISTS provisional_tree jsonb;
ALTER TABLE tutor_state.learning_sessions ADD COLUMN IF NOT EXISTS prerequisite_return_focus text;
ALTER TABLE tutor_state.exercise_runs ADD COLUMN IF NOT EXISTS dataset_hash text;
ALTER TABLE tutor_state.exercise_runs ADD COLUMN IF NOT EXISTS solution_revealed boolean NOT NULL DEFAULT false;
ALTER TABLE tutor_state.exercise_contracts ADD COLUMN IF NOT EXISTS prompt_version text NOT NULL DEFAULT 'tutor-v2';
ALTER TABLE tutor_state.exercise_contracts ADD COLUMN IF NOT EXISTS registry_version integer NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS tutor_state.operations (
  action_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES tutor_state.learning_sessions(id), run_id uuid, kind text NOT NULL,
  payload_json jsonb NOT NULL, payload_hash text NOT NULL, expected_revision integer NOT NULL, status text NOT NULL DEFAULT 'pending',
  error_code text, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tutor_state.sql_runs (
  operation_id uuid PRIMARY KEY REFERENCES tutor_state.operations(action_id), run_id uuid NOT NULL, submitted_sql text NOT NULL,
  executed_sql text, execution_json jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tutor_state.submissions (
  operation_id uuid PRIMARY KEY REFERENCES tutor_state.operations(action_id), run_id uuid NOT NULL, submitted_sql text,
  reasoning text, hint_level_at_submit integer NOT NULL, evaluation_json jsonb NOT NULL, status text NOT NULL,
  feedback_status text NOT NULL DEFAULT 'pending', finalized_at timestamptz
);
CREATE TABLE IF NOT EXISTS tutor_state.tutor_messages (
  id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES tutor_state.learning_sessions(id), run_id uuid, request_id uuid NOT NULL,
  role text NOT NULL, content text NOT NULL, model_id text, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(request_id, role)
);
CREATE TABLE IF NOT EXISTS tutor_state.evidence_events (
  id uuid PRIMARY KEY, submission_id uuid NOT NULL, skill_key text NOT NULL, result text NOT NULL,
  independent boolean NOT NULL DEFAULT false, assisted boolean NOT NULL DEFAULT false,
  before_state jsonb NOT NULL, after_state jsonb NOT NULL, policy_version text NOT NULL DEFAULT 'evidence-v1',
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(submission_id, skill_key)
);
CREATE TABLE IF NOT EXISTS tutor_state.checkpoints (
  id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES tutor_state.learning_sessions(id),
  trigger_event_id uuid NOT NULL UNIQUE, reasons jsonb NOT NULL, state_snapshot jsonb NOT NULL,
  summary text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tutor_state.lifecycle_events (
  id uuid PRIMARY KEY, session_id uuid REFERENCES tutor_state.learning_sessions(id),
  skill_key text, operation_id uuid REFERENCES tutor_state.operations(action_id),
  kind text NOT NULL, dedup_key text NOT NULL UNIQUE,
  before_state jsonb, after_state jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE tutor_state.operations ADD COLUMN IF NOT EXISTS started_at timestamptz;
ALTER TABLE tutor_state.operations ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE tutor_state.tutor_messages ADD COLUMN IF NOT EXISTS submission_id uuid;
ALTER TABLE tutor_state.tutor_messages ADD COLUMN IF NOT EXISTS prompt_version text NOT NULL DEFAULT 'tutor-v2';
ALTER TABLE tutor_state.evidence_events ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'deterministic';
ALTER TABLE tutor_state.evidence_events ADD COLUMN IF NOT EXISTS error_kind text;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='learning_sessions_current_run_fk') THEN
    ALTER TABLE tutor_state.learning_sessions ADD CONSTRAINT learning_sessions_current_run_fk FOREIGN KEY (current_run_id) REFERENCES tutor_state.exercise_runs(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='operations_run_fk') THEN
    ALTER TABLE tutor_state.operations ADD CONSTRAINT operations_run_fk FOREIGN KEY (run_id) REFERENCES tutor_state.exercise_runs(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='sql_runs_run_fk') THEN
    ALTER TABLE tutor_state.sql_runs ADD CONSTRAINT sql_runs_run_fk FOREIGN KEY (run_id) REFERENCES tutor_state.exercise_runs(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='submissions_run_fk') THEN
    ALTER TABLE tutor_state.submissions ADD CONSTRAINT submissions_run_fk FOREIGN KEY (run_id) REFERENCES tutor_state.exercise_runs(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='evidence_submission_fk') THEN
    ALTER TABLE tutor_state.evidence_events ADD CONSTRAINT evidence_submission_fk FOREIGN KEY (submission_id) REFERENCES tutor_state.submissions(operation_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tutor_messages_submission_fk') THEN
    ALTER TABLE tutor_state.tutor_messages ADD CONSTRAINT tutor_messages_submission_fk FOREIGN KEY (submission_id) REFERENCES tutor_state.submissions(operation_id);
  END IF;
END $$;
INSERT INTO tutor_state.schema_migrations (version) VALUES ('001_initial') ON CONFLICT DO NOTHING;
