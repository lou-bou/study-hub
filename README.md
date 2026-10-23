# study-hub

Personal site for my interactive course remakes and practice sheets, with auto-saved answers.

```
python3 build.py              # courses/ -> dist/
python3 server.py             # answers API on 127.0.0.1:8001 (data/answers.db)
```

Add content: upload it at `/upload/` on the site (the server places it in `modules/`, builds, commits and pushes), or run `python3 add.py <module> <chapter> lesson.html practice.html cours.pdf --title "..."` locally. The ThinkPad pulls and rebuilds within 5 minutes (`deploy/update.sh` on cron). New remakes start from `remake_template.html` (see `REMAKE_BRIEF.md`). Run `git pull` before working in the repo, since the server commits uploads.
Setting up a server (or moving to a new one): `deploy/SETUP.md`. Design notes: `CLAUDE.md`.
