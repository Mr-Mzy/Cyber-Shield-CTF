"""
reset.py
--------
The RESET MECHANISM for the CyberShield platform. One command puts the
platform back to a clean state, for example between two demo runs or
after a participant has made a mess.

Usage (run from the project folder, with the virtual environment on):

    python reset.py player alice      # wipe ONE player's progress
    python reset.py progress          # wipe EVERYONE's progress (keeps accounts)
    python reset.py full              # rebuild the whole database from scratch

Add --yes to skip the "are you sure?" question.

What each mode does
-------------------
player    deletes that player's submissions, solved/unlocked stages and
          hint purchases. Their account stays; they start again at CS-01.
progress  does the same for every player. Accounts, challenges and the
          admin account stay.
full      deletes database/cybershield.db and runs seed.py, which makes
          a brand-new database (admin account + the six challenges).
          STOP THE SERVER FIRST: Windows will not delete a database
          file that is still open.

The audit log is NEVER erased by player/progress resets. Instead a
"reset" entry is added, so there is still a record of who/what was
reset and when.
"""

import argparse
import os
import sys

from config import Config


def ask(question, assume_yes):
    """Asks for confirmation unless --yes was given."""
    if assume_yes:
        return True
    return input(f"{question} Type YES to continue: ").strip() == "YES"


def wipe_progress(user_id=None):
    """
    Deletes Submission, Progress and HintReveal rows.
    user_id=None means everyone; otherwise only that one player.
    Returns how many rows were removed from each table.
    """
    from app import create_app, db
    from app.models import HintReveal, Progress, Submission

    app = create_app()
    with app.app_context():
        removed = {}
        for name, model in (
            ("submissions", Submission),
            ("progress rows", Progress),
            ("hint purchases", HintReveal),
        ):
            query = model.query
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            removed[name] = query.delete()
        db.session.commit()
        return removed


def log_reset(detail):
    """Adds a 'reset' line to the audit log (shown in Admin -> System Logs)."""
    from app import create_app, db
    from app.models import LogEntry

    app = create_app()
    with app.app_context():
        db.session.add(LogEntry(event_type="reset", detail=detail))
        db.session.commit()


def reset_player(username, assume_yes):
    from app import create_app
    from app.models import User

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=username, is_admin=False).first()
        user_id = user.id if user else None

    if user_id is None:
        print(f"No player called '{username}' was found.")
        return 1
    if not ask(f"Reset ALL progress for player '{username}'?", assume_yes):
        print("Cancelled.")
        return 1

    removed = wipe_progress(user_id)
    log_reset(f"progress reset for player '{username}' (reset.py)")
    print(f"Done. Removed: {removed}")
    return 0


def reset_progress(assume_yes):
    if not ask("Reset progress for EVERY player? Accounts are kept.", assume_yes):
        print("Cancelled.")
        return 1

    removed = wipe_progress(None)
    log_reset("progress reset for all players (reset.py)")
    print(f"Done. Removed: {removed}")
    return 0


def reset_full(assume_yes):
    uri = Config.SQLALCHEMY_DATABASE_URI
    if not uri.startswith("sqlite:///"):
        print("Full reset only supports the SQLite database file.")
        return 1

    path = uri.replace("sqlite:///", "", 1)
    if not ask(f"DELETE the whole database ({path}) and rebuild it?", assume_yes):
        print("Cancelled.")
        return 1

    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            print("The database file is in use. Stop the server (Ctrl+C) and try again.")
            return 1

    # Importing seed builds a new empty database; seed() then fills it
    # with the admin account and the six challenges.
    import seed

    seed.seed()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Reset the CyberShield platform.")
    parser.add_argument("mode", choices=["player", "progress", "full"])
    parser.add_argument("username", nargs="?", help="needed for 'player' mode")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation question")
    args = parser.parse_args()

    if args.mode == "player":
        if not args.username:
            parser.error("'player' mode needs a username, e.g.  python reset.py player alice")
        return reset_player(args.username, args.yes)
    if args.mode == "progress":
        return reset_progress(args.yes)
    return reset_full(args.yes)


if __name__ == "__main__":
    sys.exit(main())