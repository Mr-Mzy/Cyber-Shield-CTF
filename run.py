"""
run.py
------
This is the file you actually execute to start the server:

    python run.py

All it does is call the "application factory" (create_app, defined in
app/__init__.py) to build a Flask app, then start Flask's built-in
development web server.

Why not just build the app directly in this file? Splitting "build
the app" (create_app) from "run the app" (this file) means our test
files (in tests/) can call create_app() too, to get a fresh app to
test against, without also starting a real web server.
"""

from app import create_app

# Build the Flask app using our factory function.
app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0" makes the server reachable from other devices on
    # your network (not just this laptop) -- handy if you want to test
    # from your phone on the same Wi-Fi. Use "127.0.0.1" instead if you
    # only ever want to access it from this machine.
    #
    # debug=True auto-reloads the server when you save a code change,
    # and shows detailed error pages. ALWAYS turn this off (debug=False)
    # before letting anyone else use this, since the debug error pages
    # can leak source code and even allow remote code execution.
    app.run(host="0.0.0.0", port=5000, debug=True)
