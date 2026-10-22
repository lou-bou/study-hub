# study-hub

Personal site for my interactive course remakes and practice sheets, with auto-saved answers.

```
python3 build.py              # courses/ -> dist/
python3 server.py             # answers API on 127.0.0.1:8001 (data/answers.db)
```

Add a course: drop `courses/<slug>/*.html` (+ optional `course.json`), run `python3 build.py`.
Deploy notes: `deploy/` and `CLAUDE.md`.
