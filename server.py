#!/usr/bin/env python3
"""Answers API for Study Hub. Python 3 stdlib only.

Env: ANSWERS_DB (default data/answers.db next to this file),
     ANSWERS_HOST (default 127.0.0.1), ANSWERS_PORT (default 8001).
"""
import json
import os
import re
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ANSWERS_DB", os.path.join(ROOT, "data", "answers.db"))
HOST = os.environ.get("ANSWERS_HOST", "127.0.0.1")
PORT = int(os.environ.get("ANSWERS_PORT", "8001"))

NAME_RE = re.compile(r"^[\w\-][\w.\-]{0,99}$")  # one path segment, no leading dot
MAX_BODY = 64 * 1024
MAX_VALUE = 20 * 1024
MAX_KEY = 200


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
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


ROUTES = {
    ("GET", "/api/health"): Handler.health,
    ("GET", "/api/answers"): Handler.get_answers,
    ("PUT", "/api/answers"): Handler.put_answer,
    ("DELETE", "/api/answers"): Handler.delete_page,
    ("GET", "/api/summary"): Handler.summary,
    ("GET", "/api/export"): Handler.export,
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
