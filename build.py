#!/usr/bin/env python3
"""Build courses/ into dist/. Python 3 stdlib only.

Each folder in courses/ (not starting with . or _) is a course. Pages get a
"← Hub" link injected; practice pages also get the auto-save script. Source
files are never modified.
"""
import html
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COURSES = os.path.join(ROOT, "courses")
ASSETS = os.path.join(ROOT, "assets")
TEMPLATE = os.path.join(ROOT, "hub_template.html")
SITE_JSON = os.path.join(ROOT, "site.json")
DIST = os.path.join(ROOT, "dist")
NEW = os.path.join(ROOT, ".dist_new")
OLD = os.path.join(ROOT, ".dist_old")

TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)

HUB_LINK = (
    '<a href="/" id="studyhub-home" data-no-save style="position:fixed;left:14px;bottom:14px;'
    "z-index:2147483000;padding:7px 13px;border-radius:999px;background:#1f2937;color:#fff;"
    "font:600 13px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif;text-decoration:none;"
    'box-shadow:0 2px 8px rgba(0,0,0,.25);opacity:.85">&larr; Hub</a>'
)


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        warn(f"ignoring {os.path.relpath(path, ROOT)}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def page_title(path, fallback):
    with open(path, "rb") as f:
        m = TITLE_RE.search(f.read())
    if m:
        t = re.sub(r"\s+", " ", html.unescape(m.group(1).decode("utf-8", "replace"))).strip()
        if t:
            return t
    return fallback


def default_kind(filename):
    return "practice" if "practice" in filename.lower() else "lesson"


def load_course(slug):
    folder = os.path.join(COURSES, slug)
    meta = load_json(os.path.join(folder, "course.json"))
    html_files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".html"))

    pages = []
    if isinstance(meta.get("pages"), list):
        for p in meta["pages"]:
            if not isinstance(p, dict) or p.get("file") not in html_files:
                warn(f"{slug}/course.json: skipping page entry {p!r} (file not found)")
                continue
            f = p["file"]
            pages.append({
                "file": f,
                "title": p.get("title") or page_title(os.path.join(folder, f), f),
                "kind": p.get("kind") if p.get("kind") in ("lesson", "practice") else default_kind(f),
            })
    else:
        for f in html_files:
            pages.append({
                "file": f,
                "title": page_title(os.path.join(folder, f), f),
                "kind": default_kind(f),
            })
        pages.sort(key=lambda p: p["kind"] == "practice")  # stable: lessons first

    try:
        order = float(meta.get("order", 1000))
    except (TypeError, ValueError):
        order = 1000.0
    return {
        "slug": slug,
        "code": str(meta.get("code") or slug.upper()),
        "title": str(meta.get("title") or ""),
        "blurb": str(meta.get("blurb") or ""),
        "order": order,
        "pages": pages,
        "html_files": html_files,
    }


def inject(src, dst, snippet):
    with open(src, "rb") as f:
        data = f.read()
    i = data.lower().rfind(b"</body>")
    data = data + snippet if i < 0 else data[:i] + snippet + data[i:]
    with open(dst, "wb") as f:
        f.write(data)


def build_course(course, out_root):
    slug = course["slug"]
    src = os.path.join(COURSES, slug)
    dst = os.path.join(out_root, slug)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("course.json", ".*", "_*"))
    kinds = {p["file"]: p["kind"] for p in course["pages"]}
    for f in course["html_files"]:
        snippet = "\n" + HUB_LINK
        if kinds.get(f, default_kind(f)) == "practice":
            snippet += (
                f'\n<script src="/assets/saver.js" data-course="{html.escape(slug)}" '
                f'data-page="{html.escape(f)}"></script>'
            )
        inject(os.path.join(src, f), os.path.join(dst, f), (snippet + "\n").encode("utf-8"))


def render_card(course):
    e = html.escape
    links = []
    for p in course["pages"]:
        href = f"/{course['slug']}/{p['file']}"
        if p["kind"] == "practice":
            key = f"{course['slug']}/{p['file']}"
            links.append(
                f'<a class="page practice" href="{e(href)}" data-key="{e(key)}">'
                f'<span class="kind">Practice</span><span class="pt">{e(p["title"])}</span>'
                f'<span class="badge" hidden></span></a>'
            )
        else:
            links.append(
                f'<a class="page lesson" href="{e(href)}">'
                f'<span class="kind">Lesson</span><span class="pt">{e(p["title"])}</span></a>'
            )
    title = course["title"] or (course["pages"][0]["title"] if course["pages"] else course["code"])
    blurb = f'<p class="blurb">{e(course["blurb"])}</p>' if course["blurb"] else ""
    return (
        f'<article class="card">\n'
        f'  <div class="card-head"><span class="chip">{e(course["code"])}</span>'
        f'<h2>{e(title)}</h2></div>\n'
        f'  {blurb}\n'
        f'  <nav class="pages">{"".join(links) or "<em>No pages yet</em>"}</nav>\n'
        f'</article>'
    )


def render_hub(courses):
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    site = load_json(SITE_JSON)
    n_pages = sum(len(c["pages"]) for c in courses)
    n_practice = sum(1 for c in courses for p in c["pages"] if p["kind"] == "practice")
    stats = (
        f'<span><b>{len(courses)}</b> course{"s" if len(courses) != 1 else ""}</span>'
        f'<span><b>{n_pages - n_practice}</b> lesson{"s" if n_pages - n_practice != 1 else ""}</span>'
        f'<span><b>{n_practice}</b> practice sheet{"s" if n_practice != 1 else ""}</span>'
        f'<span><b id="saved-total">0</b> <span id="saved-word">answers</span> saved</span>'
    )
    cards = "\n".join(render_card(c) for c in courses) or '<p class="empty">No courses yet. Drop a folder into <code>courses/</code> and rebuild.</p>'
    return (
        tpl.replace("%%TITLE%%", html.escape(str(site.get("title") or "Study Hub")))
        .replace("%%SUB%%", html.escape(str(site.get("subtitle") or "Course remakes and practice sheets")))
        .replace("%%STATS%%", stats)
        .replace("%%CARDS%%", cards)
    )


def main():
    for d in (NEW, OLD):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(NEW)

    if os.path.isdir(ASSETS):
        shutil.copytree(ASSETS, os.path.join(NEW, "assets"))

    slugs = []
    if os.path.isdir(COURSES):
        slugs = sorted(
            d for d in os.listdir(COURSES)
            if not d.startswith((".", "_")) and os.path.isdir(os.path.join(COURSES, d))
        )
    for s in slugs:
        if s == "assets" or not re.match(r"^[\w.\-]{1,100}$", s):
            sys.exit(f"error: course folder name {s!r} is reserved or invalid")

    courses = [load_course(s) for s in slugs]
    courses.sort(key=lambda c: (c["order"], c["code"].lower()))
    for c in courses:
        build_course(c, NEW)

    with open(os.path.join(NEW, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_hub(courses))

    # swap: dist -> .dist_old, .dist_new -> dist
    if os.path.exists(DIST):
        os.rename(DIST, OLD)
    os.rename(NEW, DIST)
    shutil.rmtree(OLD, ignore_errors=True)

    n = sum(len(c["html_files"]) for c in courses)
    print(f"built {len(courses)} course(s), {n} page(s) -> dist/")


if __name__ == "__main__":
    main()
