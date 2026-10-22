#!/usr/bin/env python3
"""Build modules/ into dist/. Python 3 stdlib only.

modules/<module>/<chapter>/
    lesson.html, practice.html   remakes (any *.html; "practice" in the name = practice page)
    cours/                       the professor's course PDFs
    td/                          the professor's exercise sheets (TD)

Every page gets a "← <MODULE>" bar (plus links to the chapter's course PDFs);
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
REMAKE_TEMPLATE = os.path.join(ROOT, "remake_template.html")
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
# The theme toggle and the nav bar follow the viewport until the contents (.toc, else .hero) are scrolled
# past, then park where they are and scroll away with the page.
PARK_SCRIPT = (
    '(function(){var els=[document.getElementById("theme-toggle"),document.getElementById("studyhub-nav")]'
    '.filter(Boolean),orig=els.map(function(el){return el.style.cssText});'
    'function park(){var a=document.querySelector(".toc")||document.querySelector(".hero");'
    'if(!a)return;var stop=a.getBoundingClientRect().bottom+scrollY,past=scrollY>stop;els.forEach(function(el,i){'
    'var s=el.style;s.cssText=orig[i];if(!past)return;'
    'var top=el.getBoundingClientRect().top;s.setProperty("position","absolute","important");'
    's.setProperty("top",(stop+top)+"px","important");s.setProperty("bottom","auto","important");});}'
    'addEventListener("scroll",park,{passive:true});addEventListener("resize",park);park();})();'
)


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


BASE_RE = re.compile(r"/\* study-hub:base.*?/\* /study-hub:base \*/", re.S)
THEME_RE = re.compile(r"<script>/\* study-hub:theme \*/.*?</script>", re.S)
FIELD_RE = re.compile(r"<(input|select|textarea)\b[^>]*>", re.I)
NOT_SAVED = ("button", "submit", "reset", "hidden", "file", "password", "image")


def remake_base():
    try:
        with open(REMAKE_TEMPLATE, encoding="utf-8") as f:
            m = BASE_RE.search(f.read())
        return m.group(0) if m else None
    except OSError:
        return None


def lint_page(path, practice, base):
    """Warnings for a remake that breaks the shared template or the saving rules."""
    with open(path, encoding="utf-8", errors="replace") as f:
        s = f.read()
    out = []
    m = BASE_RE.search(s)
    if not m:
        out.append("missing the study-hub:base styles from remake_template.html")
    elif base and m.group(0) != base:
        out.append("study-hub:base styles differ from remake_template.html (copy them verbatim)")
    if not THEME_RE.search(s) or 'id="theme-toggle"' not in s:
        out.append("missing the shared theme script or the theme-toggle button")
    if "localStorage" in THEME_RE.sub("", s):
        out.append("uses localStorage (the site saves answers itself)")
    if practice:
        ids, missing, radios = [], 0, 0
        for tag in (t.group(0) for t in FIELD_RE.finditer(s)):
            t = re.search(r'\btype\s*=\s*["\']?(\w+)', tag, re.I)
            kind = t.group(1).lower() if t else ""
            if kind in NOT_SAVED or "data-no-save" in tag:
                continue
            if kind == "radio":
                if not re.search(r"\bname\s*=", tag) or not re.search(r"\bvalue\s*=", tag):
                    radios += 1
                continue
            i = re.search(r'\bid\s*=\s*["\']([^"\']+)', tag)
            if i:
                ids.append(i.group(1))
            else:
                missing += 1
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if missing:
            out.append(f"{missing} field(s) without an id (answers won't survive edits)")
        if radios:
            out.append(f"{radios} radio(s) without a name or value (restores the wrong option)")
        if dup:
            out.append(f"duplicate field ids: {', '.join(dup[:5])}")
    return out


def inject(src, dst, snippet):
    with open(src, "rb") as f:
        data = f.read()
    i = data.lower().rfind(b"</body>")
    data = data + snippet if i < 0 else data[:i] + snippet + data[i:]
    with open(dst, "wb") as f:
        f.write(data)


def nav_bar(module, chapter, depth):
    """Bottom-left bar: ← back to the module page, then one link per course PDF of the chapter."""
    e = html.escape
    up = "../" * depth
    links = [f'<a href="/{e(module["slug"])}/" style="{LINK_STYLE}">&larr; {e(module["code"])}</a>']
    cours = chapter["docs"]["cours"]
    for i, d in enumerate(cours, 1):
        text = "Cours PDF" if len(cours) == 1 else f"PDF {i}"
        links.append(f'<a href="{up}cours/{e(d["file"])}" target="_blank" rel="noopener" '
                     f'title="{e(d["label"])}" style="{LINK_STYLE}">{text}</a>')
    # on phones, lift the bar above the saver pill so they don't overlap
    css = "<style>@media (max-width:640px){#studyhub-nav{bottom:58px!important}}</style>"
    return (f'{css}<nav id="studyhub-nav" data-no-save aria-label="Study Hub" style="{BAR_STYLE}">{"".join(links)}</nav>'
            f'\n<script>{PARK_SCRIPT}</script>')


def build_module(module, out_root, base, warnings):
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
                practice = in_td or "practice" in f.lower()
                for w in lint_page(os.path.join(dirpath, f), practice, base):
                    warnings.append(f"modules/{module['slug']}/{page}: {w}")
                if practice:
                    snippet += (f'\n<script src="/assets/saver.js" data-module="{html.escape(module["slug"])}" '
                                f'data-page="{html.escape(page)}"></script>')
                inject(os.path.join(dirpath, f), os.path.join(dst, ch["slug"], rel),
                       (snippet + "\n").encode("utf-8"))


def resource(href, kind, label, tag, key=None, new_tab=False):
    e = html.escape
    attrs = f' data-key="{e(key)}"' if key else ""
    attrs += ' target="_blank" rel="noopener"' if new_tab else ""
    badge = '<span class="badge" hidden></span>' if key else ""
    return (f'<li><a class="res {kind}" href="{e(href)}"{attrs}><span class="ft">{e(tag)}</span>'
            f'<span>{e(label)}</span>{badge}</a></li>')


def render_chapter(module, ch, open_):
    e = html.escape
    base = f"/{module['slug']}/{ch['slug']}/"
    remakes = [
        resource(base + p["file"], p["kind"], p["kind"].capitalize(), "HTML",
                 key=f"{module['slug']}/{ch['slug']}/{p['file']}" if p["kind"] == "practice" else None)
        for p in ch["pages"]
    ]
    groups = [("Remakes", remakes)]
    for d, name in (("cours", "Cours"), ("td", "TD")):
        groups.append((name, [resource(f"{base}{d}/{x['file']}", "doc", x["label"], x["type"], new_tab=True)
                              for x in ch["docs"][d]]))
    body = "".join(
        f'<div class="group"><h3>{name}</h3><ul>{"".join(items) or "<li class=none>none yet</li>"}</ul></div>'
        for name, items in groups
    )
    title = f'<span class="ct">{e(ch["title"])}</span>' if ch["title"] else ""
    return (f'<details class="chapter" id="{e(ch["slug"])}"{" open" if open_ else ""}>'
            f'<summary><span class="cl">{e(ch["label"])}</span>{title}</summary>'
            f'<div class="groups">{body}</div></details>')


def render_card(module):
    e = html.escape
    blurb = f'<p class="blurb">{e(module["blurb"])}</p>' if module["blurb"] else ""
    return (f'<a class="card" href="/{e(module["slug"])}/"><span class="chip">{e(module["code"])}</span>'
            f'<h2>{e(module["title"] or module["code"])}</h2>{blurb}</a>')


def plural(n, word):
    return f'<span><b>{n}</b> {word}{"" if n == 1 else "s"}</span>'


SAVED_STAT = '<span><b id="saved-total">0</b> <span id="saved-word">answers</span> saved</span>'


def fill(tpl, **parts):
    for k, v in parts.items():
        tpl = tpl.replace(f"%%{k}%%", v)
    return tpl


def render_hub(tpl, modules):
    site = load_json(SITE_JSON)
    title = html.escape(str(site.get("title") or "Study Hub"))
    chapters = [c for m in modules for c in m["chapters"]]
    n_practice = sum(1 for c in chapters for p in c["pages"] if p["kind"] == "practice")
    n_docs = sum(len(c["docs"][d]) for c in chapters for d in DOC_DIRS)
    stats = (plural(len(modules), "module") + plural(len(chapters), "chapter")
             + plural(n_practice, "practice sheet") + plural(n_docs, "PDF") + SAVED_STAT)
    cards = "\n".join(render_card(m) for m in modules) or \
        '<p class="empty">No modules yet. Add <code>modules/&lt;module&gt;/&lt;chapter&gt;/</code> and rebuild.</p>'
    return fill(tpl, PAGETITLE=title, BACK="", EYEBROW="Master Big Data Analytics · USTHB", TITLE=title,
                SUB=html.escape(str(site.get("subtitle") or "Course remakes, practice sheets and the original PDFs")),
                STATS=stats, MAIN=f'<main class="grid">\n{cards}\n</main>')


def render_module_page(tpl, module):
    e = html.escape
    chs = module["chapters"]
    n_practice = sum(1 for c in chs for p in c["pages"] if p["kind"] == "practice")
    n_docs = sum(len(c["docs"][d]) for c in chs for d in DOC_DIRS)
    stats = plural(len(chs), "chapter") + plural(n_practice, "practice sheet") + plural(n_docs, "PDF") + SAVED_STAT
    chapters = "\n".join(render_chapter(module, c, open_=len(chs) == 1) for c in chs)
    page = fill(tpl, PAGETITLE=f'{e(module["code"])} · {e(module["title"] or module["code"])}',
                BACK='<a class="back" href="/">&larr; All modules</a>', EYEBROW=e(module["code"]),
                TITLE=e(module["title"] or module["code"]), SUB=e(module["blurb"]), STATS=stats,
                MAIN=f'<main class="chapters">\n{chapters}\n</main>')
    return page.replace("<body>", f'<body data-module="{e(module["slug"])}">', 1)


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
    base, warnings = remake_base(), []
    for m in modules:
        build_module(m, NEW, base, warnings)

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    with open(os.path.join(NEW, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_hub(tpl, modules))
    for m in modules:
        with open(os.path.join(NEW, m["slug"], "index.html"), "w", encoding="utf-8") as f:
            f.write(render_module_page(tpl, m))

    if os.path.exists(DIST):
        os.rename(DIST, OLD)
    os.rename(NEW, DIST)
    shutil.rmtree(OLD, ignore_errors=True)

    n_ch = sum(len(m["chapters"]) for m in modules)
    n_pages = sum(len(c["pages"]) for m in modules for c in m["chapters"])
    print(f"built {len(modules)} module(s), {n_ch} chapter(s), {n_pages} page(s) -> dist/")
    for w in warnings:
        warn(w)


if __name__ == "__main__":
    main()
