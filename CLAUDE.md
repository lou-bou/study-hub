# Study Hub

Personal, single-user website that hosts my interactive HTML course remakes (THOR, OPL, GBD, SSAD, and more to come) plus their practice sheets, and saves my practice answers in a small database. Self-hosted on a Debian ThinkPad, reachable at a subdomain of boussaid.me. Nobody else uses it.

I am a master's student (Big Data Analytics, USTHB) in Algeria. Be short, direct and opinionated. Lead with the answer. When I ask for a decision, give a concrete recommendation.

## Status
Design is settled and was prototyped and tested in a chat session (build, API, and a headless-browser save/restore test all passed). Nothing is in this repo yet: build the structure below. I will add the existing HTML remakes when you ask for them; do not invent course content. Until then, use a throwaway `courses/demo/` (one lesson page, one practice page with a text input, radios, a checkbox and a textarea) to test with, and delete it once real courses exist.

## Decisions already made
- Plain static site, no framework. Remakes are standalone HTML files and stay that way.
- Answers stored in SQLite behind a tiny API. Python 3 standard library only (no pip dependencies).
- Caddy serves `dist/` and proxies `/api/*` to the API. Both bind to 127.0.0.1.
- Exposure: Cloudflare Tunnel, no router ports (Algerian ISPs often use CGNAT). Cloudflare Access (one-time email code) restricts the whole hostname, API included, to me. boussaid.me must be on Cloudflare DNS for this; if I don't want to move it, use a spare student-pack domain or Tailscale instead.
- Must be extensible: adding a remake means dropping files in a folder and running the build, nothing else.

## Layout
```
courses/<slug>/*.html     remakes (+ optional course.json)
assets/saver.js           auto-save script for practice pages
hub_template.html         hub page template (%%TITLE%% %%SUB%% %%STATS%% %%CARDS%% placeholders)
build.py                  courses/ -> dist/
server.py                 answers API
site.json                 optional {"title","subtitle"}
deploy/Caddyfile, deploy/studysite-api.service
data/answers.db           my answers, never committed, never rsynced
dist/                     generated, never committed
```
`.gitignore`: `dist/`, `.dist_new/`, `data/*.db*`, `__pycache__/`. Keep `data/.gitkeep`.

## build.py
- Each folder in `courses/` (skip names starting with `.` or `_`) is a course. Optional `course.json`: `{"code","title","blurb","order","pages":[{"file","title","kind"}]}`. Without it: code = folder name uppercased, pages = all `*.html`, lessons first, `kind` = `practice` if the filename contains "practice" else `lesson`, title from `<title>`.
- Build into `.dist_new/`, then swap into `dist/`. Copy `assets/`, each course folder (minus `course.json`), and generate `index.html` from the template.
- Inject before the last `</body>` of every page: a fixed bottom-left "← Hub" link. On `practice` pages also `<script src="/assets/saver.js" data-course="<slug>" data-page="<filename>"></script>`. Never edit the source HTML.
- Hub: one card per course (code chip, title, blurb, a link per page), light/dark theme with toggle, hero with a small SVG figure, matching the look of my Graph Theory Primer remake. Practice links get a badge filled from `/api/summary` ("N saved").

## server.py (127.0.0.1:8001, env ANSWERS_DB / ANSWERS_HOST / ANSWERS_PORT)
Table `answers(course, page, key, value, updated_at, PRIMARY KEY(course,page,key))`, WAL mode.
- `GET /api/health`
- `GET /api/answers?course=&page=` -> `{key: value}`
- `PUT /api/answers` body `{course,page,key,value}`; upsert; an empty value deletes the row
- `DELETE /api/answers?course=&page=` wipes one page
- `GET /api/summary` -> `{"course/page": count}`
- `GET /api/export` -> all rows
Validate course/page against `^[\w.\-]{1,100}$`, key 1-200 chars, body <= 64 KB, value <= 20 KB. JSON responses, `Cache-Control: no-store`, quiet logging.

## saver.js
- Handles `input, textarea, select`, skipping button/submit/reset/hidden/file/password/image and anything inside `[data-no-save]`.
- Key: radio `r:<name>`; checkbox `c:<id or name:value>`; otherwise `v:<id>`, else `v:<name>`, else `v:#<position>`. Unchecked checkbox saves `""` (deletes the row).
- Debounced (400 ms) PUT on `input`/`change` via event delegation. Restore on load by setting values and dispatching `input`+`change` (with a `restoring` flag so it doesn't re-save). A MutationObserver restores fields the page creates later.
- Small bottom-right pill: Saving… / Saved ✓ / Restored N answers / Not saved ⚠, plus a Reset button (confirm, then DELETE and reload).

## Deploy (Debian ThinkPad)
- Code in `/srv/studysite`. Caddy: global `auto_https off`, site `http://localhost:8080`, `bind 127.0.0.1`, `root * /srv/studysite/dist`, `encode zstd gzip`, `handle /api/*` -> `reverse_proxy 127.0.0.1:8001`, otherwise `file_server`.
- systemd unit `studysite-api.service` running `python3 /srv/studysite/server.py` as my user, `Restart=on-failure`, `ReadWritePaths=/srv/studysite/data`.
- cloudflared installed from the Cloudflare Zero Trust dashboard (Networks -> Tunnels); public hostname `study.boussaid.me` -> `http://localhost:8080`; Access application with an Allow policy for my email only.
- Update flow: push from my main machine, then on the ThinkPad `git pull && python3 build.py` (no restart needed). Never overwrite `data/`.
- Backup: `sqlite3 data/answers.db ".backup '<path>'"` on a daily cron, plus `/api/export` for a portable copy.

## Writing new remakes (when I give you course material)
- Output is one standalone styled HTML file per lesson, modeled on my Graph Theory Primer: hero with a figure, contents grid, numbered sections each with an "In plain words" box, keyword definitions, hand-drawn inline SVG figures, a worked-example box, light and dark theme.
- Written in English with the French term in parentheses next to key terms. At least one example per concept, and redo the examples from the original course. Concise, not dense.
- Verify every example by running a program before putting it in.
- End with a short notes box listing errors found in the original course text.
- Practice pages: keep problems simple and show visual aids (alphabet for Caesar, lookup tables). The goal is to get used to the algorithm, not to compute by hand; exams don't require hand computation.
- Give every practice input a stable `id` (`q1`, `q2`, ...) so saved answers survive edits. Use `data-no-save` on anything that must not be stored.
- Put files in `courses/<slug>/` (`lesson.html`, `practice.html`), add a `course.json` for the card, run `python3 build.py`.

## Conventions
- Python 3 stdlib only unless I approve a dependency. No frameworks, no build tooling beyond `build.py`.
- Run `python3 build.py` and a quick API check after changes. For anything touching saver.js, test save + reload + restore in a headless browser.
- Don't commit generated output or my answers database.