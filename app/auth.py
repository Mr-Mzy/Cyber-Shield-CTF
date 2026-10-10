"""
app/auth.py
-----------
Everything related to accounts: register, login, logout.

This file defines a BLUEPRINT, not a full Flask app. A blueprint is
like a "mini app" of related routes that gets plugged into the real
app later (see app/__init__.py -> app.register_blueprint(auth_bp)).

Splitting routes into blueprints (auth.py vs routes.py) is purely
organizational -- it keeps "account stuff" separate from "challenge
stuff" so each file stays a manageable size.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import LogEntry, User

# "auth" is this blueprint's name. Flask uses it to build endpoint
# names like "auth.login", which is what url_for("auth.login") and
# login_manager.login_view = "auth.login" (in app/__init__.py) refer to.
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    GET  -> just show the registration form (register.html)
    POST -> the form was submitted; try to create the account
    """

    # If someone who's already logged in visits /register, just send
    # them to their dashboard instead of showing the form again.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        # request.form is a dict-like object holding whatever the
        # <form> on register.html submitted. .get(..., "") avoids a
        # crash if the field is somehow missing.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("auth.register"))

        # Check the database for an existing user with this username.
        # first() returns None if no match is found.
        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
            return redirect(url_for("auth.register"))

        # generate_password_hash() turns the plaintext password into a
        # secure, salted hash -- we store ONLY this, never the raw
        # password. There is no way to reverse a hash back into the
        # original password; login works by hashing the ATTEMPT and
        # comparing hashes (see login() below).
        user = User(username=username, password_hash=generate_password_hash(password))

        db.session.add(user)     # stage this new row for insertion
        db.session.commit()      # actually write it to the database file

        flash("Account created. You may now log in.", "success")
        return redirect(url_for("auth.login"))

    # GET request (or nothing matched above): just render the form.
    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    GET  -> show the login form
    POST -> check the submitted username/password against the database
    """

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        # check_password_hash() hashes `password` the same way
        # generate_password_hash() did at registration, and compares
        # the result to what's stored in user.password_hash. We never
        # decrypt the stored hash -- hashing is one-way by design.
        if user and check_password_hash(user.password_hash, password):
            # login_user() is provided by Flask-Login. It stores the
            # user's ID in the encrypted session cookie so future
            # requests know who's logged in (via our load_user()
            # function in app/__init__.py).
            login_user(user)

            db.session.add(
                LogEntry(event_type="login", user_id=user.id, detail=f"{username} logged in")
            )
            db.session.commit()

            return redirect(url_for("main.dashboard"))

        # Either the username didn't exist, or the password was wrong.
        # We log the attempt (without the password!) for the admin
        # panel, and show one generic error message -- deliberately
        # NOT saying which of "username" or "password" was wrong,
        # since that would help an attacker guess valid usernames.
        db.session.add(
            LogEntry(event_type="login_failed", detail=f"failed login attempt for '{username}'")
        )
        db.session.commit()
        flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required   # this decorator blocks access unless someone is logged in
def logout():
    db.session.add(
        LogEntry(event_type="logout", user_id=current_user.id, detail=f"{current_user.username} logged out")
    )
    db.session.commit()

    logout_user()   # clears the session cookie -- Flask-Login forgets who you are
    return redirect(url_for("auth.login"))
