# CS-04 — Vulnerable Portal (Web Security)

This is a **service-based** challenge, not a file-based one — there's
nothing to download; participants attack a live vulnerable web app.

Build the vulnerable portal as its OWN small Flask/PHP app with one
deliberate weakness (e.g. SQL injection in a login form, or an IDOR in
a URL parameter), and run it as a **separate container on its own
isolated Docker network** — not inside this CyberShield platform's own
container — per the network-isolation section of the design document.

A minimal starting point:
1. Put the vulnerable app's code in this folder (e.g. `app.py`, `templates/`).
2. Add a `Dockerfile` + `docker-compose.yml` here just for this challenge.
3. In `challenge.html`, show participants the connection info
   (e.g. `http://localhost:8080`) instead of a file download link.
4. Write a `reset.sh` here to tear down and rebuild this container
   between attempts/teams.
