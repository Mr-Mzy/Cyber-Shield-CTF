"""
config.py
---------
Central configuration for the whole app.

Why a separate config file at all?
Instead of scattering settings (secret keys, database paths, folder
locations) across multiple files, we keep them in ONE place. When you
later deploy this somewhere else, or need to change a setting, this
is the only file you should need to touch.
"""

import os

# BASE_DIR = the absolute path of the folder this config.py file is in
# (i.e. the project root, "CyberShield/"). We use this so that file
# paths work correctly no matter where you run the app from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # ------------------------------------------------------------------
    # SECRET_KEY: Flask uses this to cryptographically sign session
    # cookies (the cookie that keeps you "logged in" between requests).
    # If someone else knows this key, they could forge a login session.
    # os.environ.get(...) means: "use the SECRET_KEY environment
    # variable if one is set, otherwise fall back to the string after
    # the comma." NEVER ship the fallback value to a real deployment.
    # ------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

    # ------------------------------------------------------------------
    # SQLALCHEMY_DATABASE_URI: tells SQLAlchemy (our database toolkit)
    # where the database file lives. "sqlite:///" + an absolute path
    # means "use a SQLite database file at this exact location."
    # SQLite stores the whole database as a single file on disk --
    # perfect for a student project, no separate database server needed.
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'database', 'cybershield.db')}",
    )

    # Turns off a SQLAlchemy feature we don't use (it tracks every
    # object modification for signals we never listen to). Turning it
    # off also silences a console warning on startup.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ------------------------------------------------------------------
    # CHALLENGES_FOLDER: where downloadable challenge files live
    # (the stego image, the ciphertext, the forensic evidence zip).
    # Each challenge gets its own subfolder, e.g.
    # challenges/cs01_hidden_message/employee_photo.jpg
    # ------------------------------------------------------------------
    CHALLENGES_FOLDER = os.path.join(BASE_DIR, "challenges")
