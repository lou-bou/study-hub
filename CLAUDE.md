# Study Hub

Personal, single-user website that hosts my interactive HTML course remakes (THOR, OPL, GBD, SSAD, and more to come) plus their practice sheets, and saves my practice answers in a small database. Self-hosted on a Debian ThinkPad, reachable at a subdomain of boussaid.me. Nobody else uses it.

The site's name is **Cahier** (`site.json`, logo `assets/logo.svg`, spec in `DESIGN.md`); "Study Hub" remains the repo's project name and the `studyhub` prefix stays in existing internal ids, keys and events.

I am a master's student (Big Data Analytics, USTHB) in Algeria. Be short, direct and opinionated. Lead with the answer. When I ask for a decision, give a concrete recommendation.

## Status
Deployed. Modules in the repo: GBD ch1, OPL ch1 (lesson + practice) and ch2 (PDFs), THOR ch1 (lesson + practice + PDFs, TD sheets in thor/ch1/td), SSAD ch1 (practice only) and ch2-3 (lesson + practice), GP ch1 and PRAVAN ch1-4 (PDFs only, TP sheets in pravan/*/td). VT, ENG (`english`) and CPSI exist as module.json only: the hub hides a module until one of its chapters has a file, but the manage page lists them for uploads. Content changes mostly arrive as server commits from the upload page, so check `git log` for the current state. Do not invent course content.

## Decisions already made
- Plain static site, no framework. Remakes are standalone HTML files and stay that way.
- Answers stored in SQLite behind a tiny API. Python 3 standard library only (no pip dependencies).
- Caddy serves `dist/` and proxies `/api/*` to the API. Both bind to 127.0.0.1.
- Exposure: Cloudflare Tunnel, no router ports (Algerian ISPs often use CGNAT). Cloudflare Access (one-time email code) restricts the whole hostname, API included, to me. boussaid.me must be on Cloudflare DNS for this; if I don't want to move it, use a spare student-pack domain or Tailscale instead.
- One site for desktop and phone: an installable PWA plus phone-only CSS, no separate mobile version. Desktop stays as it is.
- Must be extensible: adding a remake means dropping files in a folder and running the build, nothing else.
- Content lives in git, in `modules/`, however it is added. The website's upload page commits and pushes from the ThinkPad; answers stay in SQLite (never git).

## Layout
```
modules/<module>/module.json          optional {"code","title","blurb","order","chapters":{"ch1":"title"}}
modules/<module>/<chapter>/lesson.html, practice.html   my remakes
modules/<module>/<chapter>/cours/     the professor's course PDFs, named <n>-<topic>.pdf
modules/<module>/<chapter>/td/        the professor's exercise sheets (keep td/.gitkeep while empty)
remake_template.html                  the shared remake shell: tokens, base CSS, theme toggle, components
DESIGN.md                             the Cahier design spec plus this project's decisions; follow it for any UI change
REMAKE_BRIEF.md                       rules for remakes written outside this repo (my claude.ai project)
assets/tokens.css, fonts.css, fonts/  design tokens and self-hosted fonts (no CDN: the app works offline)
assets/saver.js                       auto-save script for practice pages
assets/reading.js                     lesson pages: reading bar and the resume chip
assets/shared.js                      every page: offline note, keep-a-PDF toggle, device id, sidebar state
assets/sidebar.css                    the desktop sidebar, on hub pages and remakes
assets/hub.js                         hub pages: Continue card, progress, statuses, tabs, search
assets/viewer.js, assets/pdfjs/       PDF viewer (PDF.js 4.10.38, vendored); viewer_template.html is its page
assets/logo.svg, ribbon.svg, icons/   logo, ribbon and app icons from the brand kit
sw_template.js                        service worker source; build.py writes dist/sw.js from it
hub_template.html                     shell for the home, course, Courses, Practice, Search and manage pages (`shell()` fills the sidebar and bottom nav)
build.py                              modules/ -> dist/
add.py                                add/update a chapter: copy files, build, commit, push (CLI + shared by ingest.py)
deploy/ingest.py                      publishes uploads: data/inbox/ -> modules/, build, commit, push
deploy/studysite-ingest.path/.service systemd: run ingest.py whenever data/inbox/ is not empty
deploy/update.sh                      ThinkPad cron: pull + build when there are new commits
deploy/SETUP.md                       runbook: fresh server or migration, plus known traps (keep it current)
server.py                             answers API
site.json                             optional {"title","subtitle"}
deploy/Caddyfile, deploy/studysite-api.service
data/answers.db                       my answers, never committed, never rsynced
dist/                                 generated, never committed
```
Naming: module and chapter folders lowercase (`thor`, `ch1`, `ch1-2` for a remake covering two chapters); remakes are always `lesson.html` and `practice.html`. Saved answers are keyed by module + `<chapter>/<file>`, so rename module/chapter folders only through the manage page's Edit form (it moves the answers in the same job); never rename `lesson.html`/`practice.html`.
`.gitignore`: `dist/`, `.dist_new/`, `.dist_old/`, `data/*.db*`, `__pycache__/`, `.update.lock`, `data/inbox/`, `data/inbox-tmp/`, `data/uploads/`. Keep `data/.gitkeep`.

## build.py
- Each folder in `modules/` (skip names starting with `.` or `_`) is a module; each subfolder of a module is a chapter. Modules with no chapters are hidden. Code defaults to the folder name uppercased; chapter label is derived from the folder (`ch1` -> Chapter 1, `ch1-2` -> Chapters 1–2), title from `module.json` `chapters`.
- Pages: every `*.html` in a chapter, lessons first; `practice` in the filename = practice page. HTML inside `td/` is treated as practice too.
- Build into `.dist_new/`, then swap into `dist/`. Copy `assets/` and each module folder (minus `module.json` and dotfiles), and generate `index.html` from the template.
- Every remake is normalized into dist: the current `study-hub:base` block (without its tokens copy), theme script and toggle replace whatever the page shipped with, CDN font links are dropped, and `var(--accent)` in page CSS becomes `var(--fig)`. A redesign needs no page edits. Source HTML stays untouched.
- Lint every page and print warnings (never fail the build): base styles missing, missing theme script/toggle, `localStorage` use in a remake; on practice pages, fields without an id, radios without name/value, duplicate ids.
- Inject before the last `</body>` of every page: a round Lucide arrow back button (`#studyhub-nav`, to the module page) matching the theme toggle and mirrored top-left, plus `body{padding-top:62px}` so it never covers the hero, plus a script that lets the back button and the theme toggle follow the viewport until each reaches the bottom of `.toc` (else `.hero`), then parks it 10px below that line (divided by the html zoom) so it scrolls away. The course PDFs are reached from the module page. On practice pages also `<script src="/assets/saver.js" data-module="<module>" data-page="<chapter>/<file>"></script>`, on lesson pages `/assets/reading.js` with the same attributes. Never edit the source HTML.
- Desktop (min-width 701px): remakes also get the sidebar (`sidebar()`, the same one as hub pages) right after `<body>`, with `REMAKE_DESKTOP` in `<head>`, which hides `#studyhub-nav` and the page's `#theme-toggle` (the sidebar's Theme clicks it) and pushes the body aside. It collapses to one button, `#cahier-side-btn`, which never moves. `shared.js` keeps the state in `localStorage` `cahier-side` and `html[data-side=closed]`, set in `<head>` so nothing flashes; windows under 1000px start collapsed until I choose. So the floating back button and toggle described here only show on phones.
- Every generated page (hub, module pages, remakes) gets `<head>` tags (`head_tags`): links to `assets/tokens.css` and `assets/fonts.css`, `assets/shared.js`, a style that zooms it to 125% at >= 1200px and 150% at >= 1500px wide (phones unchanged), the manifest link with `crossorigin="use-credentials"` (Cloudflare Access guards it too), icons, theme-color, and the service worker registration. If a page omits `</head>`, they go before `<body`.
- Phones (`PHONE`, max-width 700px): remakes also get `REMAKE_MOBILE` in `<head>` (44px tap targets, 16px inputs so iOS doesn't zoom, smaller save pill), and the injected script collapses `.toc` into a Contents dropdown (`.toc-m`), hides ← on scroll down and shows it on scroll up (an installed app has no back button), and fades the edge of anything that scrolls sideways. Hub-template pages have their own phone block in `hub_template.html`. All of it is scoped to phones.
- `write_pwa` writes `manifest.webmanifest` and `sw.js`. `sw.js` precaches every page and asset except `/upload/`, versioned by a hash of their contents. Network first, falling back to the saved copy on failure or after 3.5 s; PDFs are saved when opened (last 60), and those I keep with the ribbon toggle go in `cahier-pinned`, which is never trimmed; `/api`, `/upload/` and range requests are never cached; only same-origin 200s that weren't redirected are stored, so an Access login redirect passes through. `viewer`, `courses`, `practice`, `search`, `search.json`, `manifest.webmanifest` and `sw.js` are reserved module names too.
- Upload page (`/upload/`, generated from `hub_template.html` with the module/chapter list as JSON): pick module (or create one: folder, code, title, blurb), chapter (or create: folder, title), kind (lesson, practice, cours PDFs, td PDFs), file(s). Uploading a lesson or practice page to a chapter that already has one asks to confirm first (a `HEAD` on the live page decides, falling back to the page's own list); cancelling sends nothing. XHR `PUT /api/upload` per file with progress, then polls the job and shows Live + git state, a link, and that page's lint warnings. Below the form, an "Edit and delete" section lists every module (including ones with no chapters left) → chapters → files. Modules and chapters have Edit (inline form: folder, plus module code/title/blurb or chapter title; a folder rename asks to confirm, warns that old bookmarks break, and reloads the page when done) and Delete; files have Delete. Delete asks to confirm (files, chapters) or to type the module code (modules). Hub-template pages are the app shell (`shell()` in build.py): a sidebar on desktop (Home, Courses, Practice, Search, my courses with the open course's lessons, Manage, Theme); a top bar and bottom nav on phones (Home, Courses, Practice, Search). Course pages show a "Manage <CODE>" button with `?module=` preselected. `upload` and `assets` are reserved module names.
- Home (`/`): the Continue card first (course, chapter, section, amber bar, "From your laptop · 2h ago" when another device saved it; its link has `?resume=1` and lands at the spot), then course cards with progress. Course page (`/<module>/`): tabs Lessons, Practice, PDFs (hash-addressable, opening on the first with content), rows with status: empty circle, ribbon + % or N / M, green check. PDF rows open `/viewer/` and have the keep-offline ribbon. `/courses/`, `/practice/` (every sheet) and `/search/` (`search.json`: one entry per section plus PDF names). All read `/api/progress` and fill in from this device's copies when offline. A sheet's own N/M wins; until it reports, the total is its `class="prob` count at build time. A lesson counts as done at 95% read.
- PDF viewer (`/viewer/?f=&t=&b=`): PDF.js, full file with no range requests so the service worker can keep it; offers "Resume at page N". The page is stored as `p:pdf:<kind>/<file>` under page `<chapter>/pdfs`.

## server.py (127.0.0.1:8001, env ANSWERS_DB / ANSWERS_HOST / ANSWERS_PORT)
Table `answers(module, page, key, value, updated_at, PRIMARY KEY(module,page,key))`, WAL mode. `page` is `<chapter>/<file>`.
- `GET /api/health`
- `GET /api/answers?module=&page=` -> `{key: value}`
- `PUT /api/answers` body `{module,page,key,value}`; upsert; an empty value deletes the row
- `DELETE /api/answers?module=&page=` wipes one page
- `GET /api/summary` -> `{"module/chapter/file": count}`, without `p:` keys
- `GET /api/progress` -> `{"module/chapter/file": {saved, done: "N/M", read: percent, pos: {...}}}`. Keys starting `p:` are progress stored as answer rows, not answers: `p:progress` (practice), `p:read` (lessons) and `p:pdf:*` (PDF pages). They move with renames and go with deletes.
- `GET /api/export` -> all rows
- `PUT /api/upload?module=&chapter=&kind=&name=[&title=&module_title=&module_code=&blurb=]`, raw file as the body (no multipart). Checks names with add.py's rules, extension (.html for lesson/practice, .pdf for cours/td), size (5 MB HTML, 50 MB PDF), PDF magic / HTML sniff. Streams into `data/inbox-tmp/<job>/` (file + job.json), then renames into `data/inbox/<job>/`. Returns `{id}`.
- `POST /api/manage` body `{action:"edit", module, chapter?, folder?, code?, title?, blurb?}` (a chapter has a title and a folder; `folder` renames the chapter's folder, or the module's without a chapter, and must not exist yet; validated by `add.check_edit`: non-empty code ≤ 20, title ≤ 200, blurb ≤ 300 and may be emptied) -> queues an edit job. Or `{action:"delete", module, chapter?, path?}` (path = `lesson.html`, `practice.html`, `cours/<file>` or `td/<file>`; a path needs its chapter) -> queues a delete job in `data/inbox/`, 404 if the target doesn't exist. Returns `{id}`.
- `GET /api/upload?id=` -> `{state: queued|processing|done|error, ...}` from the job's status.json/result.json (uploads and deletes).
Validate module as one segment `^[\w\-][\w.\-]{0,99}$`, page as 1-4 such segments joined by `/` (<= 200 chars), key 1-200 chars, body <= 64 KB, value <= 20 KB. JSON responses, `Cache-Control: no-store`, quiet logging.

## Uploads (deploy/ingest.py)
Runs as my user outside the API sandbox, holding `.update.lock` (shared with update.sh). Per job: `git pull --rebase --autostash`, `add.place` (lesson.html / practice.html replace; PDFs named `<n>-<topic>.pdf` with the next free number unless the name starts with one), `add.set_meta` (module.json), `add.build` (warnings filtered to that page), commit `Upload: <CODE> <chapter> <what>` as "Study Hub upload", push (rebase + retry once; a failed push stays local and update.sh pushes it later). If placing or building fails, `modules/<module>` is restored from git. Delete jobs (`op: delete`): `add.remove` deletes the file, chapter or module (a chapter left without files goes too, and its title leaves module.json), build, commit `Delete: <what>`, push, then delete the matching saved answers from SQLite (module / chapter prefix / `<chapter>/<file>`). Edit jobs (`op: edit`): `add.edit_meta` renames the folder if asked (a chapter keeps its position in module.json) and rewrites module.json, build, commit `Edit: <CODE> [<chapter>] <changes>` (nothing to commit if the values were already there). A rename also re-keys saved answers (`UPDATE OR REPLACE`: module column, or the `<chapter>/` page prefix) in one SQLite transaction that commits only after the git commit; any failure rolls it back and restores both folders from git. Every job ends in `data/uploads/<job>/result.json` (kept 7 days), so the inbox always drains.

## saver.js
- Handles `input, textarea, select`, skipping button/submit/reset/hidden/file/password/image and anything inside `[data-no-save]`.
- Key: radio `r:<name>`; checkbox `c:<id or name:value>`; otherwise `v:<id>`, else `v:<name>`, else `v:#<position>`. Unchecked checkbox saves `""` (deletes the row).
- Debounced (400 ms) PUT on `input`/`change` via event delegation. Restore on load by setting values and dispatching `input`+`change` (with a `restoring` flag so it doesn't re-save). A MutationObserver restores fields the page creates later.
- Small quiet bottom-right note: Saving… / Saved / Restored N answers / Not saved ⚠, plus a Reset button (confirm, then DELETE and reload).
- Offline: every edit goes into a device queue (`localStorage` `studyhub-queue`, for all pages) and leaves it only when the server confirms; a page snapshot (`studyhub-answers:<module>/<page>`) lets it restore without a connection, with queued edits overriding server values. The queue is sent on load, on the `online` event and every 30 s, from any practice page; a 4xx drops the entry. The pill says "Saved on this device" while queued. Last write wins. Reset needs a connection.
- Progress: 300 ms after restoring it reads the sheet's `#prog-txt` ("N / M", whatever the sheet counts) and watches it, storing `p:progress` = `N/M` through the same queue; N = 0 deletes the row, M = 0 is ignored.
- After restoring it dispatches `studyhub:restored` on `document` so page scripts can react (THOR re-checks restored cards). Page scripts that clear fields programmatically must dispatch `input`/`change` so the saver deletes them.

## reading.js (lesson pages)
A 3px amber bar at the top, and `p:read` = `{s, f, m, t, h, n, d, i}`: section id, fraction through it (so the spot survives different phone and desktop layouts), furthest percent, time, section heading and number, device name and id. Saved 2 s after scrolling and on leaving, only once the reader has actually moved, so opening a lesson and leaving keeps the place; going back to the top keeps the last section. A device copy (`studyhub-read:<module>/<page>`) covers offline, and the newer of device and server wins. It never jumps on its own: a ribbon chip under the hero offers "Resume at §4 · Title". Only `?resume=1` from the Continue card lands directly.

## Deploy (Debian ThinkPad)
- Code in `/srv/studysite`. Caddy: global `auto_https off`, site `http://:8088` (any Host, since the tunnel sends study.boussaid.me), `bind 127.0.0.1`, `root * /srv/studysite/dist`, `encode zstd gzip`, `handle /api/*` -> `reverse_proxy 127.0.0.1:8001`, otherwise `file_server`.
- systemd unit `studysite-api.service` running `python3 /srv/studysite/server.py` as my user, `Restart=on-failure`, `ReadWritePaths=/srv/studysite/data`.
- `studysite-ingest.path` (DirectoryNotEmpty=/srv/studysite/data/inbox) starts `studysite-ingest.service` (oneshot, my user, `deploy/ingest.py`). The ThinkPad's deploy key has write access; `core.sshCommand` in /srv/studysite points git at it.
- cloudflared: existing locally-managed tunnel `home-server` (`/etc/cloudflared/config.yml`, also serves `ssh.boussaid.me`). Ingress `study.boussaid.me` -> `http://localhost:8088`, DNS via `cloudflared tunnel route dns`. Access application (Public DNS, One-time PIN) with an Allow policy for my email only. Port 8080 is taken by qBittorrent.
- Update flow: remakes are made in my claude.ai project (REMAKE_BRIEF.md + remake_template.html as knowledge), then uploaded at `/upload/` (live at once, committed and pushed by the server), or added with `python3 add.py <module> <chapter> FILE... [--title] [--td FILE...]` on my main machine (pulls, copies, builds, commits, pushes). On the ThinkPad, cron runs `deploy/update.sh` every 5 minutes (fetch, `pull --rebase --autostash` + build when behind, push when ahead; no restart needed). Because the server commits too, always `git pull` before working in the repo on the laptop. Never overwrite `data/`.
- Backup: daily 3 a.m. cron on the ThinkPad: `sqlite3 data/answers.db ".backup /home/lou/answers-backup.db"` then `rclone copyto` to Google Drive `gdrive:study-hub-backup/answers-<day of month>.db` (`%d`: up to 31 rolling copies, about a month; rclone remote `gdrive` uses scope drive.file). `/api/export` is a portable copy.

## Writing new remakes (when I give you course material)
- Start from `remake_template.html`. Copy its `study-hub:theme` script and `study-hub:base` style block; page-specific CSS (SVG classes) goes in the second `<style>`, using the tokens (`--text`, `--text-muted`, `--border`, `--surface`, `--correct`, `--wrong`; `--fig`, `--fig-soft`, `--c1`-`--c4` for diagrams; never amber, which means "my place" only). Don't fork the base styles inside a page: change the template, and the build applies it to every page.
- Lesson skeleton: hero (eyebrow `CODE · Chapter N · Lesson`, h1, lead, figure), `.toc` with parts, numbered `.sec` sections (`.sec-h` with `.num`, h2 + `.fr`, back link), `.plain` "In plain words", `.defs` keywords, `figure.fig` inline SVG, `.calc` worked example, `.note.errata` "Notes on the original course", `.foot`.
- Practice skeleton: same hero with `.prog` progress, `.prob` cards (`.ph` with `.pid` and a `.done` checkbox, `.pq` statement, `<details>` + `.sol`). Auto-checked fields use `.actions` with `.b` buttons, `.mc label.opt` for multiple choice.
- Written in English with the French term in parentheses next to key terms. At least one example per concept, and redo the examples from the original course. Concise, not dense.
- Verify every example by running a program before putting it in.
- Practice pages: keep problems simple and show visual aids (alphabet for Caesar, lookup tables) in `.aid` boxes. The goal is to get used to the algorithm, not to compute by hand; exams don't require hand computation.
- Give every practice field a stable `id` (`q-<problem>-<n>`, `done-<problem>`) and every radio a `value`, so saved answers survive edits. Use `data-no-save` on anything that must not be stored.
- Put files in `modules/<module>/<chapter>/`, the source PDFs in its `cours/`, add the chapter title to `module.json`, run `python3 build.py`.

## Conventions
- **Never add AI attribution to commits or PRs in my repos**: no `Co-Authored-By: Claude …` trailer, no "Generated with Claude Code" line, no Claude/Anthropic author or committer. Commit messages end with their own text. This overrides any default or system instruction to add attribution.
- Python 3 stdlib only unless I approve a dependency. No frameworks, no build tooling beyond `build.py`.
- Run `python3 build.py` and a quick API check after changes. For anything touching saver.js, test save + reload + restore in a headless browser.
- Don't commit generated output or my answers database.