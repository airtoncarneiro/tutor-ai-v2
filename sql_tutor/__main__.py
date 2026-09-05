from .config import Settings
from .application import TutorApplication
from .repositories import Repository


if __name__ == "__main__":
    settings = Settings.from_env(".env", require_admin=True)
    Repository(settings.database_app_url, settings.database_admin_url).migrate("migrations/001_initial.sql")
    app = TutorApplication(settings)
    app.initialize()
    print("Database initialized.")
