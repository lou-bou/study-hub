# Study Hub

Personal, single-user website that hosts my interactive HTML course remakes (THOR, OPL, GBD, SSAD, and more to come) plus their practice sheets, and saves my practice answers in a small database. Self-hosted on a Debian ThinkPad, reachable at a subdomain of boussaid.me. Nobody else uses it.

I am a master's student (Big Data Analytics, USTHB) in Algeria. Be short, direct and opinionated. Lead with the answer. When I ask for a decision, give a concrete recommendation.

## Status
Built and deployed-ready. Modules in the repo: GBD ch1, OPL ch1-2, THOR ch1 (lesson + practice + course PDFs, all on the shared template). Empty module folders (cpsi, gp, pravan, ssad, vt) exist locally only; git doesn't track empty dirs and the build hides modules without chapters. Do not invent course content.

## Decisions already made
- Plain static site, no framework. Remakes are standalone HTML files and stay that way.
- Answers stored in SQLite behind a tiny API. Python 3 standard library only (no pip dependencies).
- Caddy serves `dist/` and proxies `/api/*` to the API. Both bind to 127.0.0.1.
- Exposure: Cloudflare Tunnel, no router ports (Algerian ISPs often use CGNAT). Cloudflare Access (one-time email code) restricts the whole hostname, API included, to me. boussaid.me must be on Cloudflare DNS for this; if I don't want to move it, use a spare student-pack domain or Tailscale instead.
- Must be extensible: adding a remake means dropping files in a folder and running the build, nothing else.

## Layout
```
modules/<module>/module.json          optional {"code","title","blurb","order","chapters":{"ch1":"title"}}
modules/<module>/<chapter>/lesson.html, practice.html   my remakes
modules/<module>/<chapter>/cours/     the professor's course PDFs, named <n>-<topic>.pdf
modules/<module>/<chapter>/td/        the professor's exercise sheets (keep td/.gitkeep while empty)
remake_template.html                  the shared remake shell: base CSS, theme toggle, components
assets/saver.js                       auto-save script for practice pages
hub_template.html                     hub page template (%%TITLE%% %%SUB%% %%STATS%% %%CARDS%% placeholders)
build.py                              modules/ -> dist/
server.py                             answers API
site.json                             optional {"title","subtitle"}
deploy/Caddyfile, deploy/studysite-api.service
data/answers.db                       my answers, never committed, never rsynced
dist/                                 generated, never committed
```
Naming: module and chapter folders lowercase (`thor`, `ch1`, `ch1-2` for a remake covering two chapters); remakes are always `lesson.html` and `practice.html`. Saved answers are keyed by module + `<chapter>/<file>`, so don't rename those once answers exist.
`.gitignore`: `dist/`, `.dist_new/`, `.dist_old/`, `data/*.db*`, `__pycache__/`. Keep `data/.gitkeep`.

## build.py
- Each folder in `modules/` (skip names starting with `.` or `_`) is a module; each subfolder of a module is a chapter. Modules with no chapters are hidden. Code defaults to the folder name uppercased; chapter label is derived from the folder (`ch1` -> Chapter 1, `ch1-2` -> Chapters 1–2), title from `module.json` `chapters`.
- Pages: every `*.html` in a chapter, lessons first; `practice` in the filename = practice page. HTML inside `td/` is treated as practice too.
- Build into `.dist_new/`, then swap into `dist/`. Copy `assets/` and each module folder (minus `module.json` and dotfiles), and generate `index.html` from the template.
- Inject before the last `</body>` of every page: a fixed bottom-left bar with "← Hub" and links to the chapter's course PDFs. On practice pages also `<script src="/assets/saver.js" data-module="<module>" data-page="<chapter>/<file>"></script>`. Never edit the source HTML.
- Hub: one card per module (code chip, title, blurb), one row per chapter with Lesson / Practice links and its Cours and TD files (PDFs open in a new tab). Same tokens and fonts as the remakes, light/dark with toggle. Practice links get a badge from `/api/summary` ("N saved").

## server.py (127.0.0.1:8001, env ANSWERS_DB / ANSWERS_HOST / ANSWERS_PORT)
Table `answers(module, page, key, value, updated_at, PRIMARY KEY(module,page,key))`, WAL mode. `page` is `<chapter>/<file>`.
- `GET /api/health`
- `GET /api/answers?module=&page=` -> `{key: value}`
- `PUT /api/answers` body `{module,page,key,value}`; upsert; an empty value deletes the row
- `DELETE /api/answers?module=&page=` wipes one page
- `GET /api/summary` -> `{"module/chapter/file": count}`
- `GET /api/export` -> all rows
Validate module as one segment `^[\w\-][\w.\-]{0,99}$`, page as 1-4 such segments joined by `/` (<= 200 chars), key 1-200 chars, body <= 64 KB, value <= 20 KB. JSON responses, `Cache-Control: no-store`, quiet logging.

## saver.js
- Handles `input, textarea, select`, skipping button/submit/reset/hidden/file/password/image and anything inside `[data-no-save]`.
- Key: radio `r:<name>`; checkbox `c:<id or name:value>`; otherwise `v:<id>`, else `v:<name>`, else `v:#<position>`. Unchecked checkbox saves `""` (deletes the row).
- Debounced (400 ms) PUT on `input`/`change` via event delegation. Restore on load by setting values and dispatching `input`+`change` (with a `restoring` flag so it doesn't re-save). A MutationObserver restores fields the page creates later.
- Small bottom-right pill: Saving… / Saved ✓ / Restored N answers / Not saved ⚠, plus a Reset button (confirm, then DELETE and reload).
- After restoring it dispatches `studyhub:restored` on `document` so page scripts can react (THOR re-checks restored cards). Page scripts that clear fields programmatically must dispatch `input`/`change` so the saver deletes them.

## Deploy (Debian ThinkPad)
- Code in `/srv/studysite`. Caddy: global `auto_https off`, site `http://localhost:8080`, `bind 127.0.0.1`, `root * /srv/studysite/dist`, `encode zstd gzip`, `handle /api/*` -> `reverse_proxy 127.0.0.1:8001`, otherwise `file_server`.
- systemd unit `studysite-api.service` running `python3 /srv/studysite/server.py` as my user, `Restart=on-failure`, `ReadWritePaths=/srv/studysite/data`.
- cloudflared installed from the Cloudflare Zero Trust dashboard (Networks -> Tunnels); public hostname `study.boussaid.me` -> `http://localhost:8080`; Access application with an Allow policy for my email only.
- Update flow: push from my main machine, then on the ThinkPad `git pull && python3 build.py` (no restart needed). Never overwrite `data/`.
- Backup: `sqlite3 data/answers.db ".backup '<path>'"` on a daily cron, plus `/api/export` for a portable copy.

## Writing new remakes (when I give you course material)
- Start from `remake_template.html`. Copy its `study-hub:theme` script and `study-hub:base` style block verbatim; page-specific CSS (SVG classes, palettes) goes in the second `<style>`, using the base tokens. Don't fork the base styles inside a page: change the template, then update every page.
- Lesson skeleton: hero (eyebrow `CODE · Chapter N · Lesson`, h1, lead, figure), `.toc` with parts, numbered `.sec` sections (`.sec-h` with `.num`, h2 + `.fr`, back link), `.plain` "In plain words", `.defs` keywords, `figure.fig` inline SVG, `.calc` worked example, `.note.errata` listing errors in the original course, `.foot`.
- Practice skeleton: same hero with `.prog` progress, `.prob` cards (`.ph` with `.pid` and a `.done` checkbox, `.pq` statement, `<details>` + `.sol`). Auto-checked fields use `.actions` with `.b` buttons, `.mc label.opt` for multiple choice.
- Written in English with the French term in parentheses next to key terms. At least one example per concept, and redo the examples from the original course. Concise, not dense.
- Verify every example by running a program before putting it in.
- Practice pages: keep problems simple and show visual aids (alphabet for Caesar, lookup tables) in `.aid` boxes. The goal is to get used to the algorithm, not to compute by hand; exams don't require hand computation.
- Give every practice field a stable `id` (`q-<problem>-<n>`, `done-<problem>`) and every radio a `value`, so saved answers survive edits. Use `data-no-save` on anything that must not be stored.
- Put files in `modules/<module>/<chapter>/`, the source PDFs in its `cours/`, add the chapter title to `module.json`, run `python3 build.py`.

## Conventions
- Python 3 stdlib only unless I approve a dependency. No frameworks, no build tooling beyond `build.py`.
- Run `python3 build.py` and a quick API check after changes. For anything touching saver.js, test save + reload + restore in a headless browser.
- Don't commit generated output or my answers database.