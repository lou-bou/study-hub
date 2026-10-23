# Study Hub

Personal, single-user website that hosts my interactive HTML course remakes (THOR, OPL, GBD, SSAD, and more to come) plus their practice sheets, and saves my practice answers in a small database. Self-hosted on a Debian ThinkPad, reachable at a subdomain of boussaid.me. Nobody else uses it.

I am a master's student (Big Data Analytics, USTHB) in Algeria. Be short, direct and opinionated. Lead with the answer. When I ask for a decision, give a concrete recommendation.

## Status
Deployed. Modules in the repo: GBD ch1, OPL ch1-2, THOR ch1 (lesson + practice + PDFs, TD sheets in thor/ch1/td), SSAD ch1 (practice only) and ch2-3 (lesson + practice), GP ch1 and PRAVAN ch1-4 (PDFs only, TP sheets in pravan/*/td). Empty module folders (cpsi, vt) exist locally only; git doesn't track empty dirs and the build hides modules without chapters. Do not invent course content.

## Decisions already made
- Plain static site, no framework. Remakes are standalone HTML files and stay that way.
- Answers stored in SQLite behind a tiny API. Python 3 standard library only (no pip dependencies).
- Caddy serves `dist/` and proxies `/api/*` to the API. Both bind to 127.0.0.1.
- Exposure: Cloudflare Tunnel, no router ports (Algerian ISPs often use CGNAT). Cloudflare Access (one-time email code) restricts the whole hostname, API included, to me. boussaid.me must be on Cloudflare DNS for this; if I don't want to move it, use a spare student-pack domain or Tailscale instead.
- Must be extensible: adding a remake means dropping files in a folder and running the build, nothing else.
- Content lives in git, in `modules/`, however it is added. The website's upload page commits and pushes from the ThinkPad; answers stay in SQLite (never git).

## Layout
```
modules/<module>/module.json          optional {"code","title","blurb","order","chapters":{"ch1":"title"}}
modules/<module>/<chapter>/lesson.html, practice.html   my remakes
modules/<module>/<chapter>/cours/     the professor's course PDFs, named <n>-<topic>.pdf
modules/<module>/<chapter>/td/        the professor's exercise sheets (keep td/.gitkeep while empty)
remake_template.html                  the shared remake shell: base CSS, theme toggle, components
REMAKE_BRIEF.md                       rules for remakes written outside this repo (my claude.ai project)
assets/saver.js                       auto-save script for practice pages
hub_template.html                     shell for the hub and module pages (%%PAGETITLE%% %%BACK%% %%EYEBROW%% %%TITLE%% %%SUB%% %%STATS%% %%MAIN%%)
build.py                              modules/ -> dist/
add.py                                add/update a chapter: copy files, build, commit, push (CLI + shared by ingest.py)
deploy/ingest.py                      publishes uploads: data/inbox/ -> modules/, build, commit, push
deploy/studysite-ingest.path/.service systemd: run ingest.py whenever data/inbox/ is not empty
deploy/update.sh                      ThinkPad cron: pull + build when there are new commits
server.py                             answers API
site.json                             optional {"title","subtitle"}
deploy/Caddyfile, deploy/studysite-api.service
data/answers.db                       my answers, never committed, never rsynced
dist/                                 generated, never committed
```
Naming: module and chapter folders lowercase (`thor`, `ch1`, `ch1-2` for a remake covering two chapters); remakes are always `lesson.html` and `practice.html`. Saved answers are keyed by module + `<chapter>/<file>`, so don't rename those once answers exist.
`.gitignore`: `dist/`, `.dist_new/`, `.dist_old/`, `data/*.db*`, `__pycache__/`, `.update.lock`, `data/inbox/`, `data/inbox-tmp/`, `data/uploads/`. Keep `data/.gitkeep`.

## build.py
- Each folder in `modules/` (skip names starting with `.` or `_`) is a module; each subfolder of a module is a chapter. Modules with no chapters are hidden. Code defaults to the folder name uppercased; chapter label is derived from the folder (`ch1` -> Chapter 1, `ch1-2` -> Chapters 1–2), title from `module.json` `chapters`.
- Pages: every `*.html` in a chapter, lessons first; `practice` in the filename = practice page. HTML inside `td/` is treated as practice too.
- Build into `.dist_new/`, then swap into `dist/`. Copy `assets/` and each module folder (minus `module.json` and dotfiles), and generate `index.html` from the template.
- Lint every page and print warnings (never fail the build): base styles missing or not identical to `remake_template.html`, missing theme script/toggle, `localStorage` use; on practice pages, fields without an id, radios without name/value, duplicate ids.
- Inject before the last `</body>` of every page: a fixed bottom-left bar with "← <CODE>" (back to the module page) and links to the chapter's course PDFs, plus a script that lets the bar and the theme toggle follow the viewport until each reaches the bottom of `.toc` (else `.hero`), then parks it just below that line so it scrolls away. On practice pages also `<script src="/assets/saver.js" data-module="<module>" data-page="<chapter>/<file>"></script>`. Never edit the source HTML.
- Every generated page (hub, module pages, remakes) gets a `<head>` style that zooms it to 125% at >= 1200px and 150% at >= 1500px wide; phones are unchanged.
- Upload page (`/upload/`, generated from `hub_template.html` with the module/chapter list as JSON): pick module (or create one: folder, code, title, blurb), chapter (or create: folder, title), kind (lesson, practice, cours PDFs, td PDFs), file(s). XHR `PUT /api/upload` per file with progress, then polls the job and shows Live + git state, a link, and that page's lint warnings. Below the form, a Delete section lists every module (including ones with no chapters left) → chapters → files, each with a delete button: confirm for files and chapters, type the module code for a module. The hub links to it as "Manage modules"; module pages link as "Manage <CODE>" with `?module=` preselected. `upload` and `assets` are reserved module names.
- Hub (`/`): one clickable card per module with only the code chip, title and blurb. Module page (`/<module>/`, generated `index.html`): one `<details>` dropdown per chapter (open by default when the module has a single chapter), listing Remakes (Lesson, Practice), Cours and TD; PDFs open in a new tab. Both pages use `hub_template.html`, the remakes' tokens and fonts, and a theme toggle. Practice links get a badge from `/api/summary` ("N saved"); the saved total is scoped to the module on module pages.

## server.py (127.0.0.1:8001, env ANSWERS_DB / ANSWERS_HOST / ANSWERS_PORT)
Table `answers(module, page, key, value, updated_at, PRIMARY KEY(module,page,key))`, WAL mode. `page` is `<chapter>/<file>`.
- `GET /api/health`
- `GET /api/answers?module=&page=` -> `{key: value}`
- `PUT /api/answers` body `{module,page,key,value}`; upsert; an empty value deletes the row
- `DELETE /api/answers?module=&page=` wipes one page
- `GET /api/summary` -> `{"module/chapter/file": count}`
- `GET /api/export` -> all rows
- `PUT /api/upload?module=&chapter=&kind=&name=[&title=&module_title=&module_code=&blurb=]`, raw file as the body (no multipart). Checks names with add.py's rules, extension (.html for lesson/practice, .pdf for cours/td), size (5 MB HTML, 50 MB PDF), PDF magic / HTML sniff. Streams into `data/inbox-tmp/<job>/` (file + job.json), then renames into `data/inbox/<job>/`. Returns `{id}`.
- `POST /api/manage` body `{action:"delete", module, chapter?, path?}` (path = `lesson.html`, `practice.html`, `cours/<file>` or `td/<file>`; a path needs its chapter) -> queues a delete job in `data/inbox/`, 404 if the target doesn't exist. Returns `{id}`.
- `GET /api/upload?id=` -> `{state: queued|processing|done|error, ...}` from the job's status.json/result.json (uploads and deletes).
Validate module as one segment `^[\w\-][\w.\-]{0,99}$`, page as 1-4 such segments joined by `/` (<= 200 chars), key 1-200 chars, body <= 64 KB, value <= 20 KB. JSON responses, `Cache-Control: no-store`, quiet logging.

## Uploads (deploy/ingest.py)
Runs as my user outside the API sandbox, holding `.update.lock` (shared with update.sh). Per job: `git pull --rebase --autostash`, `add.place` (lesson.html / practice.html replace; PDFs named `<n>-<topic>.pdf` with the next free number unless the name starts with one), `add.set_meta` (module.json), `add.build` (warnings filtered to that page), commit `Upload: <CODE> <chapter> <what>` as "Study Hub upload", push (rebase + retry once; a failed push stays local and update.sh pushes it later). If placing or building fails, `modules/<module>` is restored from git. Delete jobs (`op: delete`): `add.remove` deletes the file, chapter or module (a chapter left without files goes too, and its title leaves module.json), build, commit `Delete: <what>`, push, then delete the matching saved answers from SQLite (module / chapter prefix / `<chapter>/<file>`). Every job ends in `data/uploads/<job>/result.json` (kept 7 days), so the inbox always drains.

## saver.js
- Handles `input, textarea, select`, skipping button/submit/reset/hidden/file/password/image and anything inside `[data-no-save]`.
- Key: radio `r:<name>`; checkbox `c:<id or name:value>`; otherwise `v:<id>`, else `v:<name>`, else `v:#<position>`. Unchecked checkbox saves `""` (deletes the row).
- Debounced (400 ms) PUT on `input`/`change` via event delegation. Restore on load by setting values and dispatching `input`+`change` (with a `restoring` flag so it doesn't re-save). A MutationObserver restores fields the page creates later.
- Small bottom-right pill: Saving… / Saved ✓ / Restored N answers / Not saved ⚠, plus a Reset button (confirm, then DELETE and reload).
- After restoring it dispatches `studyhub:restored` on `document` so page scripts can react (THOR re-checks restored cards). Page scripts that clear fields programmatically must dispatch `input`/`change` so the saver deletes them.

## Deploy (Debian ThinkPad)
- Code in `/srv/studysite`. Caddy: global `auto_https off`, site `http://:8088` (any Host, since the tunnel sends study.boussaid.me), `bind 127.0.0.1`, `root * /srv/studysite/dist`, `encode zstd gzip`, `handle /api/*` -> `reverse_proxy 127.0.0.1:8001`, otherwise `file_server`.
- systemd unit `studysite-api.service` running `python3 /srv/studysite/server.py` as my user, `Restart=on-failure`, `ReadWritePaths=/srv/studysite/data`.
- `studysite-ingest.path` (DirectoryNotEmpty=/srv/studysite/data/inbox) starts `studysite-ingest.service` (oneshot, my user, `deploy/ingest.py`). The ThinkPad's deploy key has write access; `core.sshCommand` in /srv/studysite points git at it.
- cloudflared: existing locally-managed tunnel `home-server` (`/etc/cloudflared/config.yml`, also serves `ssh.boussaid.me`). Ingress `study.boussaid.me` -> `http://localhost:8088`, DNS via `cloudflared tunnel route dns`. Access application (Public DNS, One-time PIN) with an Allow policy for my email only. Port 8080 is taken by qBittorrent.
- Update flow: remakes are made in my claude.ai project (REMAKE_BRIEF.md + remake_template.html as knowledge), then uploaded at `/upload/` (live at once, committed and pushed by the server), or added with `python3 add.py <module> <chapter> FILE... [--title] [--td FILE...]` on my main machine (pulls, copies, builds, commits, pushes). On the ThinkPad, cron runs `deploy/update.sh` every 5 minutes (fetch, `pull --rebase --autostash` + build when behind, push when ahead; no restart needed). Because the server commits too, always `git pull` before working in the repo on the laptop. Never overwrite `data/`.
- Backup: daily 3 a.m. cron on the ThinkPad: `sqlite3 data/answers.db ".backup /home/lou/answers-backup.db"` then `rclone copyto` to Google Drive `gdrive:study-hub-backup/answers-<weekday>.db` (7 rolling copies; rclone remote `gdrive` uses scope drive.file). `/api/export` is a portable copy.

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