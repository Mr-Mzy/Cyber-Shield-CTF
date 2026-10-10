"""
app/__init__.py
----------------
This file does two jobs:

1. Its mere existence tells Python "the app/ folder is a package,"
   which is what lets other files write `from app.models import User`.

2. It defines create_app(), the "application factory" function.

WHY A FACTORY FUNCTION instead of just writing
    app = Flask(__name__)
directly in this file?

  - It lets tests/ create a fresh, isolated app for each test instead
    of reusing one global app object.
  - It avoids "circular imports": routes.py needs `db` from here, and
    this file needs the blueprints from routes.py. Defining `db` at
    module level (below) and only *connecting* it to the app inside
    create_app() breaks that circle.
  - It's the standard, recommended pattern for any Flask app bigger
    than a single file -- worth learning now.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# ----------------------------------------------------------------------
# These two objects are created here at IMPORT TIME, but not yet tied
# to any specific Flask app -- that happens later, inside create_app(),
# via db.init_app(app) and login_manager.init_app(app).
#
# This "create now, configure later" split is called the
# "application factory" pattern. Because `db` and `login_manager` are
# defined here at module level, any other file can do
# `from app import db` and get the SAME db object that's wired up to
# whichever app create_app() eventually builds.
# ----------------------------------------------------------------------
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    """
    Builds and configures a Flask application, then returns it.

    run.py calls this once, at startup, to get the real app that
    gets served. A test file could call it again to get a separate,
    isolated app for testing.
    """

    # Flask(__name__) creates the app. Because __name__ here is
    # "app" (this file's package name), Flask automatically looks for
    # templates in app/templates/ and static files in app/static/ --
    # which is exactly our folder structure. No extra config needed.
    app = Flask(__name__)

    # Load every setting from the Config class in config.py
    # (SECRET_KEY, SQLALCHEMY_DATABASE_URI, CHALLENGES_FOLDER, etc.)
    app.config.from_object("config.Config")

    # --------------------------------------------------------------
    # Now that we HAVE an app object, connect our extensions to it.
    # --------------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)

    # If someone who ISN'T logged in tries to visit a page marked
    # with @login_required, Flask-Login redirects them here.
    # "auth.login" means: the `login` view function, inside the
    # blueprint named `auth` (defined in app/auth.py below).
    login_manager.login_view = "auth.login"

    # --------------------------------------------------------------
    # Blueprints let us split routes across multiple files instead of
    # writing every single @app.route in one giant file. We import
    # them INSIDE this function (not at the top of the file) to avoid
    # a circular import: auth.py and routes.py both need to import
    # `db` from this file, so this file can't import THEM until after
    # `db` already exists above.
    # --------------------------------------------------------------
    from app.auth import auth_bp
    from app.routes import main_bp

    app.register_blueprint(auth_bp)   # adds /login, /register, /logout
    app.register_blueprint(main_bp)   # adds /, /dashboard, /challenge/..., etc.

    # --------------------------------------------------------------
    # Create the database tables if they don't already exist.
    # `app.app_context()` is required because SQLAlchemy needs to know
    # which app's config (i.e. which database file) to use -- outside
    # of a request, Flask doesn't know that automatically, so we tell
    # it explicitly with this "context manager."
    #
    # NOTE: db.create_all() only CREATES missing tables; it will not
    # update a table if you later change a model's columns. For a
    # student project that's fine -- just delete database/cybershield.db
    # and re-run seed.py if you change models.py.
    # --------------------------------------------------------------
    with app.app_context():
        db.create_all()

    return app


# ----------------------------------------------------------------------
# Flask-Login needs a "user loader": a function that takes the user ID
# stored in the encrypted session cookie and returns the matching User
# object from the database. This runs on every request for a logged-in
# user, so Flask-Login knows who "current_user" is.
#
# We import User INSIDE the function (not at the top of the file) to
# avoid a circular import, same reasoning as above.
# ----------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))
