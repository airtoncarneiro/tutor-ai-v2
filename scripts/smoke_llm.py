"""Run one real exercise-generation smoke test without printing secrets."""

from __future__ import annotations

import argparse

from sql_tutor.application import TutorApplication
from sql_tutor.config import Settings
from sql_tutor.evaluator import evaluate_sql
from sql_tutor.exercises import example_contract
from sql_tutor.provision import provision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="also provision, execute, evaluate, and request feedback")
    args = parser.parse_args()
    settings = Settings.from_env(".env")
    print(f"LLM model: {settings.llm_model or 'local fallback'}")
    if not (settings.llm_base_url and settings.llm_model):
        print("Result: local fallback (remote LLM is not configured)")
        return 0
    try:
        app = TutorApplication(settings)
        contract = app.generate_exercise(
            "aggregation.grouping.group_by",
            difficulty=1,
            response_mode="SQL_ONLY",
            evidence_kind="isolated",
        )
        print(f"Result: contract accepted ({contract.exercise_id})", flush=True)
        print(f"Primary skill: {contract.task.primary_skill}")
        if args.full:
            print("Stage: provisioning", flush=True)
            try:
                provision(contract, settings.database_app_url)
                app.contract = contract
                print("Stage: executing visible and hidden datasets", flush=True)
                visible = app.db.execute(contract, contract.private.reference_sql, preview_limit=settings.display_row_limit)
                hidden = app.db.execute(contract, contract.private.reference_sql, hidden=True, preview_limit=settings.evaluation_row_limit)
                evaluation = evaluate_sql(contract, visible, hidden)
                print(f"Stage: evaluation={evaluation.decision}", flush=True)
                feedback = app._feedback(evaluation)
                print(f"Stage: feedback={'ok' if feedback.get('message') else 'missing'}", flush=True)
            finally:
                provision(example_contract(), settings.database_app_url)
                print("Stage: fixture restored", flush=True)
        return 0
    except Exception as exc:
        print(f"Result: generation unavailable ({type(exc).__name__})")
        print("The application will use a validated local fallback when available.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
