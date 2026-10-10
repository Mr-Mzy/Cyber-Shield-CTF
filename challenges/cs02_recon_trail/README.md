# CS-02 — The Recon Trail (OSINT)

This stage is intentionally file-less: no download is served for it
(`file_path` is `None` in seed.py). The scenario in the design document
describes correlating simulated company information sources (a fake
employee directory, a mock blog post, etc.).

To build this stage out, add your simulated static pages/files here
(e.g. `directory.html`, `company_blog.html`) and either:
  - host them from a tiny separate Flask route or static folder, or
  - link to them as downloadable files (set `file_path` in seed.py
    to point at whichever file inside this folder holds the clue).
