# study-hub

Personal site for my interactive course remakes and practice sheets, with auto-saved answers.

```
python3 build.py              # courses/ -> dist/
python3 server.py             # answers API on 127.0.0.1:8001 (data/answers.db)
```

Add a chapter: `python3 add.py <module> <chapter> lesson.html practice.html cours.pdf --title "..."` copies the files into `modules/<module>/<chapter>/`, builds, commits and pushes; the ThinkPad pulls and rebuilds within 5 minutes (`deploy/update.sh` on cron). New remakes start from `remake_template.html` (see `REMAKE_BRIEF.md`).
Deploy notes: `deploy/` and `CLAUDE.md`.
