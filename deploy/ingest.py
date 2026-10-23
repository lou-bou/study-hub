#!/usr/bin/env python3
"""Publish uploads: data/inbox/<job>/ -> modules/, build, commit, push. Python 3 stdlib only.

Started by studysite-ingest.path whenever the inbox is not empty. Runs as my user, outside the
API's sandbox, because it needs git and the deploy key. Every job ends in data/uploads/<job>/
with a result.json the upload page polls, so a bad job can't keep the inbox busy.

Env: ANSWERS_DB, as for server.py (the inbox lives next to the database).
"""
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import add  # noqa: E402

DATA = os.path.dirname(os.path.abspath(os.environ.get("ANSWERS_DB", os.path.join(ROOT, "data", "answers.db"))))
INBOX = os.path.join(DATA, "inbox")
DONE = os.path.join(DATA, "uploads")
LOCK = os.path.join(ROOT, ".update.lock")  # shared with deploy/update.sh
IDENT = ("Study Hub upload", "upload@study.boussaid.me")
KEEP_DAYS = 7


def write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def process(job_dir):
    with open(os.path.join(job_dir, "job.json"), encoding="utf-8") as f:
        job = json.load(f)
    write(os.path.join(job_dir, "status.json"), {"state": "processing"})
    m, ch, kind = job["module"], job["chapter"], job["kind"]
    add.sync()
    try:
        rel, replaced = add.place(m, ch, kind, os.path.join(job_dir, "file"), job["name"])
        add.set_meta(m, ch, job.get("title"), job.get("module_title"), job.get("module_code"), job.get("blurb"))
        _, warnings = add.build()
    except Exception:
        # leave modules/ as git has it, so the next job doesn't commit half of this one
        mod = os.path.join(ROOT, "modules", m)
        subprocess.run(["git", "-C", ROOT, "checkout", "-q", "--", mod], capture_output=True)
        subprocess.run(["git", "-C", ROOT, "clean", "-fdq", "--", mod], capture_output=True)
        raise
    prefix = f"modules/{m}/{ch}/{rel}: "
    what = kind if kind in ("lesson", "practice") else f"{kind} {os.path.basename(rel)}"
    state = add.commit_and_push([os.path.join("modules", m)], f"Upload: {m.upper()} {ch} {what}", ident=IDENT)
    return {"state": "done", "url": f"/{m}/{ch}/{rel}", "replaced": replaced, "git": state,
            "warnings": [w[len(prefix):] for w in warnings if w.startswith(prefix)]}


def cleanup():
    cutoff = time.time() - KEEP_DAYS * 86400
    for name in os.listdir(DONE):
        path = os.path.join(DONE, name)
        if os.path.getmtime(path) < cutoff:
            shutil.rmtree(path, ignore_errors=True)


def main():
    os.makedirs(DONE, exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # waits for a running update.sh
        while True:
            jobs = sorted(n for n in os.listdir(INBOX) if not n.startswith(".")) if os.path.isdir(INBOX) else []
            if not jobs:
                break
            for name in jobs:
                src = os.path.join(INBOX, name)
                try:
                    result = process(src)
                except Exception as e:  # noqa: BLE001 - reported to the upload page
                    result = {"state": "error", "error": str(e)}
                print(f"{time.strftime('%F %T')} {name}: {json.dumps(result, ensure_ascii=False)}", flush=True)
                if os.path.isdir(src):
                    try:
                        os.remove(os.path.join(src, "file"))
                    except OSError:
                        pass
                    write(os.path.join(src, "result.json"), result)
                    shutil.rmtree(os.path.join(DONE, name), ignore_errors=True)
                    os.replace(src, os.path.join(DONE, name))
                else:  # a stray file in the inbox
                    os.remove(src)
        cleanup()


if __name__ == "__main__":
    main()
