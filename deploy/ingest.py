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
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import add  # noqa: E402

DB = os.path.abspath(os.environ.get("ANSWERS_DB", os.path.join(ROOT, "data", "answers.db")))
DATA = os.path.dirname(DB)
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


def restore(*mods):
    """Leave modules/<m> as git has it, so the next job doesn't commit half of this one."""
    for m in mods:
        mod = os.path.join(ROOT, "modules", m)
        subprocess.run(["git", "-C", ROOT, "checkout", "-q", "--", mod], capture_output=True)
        subprocess.run(["git", "-C", ROOT, "clean", "-fdq", "--", mod], capture_output=True)


def move_answers(conn, m, ch, folder):
    """Re-key saved answers for a renamed module (ch None) or chapter. Runs inside the caller's
    transaction, so it only sticks if the rename is committed. OR REPLACE drops stale rows that
    already sat under the new name."""
    if ch is None:
        return conn.execute("UPDATE OR REPLACE answers SET module=? WHERE module=?", (folder, m)).rowcount
    return conn.execute(
        "UPDATE OR REPLACE answers SET page=? || substr(page, ?) WHERE module=? AND substr(page, 1, ?)=?",
        (folder + "/", len(ch) + 2, m, len(ch) + 1, ch + "/")).rowcount


def forget_answers(m, ch=None, path=None):
    """Saved answers of what was deleted. Lessons and PDFs have none, so only practice pages count."""
    if not os.path.exists(DB):
        return 0
    if ch is None:
        sql, args = "DELETE FROM answers WHERE module=?", (m,)
    elif path is None:
        sql, args = "DELETE FROM answers WHERE module=? AND page LIKE ? ESCAPE '\\'", (m, ch.replace("_", "\\_") + "/%")
    else:
        sql, args = "DELETE FROM answers WHERE module=? AND page=?", (m, f"{ch}/{path}")
    conn = sqlite3.connect(DB, timeout=10)
    try:
        with conn:
            return conn.execute(sql, args).rowcount
    finally:
        conn.close()


def delete(job):
    m, ch, path = job["module"], job.get("chapter"), job.get("path")
    add.sync()
    try:
        what = add.remove(m, ch, path)
        add.build()
    except Exception:
        restore(m)
        raise
    state = add.commit_and_push([os.path.join("modules", m)], f"Delete: {what}", ident=IDENT)
    return {"state": "done", "deleted": what, "git": state, "answers_deleted": forget_answers(m, ch, path)}


def edit(job):
    m, ch, folder = job["module"], job.get("chapter"), job.get("folder")
    add.sync()
    renames_module = folder is not None and ch is None
    conn = sqlite3.connect(DB, timeout=10) if folder is not None and os.path.exists(DB) else None
    try:
        moved = move_answers(conn, m, ch, folder) if conn else 0
        what = add.edit_meta(m, ch, job.get("code"), job.get("title"), job.get("blurb"), folder)
        add.build()
        if not what:
            if conn:
                conn.rollback()
            return {"state": "done", "edited": "", "git": "unchanged"}
        paths = [os.path.join("modules", m)] + ([os.path.join("modules", folder)] if renames_module else [])
        where = f"{m.upper()} {ch}" if ch else m.upper()
        state = add.commit_and_push(paths, f"Edit: {where} {what}", ident=IDENT)
    except Exception:
        if conn:
            conn.rollback()
        restore(m, *([folder] if renames_module else []))
        raise
    finally:
        if conn and conn.in_transaction:
            conn.commit()  # reached only after a successful commit (rollback above otherwise)
        if conn:
            conn.close()
    new_m, new_ch = (folder, ch) if renames_module else (m, folder or ch)
    return {"state": "done", "edited": what, "git": state, "answers_moved": moved,
            "module": new_m, "chapter": new_ch}


def process(job_dir):
    with open(os.path.join(job_dir, "job.json"), encoding="utf-8") as f:
        job = json.load(f)
    write(os.path.join(job_dir, "status.json"), {"state": "processing"})
    if job.get("op") == "delete":
        return delete(job)
    if job.get("op") == "edit":
        return edit(job)
    m, ch, kind = job["module"], job["chapter"], job["kind"]
    add.sync()
    try:
        rel, replaced = add.place(m, ch, kind, os.path.join(job_dir, "file"), job["name"])
        add.set_meta(m, ch, job.get("title"), job.get("module_title"), job.get("module_code"), job.get("blurb"))
        _, warnings = add.build()
    except Exception:
        restore(m)
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
