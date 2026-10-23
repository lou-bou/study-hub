# Setting up Study Hub on a server

Runbook for a fresh Debian machine (written for the ThinkPad, Debian 13). It ends with the site at
`https://study.boussaid.me`, locked to my email by Cloudflare Access. Run every command as my normal
user (`lou`); `sudo` only where shown. Section 10 lists the traps I already fell into.

## What runs where

| Piece | What it does | How it runs |
|---|---|---|
| `build.py` | `modules/` → `dist/` (static site) | by `update.sh`, `ingest.py`, or by hand |
| Caddy | serves `dist/`, proxies `/api/*` | `caddy.service`, `127.0.0.1:8088` |
| `server.py` | answers API + upload/delete queue | `studysite-api.service`, `127.0.0.1:8001`, sandboxed |
| `deploy/ingest.py` | publishes uploads/deletes: place, build, commit, push | `studysite-ingest.path` → `.service`, as `lou` |
| `deploy/update.sh` | pulls new commits + builds; pushes stuck server commits | cron, every 5 min |
| cloudflared | tunnel from Cloudflare to `localhost:8088` | `cloudflared.service` |
| Backup | `answers.db` → Google Drive, 7 rolling copies | cron, 03:00 |

Content (remakes, PDFs) lives in git. Answers live only in `data/answers.db` (never in git), so the Drive
backup is the only copy that survives losing the machine.

## 1. Packages

```bash
sudo apt update && sudo apt install -y git python3 sqlite3 caddy rclone
```

No pip packages: everything is Python standard library.

## 2. Deploy key (read and write)

The server pushes uploads, so it needs a key with write access to this repo only.

```bash
ssh-keygen -t ed25519 -N "" -C thinkpad-studysite -f ~/.ssh/studysite_deploy && cat ~/.ssh/studysite_deploy.pub
```

GitHub → `lou-bou/study-hub` → Settings → Deploy keys → Add deploy key: paste it, tick **Allow write
access**. Deploy keys can't be edited later; to change access, delete and re-add the same key.
No passphrase (`-N ""`): cron and systemd can't type one.

## 3. Clone and build

```bash
sudo mkdir -p /srv/studysite && sudo chown $USER:$USER /srv/studysite
```
```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/studysite_deploy -o IdentitiesOnly=yes" git clone git@github.com:lou-bou/study-hub.git /srv/studysite
```
```bash
cd /srv/studysite && git config core.sshCommand "ssh -i ~/.ssh/studysite_deploy -o IdentitiesOnly=yes" && python3 build.py
```

The code must live in `/srv/studysite`: the units, Caddyfile and cron lines use that path, and the API's
sandbox (`ProtectHome=true`) can't see anything under `/home`.

Test that pushing will work without a prompt:

```bash
git -c core.sshCommand="ssh -o BatchMode=yes -i ~/.ssh/studysite_deploy -o IdentitiesOnly=yes" push --dry-run && echo OK
```

## 4. Answers API

The unit says `User=lou`; the `sed` swaps in the current login if it differs.

```bash
sudo sed "s/^User=lou/User=$USER/" deploy/studysite-api.service | sudo tee /etc/systemd/system/studysite-api.service >/dev/null
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now studysite-api && sleep 2 && curl -s localhost:8001/api/health
```

Expect `{"ok": true}`. Moving from another server? Restore the answers first (section 9).

## 5. Upload worker

```bash
sudo sed "s/^User=lou/User=$USER/" deploy/studysite-ingest.service | sudo tee /etc/systemd/system/studysite-ingest.service >/dev/null
```
```bash
sudo cp deploy/studysite-ingest.path /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now studysite-ingest.path
```

`systemctl status studysite-ingest.path` should say `active (waiting)`: that's its idle state.
Logs of each upload or delete: `journalctl -u studysite-ingest -n 30 --no-pager`.

## 6. Caddy

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl restart caddy && curl -s localhost:8088/api/health && curl -s localhost:8088/ | head -3
```

Port 8088 because qBittorrent holds 8080 on the ThinkPad. If Caddy won't start, check the port:
`sudo ss -ltnp | grep :8088`. If you change the port, change it in the tunnel too.

## 7. Cloudflare Tunnel and Access

`boussaid.me` is on Cloudflare DNS (nameservers `*.ns.cloudflare.com`).

**Tunnel.** The ThinkPad already runs the locally managed tunnel `home-server`
(`/etc/cloudflared/config.yml`, which also serves `ssh.boussaid.me`). Its routes are edited in that
file, not in the dashboard. Add, above the final catch-all:

```yaml
  - hostname: study.boussaid.me
    service: http://localhost:8088
```
```bash
sudo cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate && sudo systemctl restart cloudflared
```
```bash
cloudflared tunnel route dns <tunnel-id> study.boussaid.me
```

On a new server without that tunnel, it's simpler to create a dashboard-managed one: Zero Trust →
Networks → Tunnels → Create → Cloudflared, run the install command it shows, then add the public hostname
`study.boussaid.me` → HTTP → `localhost:8088` in the dashboard (it creates the DNS record).

**Access.** Set this up before anything else can reach the hostname: without it the site, the answers API
and the upload/delete API are public.

1. Zero Trust → Integrations → Identity providers: add **One-time PIN** if it isn't there (a blank page
   after "choose login method" means it's missing).
2. Access → Applications → Add → Self-hosted and private → **Public DNS**: subdomain `study`, domain
   `boussaid.me`, empty path (covers `/api` too).
3. Policy: Allow, Include → Emails → my address. Session duration 1 month. Turn on instant authentication.
4. Test from a phone on mobile data, in a private tab: email code, then the hub.

## 8. Cron: auto-update and backup

**rclone remote** (once): `rclone config` → `n` → name `gdrive` → storage `drive` → empty client id/secret
→ scope `drive.file` (rclone can only see files it created) → no advanced config → **`n`** to auto
config on a headless server. It prints `rclone authorize "drive" "…"`: run that on the laptop
(`winget install Rclone.Rclone`), log in, paste the token back. Then `n` (team drive), `y`, `q`.

Test the upload once:

```bash
sqlite3 /srv/studysite/data/answers.db ".backup /home/$USER/answers-backup.db" && rclone copyto /home/$USER/answers-backup.db gdrive:study-hub-backup/answers-$(date +%a).db && rclone ls gdrive:study-hub-backup
```

Install both cron lines (keeps any other jobs, drops old copies of these):

```bash
(crontab -l 2>/dev/null | grep -v -e 'studysite' -e 'answers.db'; echo "*/5 * * * * /srv/studysite/deploy/update.sh >> \$HOME/studysite-update.log 2>&1"; echo '0 3 * * * sqlite3 /srv/studysite/data/answers.db ".backup /home/'$USER'/answers-backup.db" && rclone copyto /home/'$USER'/answers-backup.db gdrive:study-hub-backup/answers-$(date +\%a).db') | crontab -
```

In a crontab `%` must be written `\%`; on the command line it must not. `crontab -l` should show each
line once. An empty `~/studysite-update.log` is normal: it only logs when there was something to do.

**Laptop as server:** keep it awake with the lid closed:

```bash
sudo sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/; s/^#\?HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf && sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Reboot once afterwards; it also proves every service comes back on its own.

## 9. Moving to a new server

1. On the old server, if it still runs: `cd /srv/studysite && git status && git log @{u}..` must show
   nothing (no unpushed upload commits), then stop it: `sudo systemctl stop studysite-api`.
2. Get the answers: copy `/srv/studysite/data/answers.db` straight from the old machine (best), or the
   latest backup: `rclone lsl gdrive:study-hub-backup` then
   `rclone copyto gdrive:study-hub-backup/answers-<Day>.db /srv/studysite/data/answers.db`.
3. Put it in place **before** starting the API (section 4), with the API stopped if it's already running.
   Check: `curl -s localhost:8001/api/summary`.
4. Point the tunnel at the new machine (move or recreate it) and stop `cloudflared` on the old one.
5. Old server: remove its deploy key from GitHub.

## 10. Things that bit me

- **Blank page through the tunnel, fine with curl.** Caddy's site address must be `http://:8088`, not
  `http://localhost:8088`: the tunnel sends `Host: study.boussaid.me`, and an unmatched host gets an empty
  200 from Caddy.
- **"not found" from a new API route.** `update.sh` pulls code but can't restart services. After a pull
  that changes `server.py` or `add.py`, run `sudo systemctl restart studysite-api` (check the code first
  arrived: `git log --oneline -1`). `ingest.py` and `build.py` changes need nothing: they start fresh each run.
- **Push rejected on the laptop.** The server commits uploads and deletes, so `git pull` before working in
  the repo. `add.py` does it itself.
- **Uploads stuck on "Queued…".** The watcher isn't running: `systemctl status studysite-ingest.path`.
- **Upload "push to GitHub failed".** The commit stays on the server and `update.sh` pushes it within
  5 minutes; if it keeps failing, the deploy key lost write access.
- **SSH from the laptop over the LAN** needs the laptop's public key in `~/.ssh/authorized_keys` (password
  login is off). Check the server's real address with `ip -4 addr`; `192.168.100.19` is the ThinkPad's
  Ethernet and `.79` its Wi-Fi at home.
- **`curl` right after `systemctl restart` prints nothing.** The API needs a second to start; `sleep 2`.
- **Remakes made in the claude.ai project** must use the current `remake_template.html`. When the template's
  base styles change, re-upload it to the project, or the build warns "base styles differ".
- **Site too small.** The build already zooms pages to 150% on wide screens; reset the browser zoom
  (Ctrl+0) or it stacks.

## Checklist

```bash
curl -s localhost:8001/api/health; curl -s -o /dev/null -w " caddy %{http_code}\n" localhost:8088/
```
```bash
systemctl is-active studysite-api caddy cloudflared studysite-ingest.path; crontab -l | grep -c studysite
```

Then from outside: log in at `https://study.boussaid.me`, save an answer on a practice page, reload
(restored), upload a PDF on Manage modules ("Live · saved to GitHub"), delete it again.
