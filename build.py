#!/usr/bin/env python3
"""Build modules/ into dist/. Python 3 stdlib only.

modules/<module>/<chapter>/
    lesson.html, practice.html   remakes (any *.html; "practice" in the name = practice page)
    cours/                       the professor's course PDFs
    td/                          the professor's exercise sheets (TD)

Every page gets a "← Hub" bar (plus links to the chapter's course PDFs);
practice pages, and any HTML inside td/, also get the auto-save script.
Source files are never modified.
"""
import html
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(ROOT, "modules")
ASSETS = os.path.join(ROOT, "assets")
TEMPLATE = os.path.join(ROOT, "hub_template.html")
SITE_JSON = os.path.join(ROOT, "site.json")
DIST = os.path.join(ROOT, "dist")
NEW = os.path.join(ROOT, ".dist_new")
OLD = os.path.join(ROOT, ".dist_old")

NAME_RE = re.compile(r"^[\w\-][\w.\-]{0,99}$")
TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)
DOC_DIRS = ("cours", "td")
BAR_STYLE = (
    "position:fixed;left:14px;bottom:14px;z-index:2147483000;display:flex;gap:2px;"
    "padding:3px;border-radius:999px;background:#1f2937;box-shadow:0 2px 8px rgba(0,0,0,.25);opacity:.9;"
    "font:600 13px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif"
)
LINK_STYLE = "color:#fff;text-decoration:none;padding:5px 11px;border-radius:999px"


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def visible(name):
    return not name.startswith((".", "_"))


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


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def page_title(path, fallback):
    with open(path, "rb") as f:
        m = TITLE_RE.search(f.read())
    if m:
        t = re.sub(r"\s+", " ", html.unescape(m.group(1).decode("utf-8", "replace"))).strip()
        if t:
            return t
    return fallback


def doc_label(filename):
    """'1-concepts-fondamentaux.pdf' -> '1 · Concepts fondamentaux'."""
    stem, ext = os.path.splitext(filename)
    m = re.match(r"^(\d+)[-_ ]+(.*)$", stem)
    num, rest = (m.group(1), m.group(2)) if m else ("", stem)
    rest = re.sub(r"[-_]+", " ", rest).strip()
    rest = rest[:1].upper() + rest[1:]
    label = f"{num} · {rest}" if num and rest else (rest or num)
    return label, ext.lstrip(".").upper()


def chapter_label(slug):
    """'ch1' -> 'Chapter 1', 'ch1-2' -> 'Chapters 1–2'."""
    m = re.match(r"^ch(\d+)(?:-(\d+))?$", slug, re.I)
    if not m:
        return slug
    return f"Chapters {m.group(1)}–{m.group(2)}" if m.group(2) else f"Chapter {m.group(1)}"


def list_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted((f for f in os.listdir(folder)
                   if visible(f) and os.path.isfile(os.path.join(folder, f))), key=natural_key)


def load_chapter(mslug, cslug, titles):
    folder = os.path.join(MODULES, mslug, cslug)
    pages = []
    for f in list_files(folder):
        if f.lower().endswith(".html"):
            kind = "practice" if "practice" in f.lower() else "lesson"
            pages.append({"file": f, "kind": kind, "title": page_title(os.path.join(folder, f), f)})
    pages.sort(key=lambda p: p["kind"] == "practice")  # stable: lessons first
    docs = {d: [{"file": f, "label": doc_label(f)[0], "type": doc_label(f)[1]}
                for f in list_files(os.path.join(folder, d))] for d in DOC_DIRS}
    return {
        "slug": cslug,
        "label": chapter_label(cslug),
        "title": str(titles.get(cslug) or ""),
        "pages": pages,
        "docs": docs,
    }


def load_module(mslug):
    folder = os.path.join(MODULES, mslug)
    meta = load_json(os.path.join(folder, "module.json"))
    titles = meta.get("chapters") if isinstance(meta.get("chapters"), dict) else {}
    chapters = []
    for c in sorted(os.listdir(folder), key=natural_key):
        if not visible(c) or not os.path.isdir(os.path.join(folder, c)):
            continue
        if not NAME_RE.match(c):
            sys.exit(f"error: chapter folder name {mslug}/{c!r} is invalid")
        ch = load_chapter(mslug, c, titles)
        if ch["pages"] or any(ch["docs"].values()):
            chapters.append(ch)
    try:
        order = float(meta.get("order", 1000))
    except (TypeError, ValueError):
        order = 1000.0
    return {
        "slug": mslug,
        "code": str(meta.get("code") or mslug.upper()),
        "title": str(meta.get("title") or ""),
        "blurb": str(meta.get("blurb") or ""),
        "order": order,
        "chapters": chapters,
    }


def inject(src, dst, snippet):
    with open(src, "rb") as f:
        data = f.read()
    i = data.lower().rfind(b"</body>")
    data = data + snippet if i < 0 else data[:i] + snippet + data[i:]
    with open(dst, "wb") as f:
        f.write(data)


def nav_bar(module, chapter, depth):
    """Bottom-left bar: ← Hub, then one link per course PDF of the chapter."""
    e = html.escape
    up = "../" * depth
    links = [f'<a href="/#{e(module["slug"])}" style="{LINK_STYLE}">&larr; Hub</a>']
    cours = chapter["docs"]["cours"]
    for i, d in enumerate(cours, 1):
        text = "Cours PDF" if len(cours) == 1 else f"PDF {i}"
        links.append(f'<a href="{up}cours/{e(d["file"])}" target="_blank" rel="noopener" '
                     f'title="{e(d["label"])}" style="{LINK_STYLE}">{text}</a>')
    # on phones, lift the bar above the saver pill so they don't overlap
    css = "<style>@media (max-width:640px){#studyhub-nav{bottom:58px!important}}</style>"
    return f'{css}<nav id="studyhub-nav" data-no-save aria-label="Study Hub" style="{BAR_STYLE}">{"".join(links)}</nav>'


def build_module(module, out_root):
    src = os.path.join(MODULES, module["slug"])
    dst = os.path.join(out_root, module["slug"])
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("module.json", ".*", "_*"))
    for ch in module["chapters"]:
        cdir = os.path.join(src, ch["slug"])
        for dirpath, dirnames, filenames in os.walk(cdir):
            dirnames[:] = [d for d in dirnames if visible(d)]
            rel_dir = os.path.relpath(dirpath, cdir)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            in_td = rel_dir.split(os.sep)[0] == "td"
            for f in filenames:
                if not f.lower().endswith(".html") or not visible(f):
                    continue
                rel = f if depth == 0 else os.path.join(rel_dir, f).replace(os.sep, "/")
                page = f"{ch['slug']}/{rel}"
                snippet = "\n" + nav_bar(module, ch, depth)
                if in_td or "practice" in f.lower():
                    snippet += (f'\n<script src="/assets/saver.js" data-module="{html.escape(module["slug"])}" '
                                f'data-page="{html.escape(page)}"></script>')
                inject(os.path.join(dirpath, f), os.path.join(dst, ch["slug"], rel),
                       (snippet + "\n").encode("utf-8"))


def render_chapter(module, ch):
    e = html.escape
    base = f"/{module['slug']}/{ch['slug']}/"
    links = []
    for p in ch["pages"]:
        if p["kind"] == "practice":
            key = f"{module['slug']}/{ch['slug']}/{p['file']}"
            links.append(f'<a class="pg practice" href="{e(base + p["file"])}" data-key="{e(key)}" title="{e(p["title"])}">'
                         f'Practice<span class="badge" hidden></span></a>')
        else:
            links.append(f'<a class="pg lesson" href="{e(base + p["file"])}" title="{e(p["title"])}">Lesson</a>')
    groups = []
    for d, name in (("cours", "Cours"), ("td", "TD")):
        items = "".join(
            f'<a class="doc" href="{e(base + d + "/" + x["file"])}" target="_blank" rel="noopener">'
            f'<span class="ft">{e(x["type"])}</span>{e(x["label"])}</a>'
            for x in ch["docs"][d]
        ) or '<span class="none">none yet</span>'
        groups.append(f'<div class="docs"><span class="dk">{name}</span>{items}</div>')
    title = f' <span class="ct">{e(ch["title"])}</span>' if ch["title"] else ""
    return (f'<li class="chapter"><div class="ch-h"><span class="cl">{e(ch["label"])}</span>{title}</div>'
            f'<div class="pgs">{"".join(links) or "<span class=none>no remake yet</span>"}</div>{"".join(groups)}</li>')


def render_card(module):
    e = html.escape
    title = module["title"] or module["code"]
    blurb = f'<p class="blurb">{e(module["blurb"])}</p>' if module["blurb"] else ""
    chapters = "".join(render_chapter(module, c) for c in module["chapters"])
    return (f'<article class="card" id="{e(module["slug"])}">\n'
            f'  <div class="card-head"><span class="chip">{e(module["code"])}</span><h2>{e(title)}</h2></div>\n'
            f'  {blurb}\n  <ol class="chapters">{chapters}</ol>\n</article>')


def plural(n, word):
    return f'<span><b>{n}</b> {word}{"" if n == 1 else "s"}</span>'


def render_hub(modules):
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    site = load_json(SITE_JSON)
    chapters = [c for m in modules for c in m["chapters"]]
    n_practice = sum(1 for c in chapters for p in c["pages"] if p["kind"] == "practice")
    n_docs = sum(len(c["docs"][d]) for c in chapters for d in DOC_DIRS)
    stats = (plural(len(modules), "module") + plural(len(chapters), "chapter")
             + plural(n_practice, "practice sheet") + plural(n_docs, "PDF")
             + '<span><b id="saved-total">0</b> <span id="saved-word">answers</span> saved</span>')
    cards = "\n".join(render_card(m) for m in modules) or \
        '<p class="empty">No modules yet. Add <code>modules/&lt;module&gt;/&lt;chapter&gt;/</code> and rebuild.</p>'
    return (tpl.replace("%%TITLE%%", html.escape(str(site.get("title") or "Study Hub")))
            .replace("%%SUB%%", html.escape(str(site.get("subtitle") or "Course remakes, practice sheets and the original PDFs")))
            .replace("%%STATS%%", stats)
            .replace("%%CARDS%%", cards))


def main():
    for d in (NEW, OLD):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(NEW)
    if os.path.isdir(ASSETS):
        shutil.copytree(ASSETS, os.path.join(NEW, "assets"))

    slugs = []
    if os.path.isdir(MODULES):
        slugs = [d for d in os.listdir(MODULES) if visible(d) and os.path.isdir(os.path.join(MODULES, d))]
    for s in slugs:
        if s == "assets" or not NAME_RE.match(s):
            sys.exit(f"error: module folder name {s!r} is reserved or invalid")

    modules = [m for m in (load_module(s) for s in slugs) if m["chapters"]]  # empty modules stay hidden
    modules.sort(key=lambda m: (m["order"], m["code"].lower()))
    for m in modules:
        build_module(m, NEW)

    with open(os.path.join(NEW, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_hub(modules))

    if os.path.exists(DIST):
        os.rename(DIST, OLD)
    os.rename(NEW, DIST)
    shutil.rmtree(OLD, ignore_errors=True)

    n_ch = sum(len(m["chapters"]) for m in modules)
    n_pages = sum(len(c["pages"]) for m in modules for c in m["chapters"])
    print(f"built {len(modules)} module(s), {n_ch} chapter(s), {n_pages} page(s) -> dist/")


if __name__ == "__main__":
    main()
