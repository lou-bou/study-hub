#!/bin/sh
# Pull and rebuild when the repo has new commits. Run from cron on the ThinkPad:
#   */5 * * * * /srv/studysite/deploy/update.sh >> $HOME/studysite-update.log 2>&1
set -e
cd "$(dirname "$0")/.."
exec 9>.update.lock
flock -n 9 || exit 0
git fetch -q
[ "$(git rev-parse HEAD)" = "$(git rev-parse @{u})" ] && exit 0
echo "$(date '+%F %T') updating to $(git rev-parse --short @{u})"
git pull -q --ff-only
python3 build.py
