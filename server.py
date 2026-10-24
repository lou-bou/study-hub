#!/usr/bin/env python3
"""Answers API for Study Hub. Python 3 stdlib only.

Env: ANSWERS_DB (default data/answers.db next to this file),
     ANSWERS_HOST (default 127.0.0.1), ANSWERS_PORT (default 8001).

Uploads (PUT /api/upload) are only validated and queued in data/inbox/; deploy/ingest.py,
outside this service's sandbox, places them in modules/, builds, commits and pushes.
"""
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import add

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ANSWERS_DB", os.path.join(ROOT, "data", "answers.db"))
HOST = os.environ.get("ANSWERS_HOST", "127.0.0.1")
PORT = int(os.environ.get("ANSWERS_PORT", "8001"))

NAME_RE = re.compile(r"^[\w\-][\w.\-]{0,99}$")  # one path segment, no leading dot
MAX_BODY = 64 * 1024
MAX_VALUE = 20 * 1024
MAX_KEY = 200

DATA = os.path.dirname(os.path.abspath(DB_PATH))
INBOX = os.path.join(DATA, "inbox")          # complete jobs, picked up by deploy/ingest.py
INBOX_TMP = os.path.join(DATA, "inbox-tmp")  # jobs still being received
DONE = os.path.join(DATA, "uploads")         # processed jobs with their result.json
MAX_UPLOAD = {"lesson": 5 << 20, "practice": 5 << 20, "cours": 50 << 20, "td": 50 << 20}
JOB_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    for d in (DATA, INBOX, INBOX_TMP, DONE):
        os.makedirs(d, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS answers(
                module TEXT NOT NULL,
                page TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(module, page, key))"""
        )


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def check_name(value, field):
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ApiError(400, f"invalid {field}")
    return value


def check_page(value):
    """A page is a path inside the module, e.g. ch1/practice.html or ch1/td/td1.html."""
    if not isinstance(value, str) or len(value) > 200:
        raise ApiError(400, "invalid page")
    parts = value.split("/")
    if not 1 <= len(parts) <= 4 or not all(NAME_RE.match(p) for p in parts):
        raise ApiError(400, "invalid page")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "StudyHubAPI/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass  # quiet: errors are reported via log_error

    def log_error(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self, method):
        try:
            url = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            route = ROUTES.get((method, url.path.rstrip("/")))
            if route is None:
                known = any(path == url.path.rstrip("/") for _, path in ROUTES)
                raise ApiError(405 if known else 404, "method not allowed" if known else "not found")
            self.send_json(200, route(self, query))
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception as e:  # noqa: BLE001
            self.log_error("internal error: %r", e)
            self.send_json(500, {"error": "internal error"})

    def do_GET(self):
        self.dispatch("GET")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def do_POST(self):
        self.dispatch("POST")

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad content-length")
        if length > MAX_BODY:
            raise ApiError(413, "body too large")
        try:
            data = json.loads(self.rfile.read(length) or b"null")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid json")
        if not isinstance(data, dict):
            raise ApiError(400, "expected a json object")
        return data

    def read_upload(self, path, limit):
        """Stream the raw request body to path."""
        try:
            length = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            length = -1
        if length < 1:
            raise ApiError(411, "empty upload or missing content-length")
        if length > limit:
            raise ApiError(413, f"file too large (max {limit >> 20} MB)")
        with open(path, "wb") as f:
            left = length
            while left:
                chunk = self.rfile.read(min(left, 1 << 16))
                if not chunk:
                    raise ApiError(400, "upload cut short")
                f.write(chunk)
                left -= len(chunk)

    # --- routes -------------------------------------------------------

    def health(self, q):
        with connect() as conn:
            conn.execute("SELECT 1")
        return {"ok": True}

    def get_answers(self, q):
        module = check_name(q.get("module"), "module")
        page = check_page(q.get("page"))
        with connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM answers WHERE module=? AND page=?", (module, page)
            ).fetchall()
        return dict(rows)

    def put_answer(self, q):
        data = self.read_json()
        module = check_name(data.get("module"), "module")
        page = check_page(data.get("page"))
        key = data.get("key")
        value = data.get("value")
        if not isinstance(key, str) or not 1 <= len(key) <= MAX_KEY:
            raise ApiError(400, "invalid key")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ApiError(400, "value must be a string")
        if len(value) > MAX_VALUE:
            raise ApiError(413, "value too large")
        with connect() as conn:
            if value == "":
                conn.execute(
                    "DELETE FROM answers WHERE module=? AND page=? AND key=?", (module, page, key)
                )
                return {"ok": True, "deleted": True}
            conn.execute(
                """INSERT INTO answers(module, page, key, value, updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(module, page, key)
                   DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (module, page, key, value, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )
        return {"ok": True}

    def delete_page(self, q):
        module = check_name(q.get("module"), "module")
        page = check_page(q.get("page"))
        with connect() as conn:
            n = conn.execute(
                "DELETE FROM answers WHERE module=? AND page=?", (module, page)
            ).rowcount
        return {"ok": True, "deleted": n}

    def summary(self, q):
        with connect() as conn:
            rows = conn.execute(
                "SELECT module, page, COUNT(*) FROM answers GROUP BY module, page"
            ).fetchall()
        return {f"{c}/{p}": n for c, p, n in rows}

    def export(self, q):
        with connect() as conn:
            rows = conn.execute(
                "SELECT module, page, key, value, updated_at FROM answers ORDER BY module, page, key"
            ).fetchall()
        return [
            {"module": c, "page": p, "key": k, "value": v, "updated_at": u}
            for c, p, k, v, u in rows
        ]


    def upload(self, q):
        kind = q.get("kind")
        if kind not in MAX_UPLOAD:
            raise ApiError(400, "kind must be lesson, practice, cours or td")
        try:
            module = add.check_module(q.get("module"))
            chapter = add.check_slug(q.get("chapter"), "chapter")
        except add.AddError as e:
            raise ApiError(400, str(e))
        name = os.path.basename(q.get("name") or "")
        ext = ".html" if kind in ("lesson", "practice") else ".pdf"
        if not name.lower().endswith(ext) or len(name) > 200:
            raise ApiError(400, f"a {kind} upload must be a {ext} file")
        meta = {k: q[k].strip()[:300] for k in ("title", "module_title", "module_code", "blurb") if q.get(k, "").strip()}

        job = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        tmp = os.path.join(INBOX_TMP, job)
        os.makedirs(tmp)
        try:
            self.read_upload(os.path.join(tmp, "file"), MAX_UPLOAD[kind])
            with open(os.path.join(tmp, "file"), "rb") as f:
                head = f.read(4096)
            if ext == ".pdf" and not head.startswith(b"%PDF-"):
                raise ApiError(400, f"{name} is not a PDF")
            if ext == ".html" and b"<html" not in head.lower() and b"<!doctype html" not in head.lower():
                raise ApiError(400, f"{name} doesn't look like an HTML page")
            with open(os.path.join(tmp, "job.json"), "w", encoding="utf-8") as f:
                json.dump({"module": module, "chapter": chapter, "kind": kind, "name": name, **meta}, f)
            os.rename(tmp, os.path.join(INBOX, job))  # appears in the inbox only once complete
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return {"ok": True, "id": job}

    def manage(self, q):
        """Queue an edit (module code/title/blurb, chapter title) or a delete (module, chapter or
        one file); deploy/ingest.py carries it out."""
        data = self.read_json()
        if data.get("action") == "edit":
            try:
                fields = add.check_edit(data.get("module"), data.get("chapter"),
                                        data.get("code"), data.get("title"), data.get("blurb"))
            except add.AddError as e:
                raise ApiError(400, str(e))
            job = {"op": "edit", "module": data["module"], "chapter": data.get("chapter"),
                   **{k: v for k, v in fields.items() if v is not None}}
            return {"ok": True, "id": self.queue(job)}
        if data.get("action") != "delete":
            raise ApiError(400, "action must be edit or delete")
        job = {"op": "delete"}
        try:
            job["module"] = add.check_module(data.get("module"))
            if data.get("chapter") is not None:
                job["chapter"] = add.check_slug(data.get("chapter"), "chapter")
                if data.get("path") is not None:
                    job["path"] = add.check_file(data.get("path"))
            elif data.get("path") is not None:
                raise add.AddError("a file needs its chapter")
        except add.AddError as e:
            raise ApiError(400, str(e))
        target = os.path.join(add.MODULES, job["module"], job.get("chapter", ""), job.get("path", ""))
        if not os.path.exists(target):
            raise ApiError(404, "nothing to delete there")
        return {"ok": True, "id": self.queue(job)}

    def queue(self, job):
        """Drop a job with no file into the inbox (complete before it appears)."""
        jid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        tmp = os.path.join(INBOX_TMP, jid)
        os.makedirs(tmp)
        with open(os.path.join(tmp, "job.json"), "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
        os.rename(tmp, os.path.join(INBOX, jid))
        return jid

    def upload_status(self, q):
        job = q.get("id") or ""
        if not JOB_RE.match(job):
            raise ApiError(400, "invalid id")
        for d in (DONE, INBOX):
            for name in ("result.json", "status.json"):
                try:
                    with open(os.path.join(d, job, name), encoding="utf-8") as f:
                        return json.load(f)
                except (OSError, ValueError):
                    pass
            if os.path.isdir(os.path.join(d, job)):
                return {"state": "queued"}
        raise ApiError(404, "unknown upload")


ROUTES = {
    ("GET", "/api/health"): Handler.health,
    ("GET", "/api/answers"): Handler.get_answers,
    ("PUT", "/api/answers"): Handler.put_answer,
    ("DELETE", "/api/answers"): Handler.delete_page,
    ("GET", "/api/summary"): Handler.summary,
    ("GET", "/api/export"): Handler.export,
    ("PUT", "/api/upload"): Handler.upload,
    ("GET", "/api/upload"): Handler.upload_status,
    ("POST", "/api/manage"): Handler.manage,
}


def main():
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"answers API on http://{HOST}:{PORT} (db: {DB_PATH})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
