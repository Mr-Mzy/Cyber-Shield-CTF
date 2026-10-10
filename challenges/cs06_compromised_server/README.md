# CS-06 — Compromised Server (Linux / System Security)

Also **service-based**: participants get SSH/terminal access to a
small Linux container or VM with an intentional misconfiguration
(e.g. a SUID binary, a writable cron job, or unnecessary sudo rights).

Suggested build steps:
1. Write a `Dockerfile` here based on a minimal Linux image, with a
   low-privilege user and the one deliberate misconfiguration baked in.
2. Add `docker-compose.yml` here (own isolated network — see the
   design document's network-isolation section) exposing an SSH port.
3. Keep the clean image/Dockerfile as your "master copy" so you can
   reset a compromised instance by just rebuilding the container.
4. Update `challenge.html` to show the SSH connection details instead
   of a file download.
