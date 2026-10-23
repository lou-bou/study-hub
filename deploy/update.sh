#!/bin/sh
# Pull and rebuild when the repo has new commits, and push uploads the server committed but
# couldn't push. Run from cron on the ThinkPad:
#   */5 * * * * /srv/studysite/deploy/update.sh >> $HOME/studysite-update.log 2>&1
set -e
cd "$(dirname "$0")/.."
exec 9>.update.lock
flock -n 9 || exit 0  # deploy/ingest.py holds the same lock while it publishes an upload
git fetch -q
if [ "$(git rev-list --count HEAD..@{u})" != 0 ]; then
  echo "$(date '+%F %T') updating to $(git rev-parse --short @{u})"
  git pull -q --rebase --autostash
  python3 build.py
fi
if [ "$(git rev-list --count @{u}..HEAD)" != 0 ]; then
  git push -q && echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD)"
fi
