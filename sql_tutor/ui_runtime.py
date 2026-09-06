from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .application import TutorApplication
from .config import Settings


SettingsFactory = Callable[[str], Settings]
TutorFactory = Callable[[Settings], Any]

_settings_factory: SettingsFactory = Settings.from_env
_tutor_factory: TutorFactory = TutorApplication


def load_settings(env_file: str = ".env") -> Settings:
    return _settings_factory(env_file)


def create_tutor(settings: Settings) -> Any:
    return _tutor_factory(settings)


def configure_for_tests(*, settings_factory: SettingsFactory, tutor_factory: TutorFactory) -> None:
    """Install deterministic factories used by Streamlit AppTest.

    Production never calls this hook. Tests must restore the defaults after
    each scenario so state cannot leak between AppTest runs.
    """
    global _settings_factory, _tutor_factory
    _settings_factory = settings_factory
    _tutor_factory = tutor_factory


def reset_factories() -> None:
    global _settings_factory, _tutor_factory
    _settings_factory = Settings.from_env
    _tutor_factory = TutorApplication
