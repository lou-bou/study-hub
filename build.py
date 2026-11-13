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
import base64
import functools
import hashlib
import html
import json
import os
import re
import shutil
import sys
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(ROOT, "modules")
ASSETS = os.path.join(ROOT, "assets")
TEMPLATE = os.path.join(ROOT, "hub_template.html")
REMAKE_TEMPLATE = os.path.join(ROOT, "remake_template.html")
SITE_JSON = os.path.join(ROOT, "site.json")
SW_TEMPLATE = os.path.join(ROOT, "sw_template.js")
DIST = os.path.join(ROOT, "dist")
NEW = os.path.join(ROOT, ".dist_new")
OLD = os.path.join(ROOT, ".dist_old")

NAME_RE = re.compile(r"^[\w\-][\w.\-]{0,99}$")
TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)
DOC_DIRS = ("cours", "td")
# Lucide icons (ISC licence), inlined at 1.75 stroke.
ICONS = {
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "house": '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "sun-moon": '<path d="M12 8a2.83 2.83 0 0 0 4 4 4 4 0 1 1-4-4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.3 17.7-1.4 1.4"/><path d="m19.1 4.9-1.4 1.4"/>',
    "folder-cog": '<circle cx="18" cy="18" r="3"/><path d="M10.3 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v3.3"/><path d="m21.7 19.4-.9-.3"/><path d="m15.2 16.9-.9-.3"/><path d="m16.6 21.7.3-.9"/><path d="m19.1 15.2.3-.9"/><path d="m19.6 21.7-.4-1"/><path d="m16.8 15.3-.4-1"/><path d="m14.3 19.6 1-.4"/><path d="m20.7 16.8 1-.4"/>',
    "search": '<path d="m21 21-4.3-4.3"/><circle cx="11" cy="11" r="8"/>',
    "circle": '<circle cx="12" cy="12" r="9"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "download": '<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>',
    "panel-left": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
}


def icon(name, cls="i"):
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


# Back button on every remake: the theme toggle's look, mirrored to the top-left corner.
BACK_STYLE = (
    "position:fixed;top:14px;left:max(14px,env(safe-area-inset-left,0px));z-index:20;display:inline-flex;"
    "align-items:center;justify-content:center;width:40px;height:40px;border:1px solid var(--border);"
    "background:var(--surface);color:var(--text);border-radius:var(--radius-md);text-decoration:none;cursor:pointer"
)
OLD_FONTS_RE = re.compile(r'<link rel="(?:stylesheet|preconnect)" href="https://fonts\.(?:googleapis|gstatic)\.com[^>]*>\s*')
TOGGLE_RE = re.compile(r'(<button[^>]*id="theme-toggle"[^>]*>).*?(</button>)', re.S)
TOKENS_RE = re.compile(r"/\* tokens:.*?/\* /tokens \*/\n?", re.S)
# Pages render bigger on wide screens, like a browser zoom of 125% / 150%; phones are unchanged.
ZOOM_STYLE = ("<style>@media (min-width:1200px){html{zoom:1.25}}"
              "@media (min-width:1500px){html{zoom:1.5}}</style>\n")
PHONE = "(max-width:700px)"
# Remakes on phones. Page styles come first in the cascade, so these win; inline styles need !important.
REMAKE_MOBILE = ("<style>@media " + PHONE + "{"
    ".toggle,#studyhub-nav{width:44px!important;height:44px!important}"
    "#studyhub-nav{transition:transform .2s}"
    ".part a,.prob summary,details.more summary,.b,label.opt,.done{min-height:44px}"
    ".prob summary{display:flex}"
    ".part a,label.opt{align-items:center}"
    "details.more summary{display:flex;align-items:center;width:auto}"
    "label.opt input{margin-top:0}"
    ".done input{width:24px;height:24px}"
    ".sec-h .back{padding:12px 0 12px 12px}"
    "label.chipbox{display:inline-flex;align-items:center;min-height:40px}"
    "input:not([type=radio]):not([type=checkbox]),select,textarea{font-size:16px!important}"
    "input:not([type=radio]):not([type=checkbox]),select{min-height:44px}"
    ".toc-m{margin-top:8px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md)}"
    ".toc-m>summary{display:flex;align-items:center;min-height:48px;padding:0 16px;font-weight:600;cursor:pointer}"
    ".toc-m>.toc{border-top:1px solid var(--border);padding:14px 16px}"
    "[data-more]{-webkit-mask-image:linear-gradient(to right,#000 calc(100% - 28px),transparent);"
    "mask-image:linear-gradient(to right,#000 calc(100% - 28px),transparent)}"
    "#studyhub-saver{right:10px!important;bottom:10px!important;font-size:12px!important}"
    "#studyhub-saver[data-state=ready] span{display:none}"
    "#studyhub-saver button{padding:9px 12px!important;min-height:40px}"
    "}</style>\n")
# Remakes on desktop: the sidebar replaces the floating back and theme buttons, and pushes the page aside.
# Collapsed, the page keeps clear of the one button left. Remakes always open collapsed (shared.js reads the flag).
REMAKE_FLAG = '<script>document.documentElement.setAttribute("data-remake","");</script>\n'
REMAKE_DESKTOP = ("<style>@media screen and (min-width:701px){"
    "#studyhub-nav,#theme-toggle{display:none!important}"
    "html:not([data-side=closed]) body{margin-left:16rem}"
    "html[data-side=closed] body{padding-inline:62px}"
    "}</style>\n")
# The theme toggle and the nav bar follow the viewport until they reach the end of the contents
# (.toc, else .hero), then each parks just below that line and scrolls away with the page.
PARK_SCRIPT = (
    '(function(){var q=function(c){return document.querySelector(c);},nav=document.getElementById("studyhub-nav"),'
    'els=[document.getElementById("theme-toggle"),document.getElementById("studyhub-dl"),nav].filter(Boolean),orig=els.map(function(el){return el.style.cssText}),'
    'phone=matchMedia("' + PHONE + '"),last=scrollY,hidden=false;'
    # phones: the contents collapse into a dropdown that closes when a link is tapped
    'var toc=q(".toc");if(toc&&phone.matches){var d=document.createElement("details");d.className="toc-m";'
    'd.innerHTML="<summary>Contents</summary>";toc.parentNode.insertBefore(d,toc);d.appendChild(toc);'
    'toc.addEventListener("click",function(e){if(e.target.closest("a"))d.open=false;});}'
    'function park(){var a=q(".toc-m")||q(".toc")||q(".hero");'
    'if(!a)return;var line=a.getBoundingClientRect().bottom+scrollY;els.forEach(function(el,i){'
    'var s=el.style;s.cssText=orig[i];'
    # phones: an installed app has no back button, so ← hides on the way down and returns on the way up
    'if(el===nav&&phone.matches){if(scrollY<=line||scrollY<last)hidden=false;else if(scrollY>last)hidden=true;'
    's.transform=hidden?"translateY(-90px)":"";return;}'
    'var r=el.getBoundingClientRect();if(!r.height)return;'
    # rects are in screen px, `top` in the page's px (divided by the html zoom); park 10px below the line
    'var k=1/(parseFloat(getComputedStyle(document.documentElement).zoom)||1);'
    'if(scrollY+r.top<line+10/k)return;s.setProperty("position","absolute","important");'
    's.setProperty("top",line*k+10+"px","important");s.setProperty("bottom","auto","important");});last=scrollY;}'
    # phones: fade the edge of anything that scrolls sideways, until its end is reached
    'function fades(){if(!phone.matches)return;document.querySelectorAll(".scroll,figure.fig,.herofig,.eq,pre.algo")'
    '.forEach(function(e){e.toggleAttribute("data-more",e.scrollWidth-e.clientWidth-e.scrollLeft>2);});}'
    'document.addEventListener("scroll",fades,{passive:true,capture:true});addEventListener("load",fades);'
    'addEventListener("resize",fades);fades();'
    'addEventListener("scroll",park,{passive:true});addEventListener("resize",park);park();})();'
)


@functools.lru_cache(maxsize=None)
def asset(rel):
    """An asset's URL, versioned by its contents. Cloudflare and browsers may keep /assets/* for hours,
    so a page must never ask for a changed file under the URL it had before."""
    with open(os.path.join(ASSETS, rel), "rb") as f:
        return f"/assets/{rel}?v={hashlib.sha256(f.read()).hexdigest()[:10]}"


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


def count_problems(path):
    """Problem cards on a practice sheet, shown until the sheet reports its own "N / M"."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return len(re.findall(r'class="prob[ "]', f.read()))


def load_chapter(mslug, cslug, titles):
    folder = os.path.join(MODULES, mslug, cslug)
    pages = []
    for f in list_files(folder):
        if f.lower().endswith(".html"):
            kind = "practice" if "practice" in f.lower() else "lesson"
            pages.append({"file": f, "kind": kind, "title": page_title(os.path.join(folder, f), f),
                          "total": count_problems(os.path.join(folder, f)) if kind == "practice" else 0})
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


def remake_theme():
    try:
        with open(REMAKE_TEMPLATE, encoding="utf-8") as f:
            m = THEME_RE.search(f.read())
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


def head_tags():
    """Tags every generated page gets. Tokens and fonts are real files so they work offline. The manifest
    needs credentials: Cloudflare Access guards it too."""
    name = html.escape(site_title())
    return (f'<link rel="stylesheet" href="{asset("tokens.css")}">\n<link rel="stylesheet" href="{asset("fonts.css")}">\n'
            f'<link rel="stylesheet" href="{asset("sidebar.css")}">\n'
            + ZOOM_STYLE +
            '<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">\n'
            '<link rel="icon" href="/assets/icons/favicon.svg" type="image/svg+xml">\n'
            '<link rel="icon" href="/assets/icons/favicon-32.png" sizes="32x32" type="image/png">\n'
            '<link rel="apple-touch-icon" href="/assets/icons/apple-touch-icon.png">\n'
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#F7F1E6">\n'
            '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#1E2A44">\n'
            '<meta name="mobile-web-app-capable" content="yes">\n'
            '<meta name="apple-mobile-web-app-capable" content="yes">\n'
            f'<meta name="apple-mobile-web-app-title" content="{name}">\n'
            f'<script src="{asset("shared.js")}"></script>\n'
            '<script>if("serviceWorker"in navigator)addEventListener("load",function(){'
            'navigator.serviceWorker.register("/sw.js");});</script>\n')


def site_title():
    return str(load_json(SITE_JSON).get("title") or "Cahier")


def write_pwa(out_root):
    """manifest.json and sw.js. The version hashes everything precached, so any change updates the app."""
    name = site_title()
    with open(os.path.join(out_root, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump({
            "name": name, "short_name": name, "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": "#F7F1E6", "theme_color": "#1E2A44",
            "icons": [
                {"src": "/assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "/assets/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }, f, ensure_ascii=False, indent=2)
    files = []
    for dirpath, dirnames, filenames in os.walk(out_root):
        rel = os.path.relpath(dirpath, out_root).replace(os.sep, "/")
        dirnames[:] = [d for d in dirnames if not (rel == "." and d == "upload") and d != "_download"]
        for fn in filenames:
            if fn.endswith((".html", ".js", ".mjs", ".css", ".woff2", ".svg", ".json", ".webmanifest", ".png")) and fn != "sw.js":
                files.append("/" + (fn if rel == "." else f"{rel}/{fn}"))
    files.sort()
    with open(SW_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    digest = hashlib.sha256(tpl.encode("utf-8"))
    for url in files:
        digest.update(url.encode("utf-8"))
        with open(os.path.join(out_root, url.lstrip("/")), "rb") as f:
            digest.update(f.read())
    urls = ["/" if u == "/index.html" else (u[:-10] if u.endswith("/index.html") else u) for u in files]
    # versioned, so installing can't store a stale copy from Cloudflare; the worker keys its cache by path
    urls = [asset(u[len("/assets/"):]) if u.startswith("/assets/") else u for u in urls]
    with open(os.path.join(out_root, "sw.js"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("%%VERSION%%", digest.hexdigest()[:12]).replace("%%PRECACHE%%", json.dumps(urls)))


def normalize(text, base, theme):
    """The look comes from the current template, whichever version a page was uploaded with. Amber means
    "my place" only, so older figures drawn in the accent move to the figure colour first."""
    text = text.replace("var(--accent)", "var(--fig)")
    if base:
        text = BASE_RE.sub(lambda m: TOKENS_RE.sub("", base), text, count=1)
    if theme:
        text = THEME_RE.sub(lambda m: theme, text, count=1)
    text = OLD_FONTS_RE.sub("", text)
    return TOGGLE_RE.sub(lambda m: m.group(1) + icon("sun-moon", "") + m.group(2), text, count=1)


def inject(src, dst, snippet, base=None, theme=None, top=b""):
    """`snippet` goes before the last </body>, `top` right after <body> so it comes first when tabbing."""
    with open(src, "rb") as f:
        data = normalize(f.read().decode("utf-8", "surrogateescape"), base, theme).encode("utf-8", "surrogateescape")
    i = data.lower().rfind(b"</body>")
    data = data + snippet if i < 0 else data[:i] + snippet + data[i:]
    m = re.search(rb"<body\b[^>]*>", data, re.I)
    data = top + data if not m else data[:m.end()] + top + data[m.end():]
    low = data.lower()
    i = low.find(b"</head>")
    if i < 0:  # the closing tag is optional in HTML, and uploaded pages sometimes omit it
        i = low.find(b"<body")
    if i >= 0:
        data = data[:i] + (REMAKE_FLAG + head_tags() + REMAKE_MOBILE + REMAKE_DESKTOP).encode("utf-8") + data[i:]
    with open(dst, "wb") as f:
        f.write(data)


# Download button: a standalone copy of the page (see standalone()), saved to the device. Top-right, beside the
# theme toggle on phones; alone there on desktop, where the sidebar replaces the toggle.
DL_STYLE = ("<style>#studyhub-dl{" + BACK_STYLE.replace("left:max(14px,env(safe-area-inset-left,0px))",
            "right:max(62px,calc(env(safe-area-inset-right,0px) + 48px))") + "}#studyhub-dl svg{width:20px;height:20px}"
            "@media (hover:hover){#studyhub-dl:hover{background:var(--surface-2)}}"
            "@media " + PHONE + "{#studyhub-dl{width:44px;height:44px;right:max(66px,calc(env(safe-area-inset-right,0px) + 52px))}}"
            "@media screen and (min-width:701px){#studyhub-dl{right:14px}}@media print{#studyhub-dl{display:none}}</style>")


def download_button(module, page):
    e = html.escape
    ch, _, rel = page.partition("/")
    name = f'{module["code"]}-{ch}-{rel.replace("/", "-")}'
    return (f'{DL_STYLE}<a id="studyhub-dl" href="/{e(module["slug"])}/{e(ch)}/_download/{e(rel)}" download="{e(name)}" '
            f'data-no-save aria-label="Download this page" title="Download this page">{icon("download")}</a>')


@functools.lru_cache(maxsize=None)
def fonts_inline():
    """assets/fonts.css with each font embedded, so a downloaded page keeps its type without the site."""
    try:
        with open(os.path.join(ASSETS, "fonts.css"), encoding="utf-8") as f:
            css = f.read()
    except OSError:
        return ""
    def embed(m):
        try:
            with open(os.path.join(ASSETS, m.group(1)), "rb") as f:
                return "url(data:font/woff2;base64," + base64.b64encode(f.read()).decode("ascii") + ")"
        except OSError:
            return m.group(0)
    return "<style>" + re.sub(r"url\(/assets/([^)]+\.woff2)\)", embed, css) + "</style>\n"


def standalone(src, dst, base, theme):
    """The downloadable copy: the page with the current look, tokens and embedded fonts,
    and nothing that needs the site (no sidebar, saver or back button). Opens from a file on its own."""
    with open(src, "rb") as f:
        text = normalize(f.read().decode("utf-8", "surrogateescape"), base, theme)
    try:
        with open(os.path.join(ASSETS, "tokens.css"), encoding="utf-8") as f:
            tokens = "<style>" + f.read() + "</style>\n"
    except OSError:
        tokens = ""
    # first in <head>, so the page's own styles still win, as they do on the site
    m = re.search(r"<head\b[^>]*>", text, re.I) or re.search(r"<html\b[^>]*>", text, re.I)
    i = m.end() if m else 0
    text = text[:i] + "\n" + tokens + fonts_inline() + text[i:]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(text.encode("utf-8", "surrogateescape"))


def back_button(module):
    """Top-left "←" back to the module page, styled like the theme toggle; it parks after the
    contents like the toggle (PARK_SCRIPT). The body gets room at the top so it never covers the hero."""
    e = html.escape
    label = f'Back to {e(module["code"])}'
    css = ("<style>body{padding-top:62px}#studyhub-nav svg{width:20px;height:20px}@media (hover:hover){#studyhub-nav:hover{background:var(--surface-2)}}"
           "@media print{#studyhub-nav{display:none}}</style>")
    return (f'{css}<a id="studyhub-nav" href="/{e(module["slug"])}/" data-no-save aria-label="{label}" '
            f'title="{label}" style="{BACK_STYLE}">{icon("arrow-left")}</a>\n<script>{PARK_SCRIPT}</script>')


def build_module(module, out_root, base, warnings, theme=None, nav=()):
    src =os.path.join(MODULES, module["slug"])
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
                snippet = "\n" + back_button(module) + "\n" + download_button(module, page)
                practice = in_td or "practice" in f.lower()
                for w in lint_page(os.path.join(dirpath, f), practice, base):
                    warnings.append(f"modules/{module['slug']}/{page}: {w}")
                if practice:
                    snippet += (f'\n<script src="{asset("saver.js")}" data-module="{html.escape(module["slug"])}" '
                                f'data-page="{html.escape(page)}"></script>')
                else:
                    snippet += (f'\n<script src="{asset("reading.js")}" data-module="{html.escape(module["slug"])}" '
                                f'data-page="{html.escape(page)}"></script>')
                # a remake's own #theme-toggle stays in the page, hidden on desktop, and does the work
                side = sidebar(nav, "module", module, current=page, theme_id="cahier-side-theme")
                inject(os.path.join(dirpath, f), os.path.join(dst, ch["slug"], rel),
                       (snippet + "\n").encode("utf-8"), base, theme, (side + "\n").encode("utf-8"))
                # source folders starting with "_" are never copied, so _download can't collide with content
                standalone(os.path.join(dirpath, f), os.path.join(dst, ch["slug"], "_download", rel), base, theme)


ICON_CHECK = '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'


def sheet_totals(module, chapters):
    '''{"module/chapter/practice.html": problem count} for the practice sheets of these chapters.'''
    return {f'{module["slug"]}/{c["slug"]}/{p["file"]}': p["total"]
            for c in chapters for p in c["pages"] if p["kind"] == "practice"}


def progress_bar(module):
    totals = sheet_totals(module, module["chapters"])
    if not totals:
        return ""
    return (f'<div class="pg" data-pages="{html.escape(json.dumps(totals))}" hidden>'
            '<span class="pg-track"><span class="pg-fill"></span></span><span class="pg-txt"></span></div>')


def render_card(module):
    e = html.escape
    blurb = f'<p class="blurb">{e(module["blurb"])}</p>' if module["blurb"] else ""
    return (f'<a class="card" href="/{e(module["slug"])}/"><span class="code">{e(module["code"])}</span>'
            f'<h3>{e(module["title"] or module["code"])}</h3>{blurb}{progress_bar(module)}</a>')


def chapter_name(ch):
    return ch["label"] + (f' · {ch["title"]}' if ch["title"] else "")


def row(href, name, key=None, kind="", total=0, small="", glyph=None, keep=None):
    '''One list row. Status starts as not started; hub.js fills in progress.'''
    e = html.escape
    attrs = f' data-key="{e(key)}" data-kind="{e(kind)}" data-total="{total}"' if key else ""
    note = f"<small>{e(small)}</small>" if small else ""
    status = glyph or f'<span class="status" aria-label="Not started">{icon("circle")}</span>'
    btn = f'<button class="offline-btn" type="button" data-keep="{e(keep)}"></button>' if keep else ""
    return (f'<div class="row-wrap"><a class="row" href="{e(href)}"{attrs}>{status}'
            f'<span class="row-name">{e(name)}{note}</span><span class="row-meta"></span></a>{btn}</div>')


def viewer_href(module, ch, d, doc):
    query = urlencode({"f": f'/{module["slug"]}/{ch["slug"]}/{d}/{doc["file"]}', "t": doc["label"],
                       "b": f'/{module["slug"]}/#{ch["slug"]}'})
    return f"/viewer/?{query}"


def chapter_rows(module, ch):
    '''A chapter's lesson and practice pages, then its PDFs.'''
    e = html.escape
    out = []
    for p in ch["pages"]:
        key = f'{module["slug"]}/{ch["slug"]}/{p["file"]}'
        name = p["kind"].capitalize() if p["file"] == f'{p["kind"]}.html' else p["title"]
        out.append(row("/" + key, name, key, p["kind"], p["total"]))
    for d, name in (("cours", "Cours"), ("td", "TD")):
        if ch["docs"][d]:
            out.append(f'<p class="label row-sub">{name}</p>')
            out += [row(viewer_href(module, ch, d, x), x["label"], glyph=f'<span class="status">{icon("file-text")}</span>',
                        keep=f'/{module["slug"]}/{ch["slug"]}/{d}/{x["file"]}') for x in ch["docs"][d]]
    return "".join(out)


def render_chapter(module, ch, is_open):
    '''The first chapter starts open; hub.js opens the one I was last reading, or the one in the link.'''
    e = html.escape
    title = f'<span class="label">{e(ch["label"])}</span>{e(ch["title"])}' if ch["title"] else e(ch["label"])
    return (f'<details class="chapter" id="{e(ch["slug"])}"{" open" if is_open else ""}>'
            f'<summary><span class="chapter-name">{title}</span>{icon("chevron-down")}</summary>'
            f'{chapter_rows(module, ch)}</details>')


def render_module_page(tpl, module, nav):
    e = html.escape
    main = '<div class="chapters">' + "".join(render_chapter(module, c, i == 0) for i, c in enumerate(module["chapters"])) + "</div>"
    blurb = f'<p>{e(module["blurb"])}</p>' if module["blurb"] else ""
    head = (f'<header class="hero"><div class="hero-text"><div class="code">{e(module["code"])}</div>'
            f'<h1>{e(module["title"] or module["code"])}</h1>{blurb}{progress_bar(module)}</div>'
            f'<a class="pbtn" href="/upload/?module={e(module["slug"])}">Manage {e(module["code"])}</a></header>')
    return fill(tpl, **shell(nav, "module", module), BODYATTR=f' data-module="{e(module["slug"])}"', HEAD=head,
                PAGETITLE=f'{e(module["code"])} · {e(module["title"] or module["code"])}', MAIN=main)


def render_home(tpl, modules):
    title = html.escape(site_title())
    cat = {f'{m["slug"]}/{c["slug"]}/{p["file"]}': {"course": m["title"] or m["code"], "chapter": chapter_name(c),
                                                    "href": f'/{m["slug"]}/{c["slug"]}/{p["file"]}'}
           for m in modules for c in m["chapters"] for p in c["pages"] if p["kind"] == "lesson"}
    catalog = '<script type="application/json" id="catalog">' + json.dumps(cat, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    cards = "".join(render_card(m) for m in modules) or '<p class="none">No courses yet.</p>'
    main = ('<div id="continue"><div class="empty-card">Nothing started yet. Open a lesson below and your place will be kept here.</div></div>'
            f'<h2 class="section">Courses</h2><div class="grid">{cards}</div>')
    return fill(tpl, **shell(modules, "home"), HEAD="", CATALOG=catalog, PAGETITLE=title, MAIN=main)


def simple_head(title, sub=""):
    p = f"<p>{html.escape(sub)}</p>" if sub else ""
    return f'<header class="hero"><div class="hero-text"><h1>{html.escape(title)}</h1>{p}</div></header>'


def render_search(tpl, modules):
    main = ('<label class="label" for="search-box" style="display:block;margin-bottom:var(--space-1)">Search chapters, lessons, practice sheets and PDF names</label>'
            '<input class="search-box" id="search-box" type="search" autocomplete="off" spellcheck="false" data-no-save>'
            '<div id="search-results" style="margin-top:var(--space-4)" aria-live="polite"></div>')
    return fill(tpl, **shell(modules, "search"), HEAD=simple_head("Search"), PAGETITLE=f"Search · {html.escape(site_title())}", MAIN=main)


SEC_RE = re.compile(r'<section\b[^>]*class="sec"[^>]*\bid="([^"]+)"[^>]*>(.*?)</section>', re.S)
CUT_RE = re.compile(r"<(svg|script|style)\b.*?</\1>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def plain_text(fragment):
    return " ".join(html.unescape(TAG_RE.sub(" ", CUT_RE.sub(" ", fragment))).split())


def search_index(modules):
    '''One entry per chapter, per section of every remake and per PDF name. Read by /search/ in the browser.'''
    out = []
    for m in modules:
        for c in m["chapters"]:
            where = f'{m["code"]} {c["label"]}'
            out.append({"u": f'/{m["slug"]}/#{c["slug"]}', "h": c["title"] or c["label"],
                        "c": where if c["title"] else m["code"], "x": ""})
            for p in c["pages"]:
                with open(os.path.join(MODULES, m["slug"], c["slug"], p["file"]), encoding="utf-8", errors="replace") as f:
                    text = f.read()
                base = f'/{m["slug"]}/{c["slug"]}/{p["file"]}'
                kind = p["kind"].capitalize()
                for sid, body in SEC_RE.findall(text):
                    h2 = re.search(r"<h2\b[^>]*>(.*?)</h2>", body, re.S)
                    head = plain_text(h2.group(1)) if h2 else kind
                    out.append({"u": f"{base}#{sid}", "h": head, "c": f"{where} · {kind}", "x": plain_text(body)[:1500]})
            for d in DOC_DIRS:
                for x in c["docs"][d]:
                    out.append({"u": viewer_href(m, c, d, x), "h": x["label"], "c": f"{where} · PDF", "x": ""})
    return out


def render_viewer():
    with open(os.path.join(ROOT, "viewer_template.html"), encoding="utf-8") as f:
        tpl = f.read()
    return fill(tpl, ICON_BACK=icon("arrow-left"), ICON_DL=icon("download"))


MAIN_NAV = (("/", "house", "Home", "home"), ("/search/", "search", "Search", "search"))


def sidebar(nav, page="home", module=None, current=None, theme_id="theme-toggle"):
    '''The desktop sidebar and its collapse button (assets/sidebar.css). `module` opens that course's
    list of pages; `current` is the "<chapter>/<file>" being read.'''
    e = html.escape
    active = module["slug"] if module else None
    item = lambda href, body, on: f'<a class="nav-item{" on" if on else ""}" href="{e(href)}">{body}</a>'
    manage = "/upload/" + (f"?module={active}" if active else "")
    side = "".join(item(h, icon(i) + n, page == k) for h, i, n, k in MAIN_NAV)
    if nav:
        side += '<div class="nav-label">My courses</div>'
        for m in nav:
            side += item(f'/{m["slug"]}/', f'<span class="nav-code">{e(m["code"])}</span>'
                         f'<span class="nav-name">{e(m["title"] or m["code"])}</span>', m["slug"] == active)
            if m["slug"] == active:
                links = ""
                for c in m["chapters"]:
                    links += f'<a class="nav-ch" href="/{e(m["slug"])}/#{e(c["slug"])}">{e(c["title"] or c["label"])}</a>'
                    for p in c["pages"]:
                        here = f'{c["slug"]}/{p["file"]}' == current
                        name = p["kind"].capitalize() if p["file"] == f'{p["kind"]}.html' else p["title"]
                        links += (f'<a class="nav-pg{" on" if here else ""}" href="/{e(m["slug"])}/{e(c["slug"])}/{e(p["file"])}"'
                                  + (' aria-current="page"' if here else "") + f'>{e(name)}</a>')
                if links:
                    side += f'<div class="nav-sub">{links}</div>'
    return (f'<button id="cahier-side-btn" type="button" data-no-save aria-controls="cahier-side" '
            f'aria-label="Collapse sidebar" title="Collapse sidebar">{icon("panel-left", "")}</button>\n'
            f'<aside id="cahier-side" data-no-save>'
            f'<a class="brand" href="/"><img src="/assets/logo.svg" alt="">{e(site_title())}</a>{side}'
            f'<div class="side-foot">{item(manage, icon("folder-cog") + "Manage modules", page == "manage")}'
            f'<button class="nav-item" id="{theme_id}" type="button" aria-label="Toggle light or dark theme">'
            f'{icon("sun-moon")}Theme</button></div></aside>')


def shell(nav, page="home", module=None):
    '''Sidebar, top bar and bottom nav for hub-template pages. `module` is set on a course page.'''
    e = html.escape
    manage = "/upload/" + (f'?module={module["slug"]}' if module else "")
    tab_on = lambda k: k == page or (k == "home" and page == "module")
    tabs = "".join(f'<a class="tab{" on" if tab_on(k) else ""}" href="{e(h)}">{icon(i)}{n}</a>'
                   for h, i, n, k in MAIN_NAV + ((manage, "folder-cog", "Manage modules", "manage"),))
    return {
        "SITENAME": e(site_title()), "ICON_THEME": icon("sun-moon"), "SIDE": sidebar(nav, page, module),
        "TABS": tabs,
    }


def fill(tpl, **parts):
    parts.setdefault("BODYATTR", "")
    parts.setdefault("CATALOG", "")
    parts.setdefault("JS_HUB", asset("hub.js"))
    parts.setdefault("JS_VIEWER", asset("viewer.js"))
    parts.setdefault("JS_SPLASH", asset("splash.js"))
    for k, v in parts.items():
        tpl = tpl.replace(f"%%{k}%%", v)
    return tpl.replace("</head>", head_tags() + "</head>", 1)


UPLOAD_MAIN = r"""<main class="up">
<form id="up" class="up" style="padding:0" novalidate>
<fieldset><legend>Where</legend>
  <div class="row">
    <label class="f">Module<select id="module"></select></label>
    <label class="f">Chapter<select id="chapter"></select></label>
  </div>
  <div class="row" id="new-module" hidden>
    <label class="f">Folder (lowercase)<input type="text" id="m-slug" placeholder="e.g. cpsi" autocomplete="off"></label>
    <label class="f">Code<input type="text" id="m-code" placeholder="e.g. CPSI" autocomplete="off"></label>
    <label class="f">Title<input type="text" id="m-title" placeholder="e.g. Information Systems" autocomplete="off"></label>
    <label class="f">Blurb<input type="text" id="m-blurb" placeholder="one line, optional" autocomplete="off"></label>
  </div>
  <div class="row" id="new-chapter" hidden>
    <label class="f">Folder<input type="text" id="c-slug" placeholder="e.g. ch2 or ch1-2" autocomplete="off"></label>
    <label class="f">Chapter title<input type="text" id="c-title" placeholder="e.g. Classical cryptography (Cryptographie classique)" autocomplete="off"></label>
  </div>
</fieldset>
<fieldset><legend>What</legend>
  <div class="kinds">
    <label><input type="radio" name="kind" value="lesson" checked> Lesson</label>
    <label><input type="radio" name="kind" value="practice"> Practice</label>
    <label><input type="radio" name="kind" value="cours"> Cours PDFs</label>
    <label><input type="radio" name="kind" value="td"> TD PDFs</label>
  </div>
  <label class="drop" id="drop"><span id="drop-txt">Drop the file here or choose it</span><input type="file" id="files"></label>
  <p class="hint" id="kind-hint"></p>
</fieldset>
<p class="err" id="err" hidden></p>
<button class="btn" id="go" type="submit">Upload</button>
</form>
<ul class="jobs" id="jobs"></ul>
<section class="manage">
  <h2>Edit and delete</h2>
  <p class="hint">Edit a module's code, title and blurb, or a chapter's title. Delete a file, a chapter or a whole module. Every change is a commit, so git history keeps the old version. A deleted practice page takes its saved answers with it (the nightly Drive backup still has them).</p>
  <div id="tree"></div>
</section>
</main>
<script>
(function(){
  var DATA=%%DATA%%, $=function(id){return document.getElementById(id);};
  var SLUG=/^[a-z0-9][a-z0-9.\-]{0,99}$/, HINT={
    lesson:'One .html file. It becomes lesson.html and replaces the current one (the old version stays in git).',
    practice:'One .html file. It becomes practice.html; saved answers survive if the field ids stay the same.',
    cours:'PDFs, several at once. Named <n>-<topic>.pdf after the ones already there.',
    td:'PDFs, several at once. Named <n>-<topic>.pdf in the td/ folder of the chapter.'};
  var mSel=$('module'), cSel=$('chapter'), files=$('files');
  function opt(v,t){var o=document.createElement('option');o.value=v;o.textContent=t;return o;}
  function kind(){return document.querySelector('input[name=kind]:checked').value;}
  function fillModules(sel){
    mSel.innerHTML='';
    DATA.forEach(function(m){mSel.appendChild(opt(m.slug,m.code+' · '+m.title));});
    mSel.appendChild(opt('+','+ New module'));
    if(sel)mSel.value=sel;
    fillChapters();
  }
  function fillChapters(sel){
    var m=DATA.filter(function(x){return x.slug===mSel.value;})[0];
    cSel.innerHTML='';
    (m?m.chapters:[]).forEach(function(c){cSel.appendChild(opt(c.slug,c.label+(c.title?' · '+c.title:'')));});
    cSel.appendChild(opt('+','+ New chapter'));
    if(sel)cSel.value=sel;
    $('new-module').hidden=mSel.value!=='+';
    $('new-chapter').hidden=cSel.value!=='+';
  }
  function setKind(){
    var k=kind(), pdf=k==='cours'||k==='td';
    files.multiple=pdf; files.accept=pdf?'.pdf,application/pdf':'.html,text/html';
    $('kind-hint').textContent=HINT[k]; files.value=''; $('drop-txt').textContent=pdf?'Drop the PDFs here or choose them':'Drop the file here or choose it';
  }
  mSel.addEventListener('change',function(){fillChapters();});
  cSel.addEventListener('change',function(){$('new-chapter').hidden=cSel.value!=='+';});
  document.querySelectorAll('input[name=kind]').forEach(function(r){r.addEventListener('change',setKind);});
  var drop=$('drop');
  ['dragenter','dragover'].forEach(function(t){drop.addEventListener(t,function(e){e.preventDefault();drop.classList.add('over');});});
  ['dragleave','drop'].forEach(function(t){drop.addEventListener(t,function(e){e.preventDefault();drop.classList.remove('over');});});
  drop.addEventListener('drop',function(e){files.files=e.dataTransfer.files;});

  function fail(msg){$('err').textContent=msg;$('err').hidden=!msg;return false;}
  function target(){
    var m=mSel.value, c=cSel.value, q={};
    if(m==='+'){
      m=$('m-slug').value.trim();
      if(!SLUG.test(m))return fail('Module folder: lowercase letters, digits, "-" and "." only.');
      if(DATA.some(function(x){return x.slug===m;}))return fail('Module '+m+' already exists: pick it in the list.');
      q.module_code=$('m-code').value.trim()||m.toUpperCase(); q.module_title=$('m-title').value.trim(); q.blurb=$('m-blurb').value.trim();
      if(!q.module_title)return fail('Give the new module a title.');
    }
    if(c==='+'){
      c=$('c-slug').value.trim();
      if(!SLUG.test(c))return fail('Chapter folder: lowercase letters, digits, "-" and "." (e.g. ch2).');
      q.title=$('c-title').value.trim();
      if(!q.title)return fail('Give the new chapter a title.');
    }
    q.module=m; q.chapter=c; return q;
  }
  function row(name){
    var li=document.createElement('li');
    li.innerHTML='<b></b><span class="st">waiting</span>';
    li.firstChild.textContent=name; $('jobs').prepend(li); return li;
  }
  function status(li,cls,text){li.className=cls||'';li.querySelector('.st').textContent=text;}
  function esc(t){var d=document.createElement('div');d.textContent=t;return d.innerHTML;}
  function renderTree(){
    var t=$('tree'); t.innerHTML='';
    if(!DATA.length){t.innerHTML='<p class="hint">Nothing to delete.</p>';return;}
    DATA.forEach(function(m){
      var d=document.createElement('details'); d.className='mod';
      d.innerHTML='<summary><span class="chip">'+esc(m.code)+'</span><span>'+esc(m.title)+'</span>'
        +'<button class="edt" type="button" data-m="'+esc(m.slug)+'">Edit</button>'
        +'<button class="del" type="button" data-m="'+esc(m.slug)+'">Delete module</button></summary>';
      if(!m.chapters.length)d.insertAdjacentHTML('beforeend','<div class="tree-ch"><span class="hint">No chapters.</span></div>');
      m.chapters.forEach(function(c){
        var div=document.createElement('div'); div.className='tree-ch';
        div.innerHTML='<div class="tree-h"><span>'+esc(c.label+(c.title?' · '+c.title:''))+'</span>'
          +'<button class="edt" type="button" data-m="'+esc(m.slug)+'" data-c="'+esc(c.slug)+'">Edit</button>'
          +'<button class="del" type="button" data-m="'+esc(m.slug)+'" data-c="'+esc(c.slug)+'">Delete chapter</button></div><ul></ul>';
        (c.files||[]).forEach(function(f){
          var li=document.createElement('li');
          li.innerHTML='<span class="ft">'+esc(f.kind==='lesson'||f.kind==='practice'?'HTML':f.kind.toUpperCase())+'</span><span>'+esc(f.label)+'</span>'
            +'<button class="del" type="button" data-m="'+esc(m.slug)+'" data-c="'+esc(c.slug)+'" data-p="'+esc(f.path)+'">Delete</button>';
          div.querySelector('ul').appendChild(li);
        });
        d.appendChild(div);
      });
      t.appendChild(d);
    });
  }
  function dropFromData(q){
    var m=DATA.filter(function(x){return x.slug===q.module;})[0]; if(!m)return;
    if(q.chapter===undefined){DATA.splice(DATA.indexOf(m),1);return;}
    var c=m.chapters.filter(function(x){return x.slug===q.chapter;})[0]; if(!c)return;
    if(q.path!==undefined)c.files=c.files.filter(function(f){return f.path!==q.path;});
    if(q.path===undefined||!c.files.length)m.chapters.splice(m.chapters.indexOf(c),1);
  }
  function find(ms,cs){
    var m=DATA.filter(function(x){return x.slug===ms;})[0];
    return [m, m&&cs!==undefined?m.chapters.filter(function(x){return x.slug===cs;})[0]:undefined];
  }
  function field(f,n){return f.elements.namedItem(n);}
  $('tree').addEventListener('click',function(e){
    var b=e.target.closest('.edt'); if(!b)return;
    e.preventDefault();
    var mc=find(b.dataset.m,b.dataset.c), m=mc[0], c=mc[1];
    var host=c?b.closest('.tree-ch'):b.closest('details'), open=host.querySelector(':scope>form.edit-form');
    if(open){open.remove();return;}
    if(!c)host.open=true;
    var f=document.createElement('form'); f.className='edit-form'; f.noValidate=true;
    f.dataset.m=m.slug; if(c)f.dataset.c=c.slug;
    f.innerHTML=(c?'<div class="row"><label class="f">Folder<input type="text" name="folder" maxlength="100" autocomplete="off" spellcheck="false"></label>'
       +'<label class="f">Chapter title<input type="text" name="title" maxlength="200" autocomplete="off"></label></div>'
      :'<div class="row"><label class="f">Folder<input type="text" name="folder" maxlength="100" autocomplete="off" spellcheck="false"></label>'
       +'<label class="f">Code<input type="text" name="code" maxlength="20" autocomplete="off"></label></div>'
       +'<label class="f">Title<input type="text" name="title" maxlength="200" autocomplete="off"></label>'
       +'<label class="f">Blurb<input type="text" name="blurb" maxlength="300" autocomplete="off"></label>')
      +'<p class="hint">'+(c?'Folder: lowercase, e.g. ch1 or ch1-2 (shown as Chapter 1 / Chapters 1\u20132). ':'Folder: lowercase, e.g. opl. ')
      +'Renaming it moves the saved answers along and changes the page addresses, so old bookmarks stop working.</p>'
      +'<p class="err" hidden></p><div class="edit-actions"><button class="btn sm" type="submit">Save</button>'
      +'<button class="pbtn" type="button" data-cancel>Cancel</button></div>';
    field(f,'folder').value=c?c.slug:m.slug;
    if(c)field(f,'title').value=c.title||'';
    else{field(f,'code').value=m.code;field(f,'title').value=m.title;field(f,'blurb').value=m.blurb||'';}
    if(c)b.closest('.tree-h').after(f); else host.querySelector('summary').after(f);
    field(f,'title').focus();
  });
  $('tree').addEventListener('click',function(e){
    var x=e.target.closest('[data-cancel]'); if(x){e.preventDefault();x.closest('form').remove();}
  });
  $('tree').addEventListener('submit',function(e){
    var f=e.target; if(!f.classList.contains('edit-form'))return;
    e.preventDefault();
    var mc=find(f.dataset.m,f.dataset.c), m=mc[0], c=mc[1], q={action:'edit',module:m.slug}, err=f.querySelector('.err');
    function clean(n){return field(f,n).value.replace(/\s+/g,' ').trim();}
    function bad(t){err.textContent=t;err.hidden=false;}
    var folder=clean('folder').replace(/ /g,'');
    if(!SLUG.test(folder))return bad('Folder: lowercase letters, digits, "-" and "." only.');
    if(folder!==(c?c.slug:m.slug)){
      var taken=c?m.chapters.some(function(x){return x.slug===folder;}):DATA.some(function(x){return x.slug===folder;});
      if(taken)return bad((c?m.slug+'/':'')+folder+' already exists.');
      if(!c&&(folder==='upload'||folder==='assets'))return bad(folder+' is reserved.');
      q.folder=folder;
    }
    if(c){q.chapter=c.slug; var t=clean('title'); if(!t)return bad('The title can\u2019t be empty.');
      if(t!==c.title)q.title=t;}
    else{
      ['code','title','blurb'].forEach(function(n){var v=clean(n);if(v!==(n==='blurb'?(m.blurb||''):m[n]))q[n]=v;});
      if(q.code===''||q.title==='')return bad('Code and title can\u2019t be empty.');
    }
    if(Object.keys(q).length===(c?3:2)){f.remove();return;}
    if(q.folder&&!confirm('Rename the folder '+(c?m.slug+'/'+c.slug:m.slug)+' to '+(c?m.slug+'/':'')+q.folder+'?\n\nSaved answers move with it. Old links and bookmarks to it stop working.'))return;
    f.querySelector('button[type=submit]').disabled=true;
    var li=row('Edit '+m.code+(c?' '+c.slug:''));
    fetch('/api/manage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)})
      .then(function(r){return r.json().then(function(j){return [r.status,j];});})
      .then(function(x){
        if(x[0]===200&&x[1].id){status(li,'','Queued…');poll(li,x[1].id,0,function(r){
          if(q.folder){setTimeout(function(){location.href='/upload/?module='+encodeURIComponent(r.module||m.slug);},1500);return;}
          if(c){if(q.title!==undefined)c.title=q.title;} else ['code','title','blurb'].forEach(function(n){if(q[n]!==undefined)m[n]=q[n];});
          renderTree(); fillModules(mSel.value);});}
        else{status(li,'bad','Rejected: '+(x[1].error||('HTTP '+x[0])));f.querySelector('button[type=submit]').disabled=false;}
      }).catch(function(){status(li,'bad','Request failed (network)');f.querySelector('button[type=submit]').disabled=false;});
  });
  $('tree').addEventListener('click',function(e){
    var b=e.target.closest('.del'); if(!b)return;
    e.preventDefault();
    var q={action:'delete',module:b.dataset.m}, m=DATA.filter(function(x){return x.slug===q.module;})[0], name;
    if(b.dataset.c!==undefined)q.chapter=b.dataset.c;
    if(b.dataset.p!==undefined)q.path=b.dataset.p;
    if(q.path!==undefined){
      name=m.code+' '+q.chapter+' '+q.path;
      if(!confirm('Delete '+name+'?'+(q.path==='practice.html'?'\n\nIts saved answers are deleted too.':'')))return;
    }else if(q.chapter!==undefined){
      name=m.code+' '+q.chapter;
      if(!confirm('Delete the whole chapter '+name+', with all its files and saved answers?'))return;
    }else{
      name=m.code+' (whole module)';
      var typed=prompt('This deletes every chapter, file and saved answer of '+m.code+'.\nType '+m.code+' to confirm.');
      if(typed===null)return;
      if(typed.trim()!==m.code){alert('That was not '+m.code+'. Nothing deleted.');return;}
    }
    b.disabled=true;
    var li=row('Delete '+name);
    fetch('/api/manage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)})
      .then(function(r){return r.json().then(function(j){return [r.status,j];});})
      .then(function(x){
        if(x[0]===200&&x[1].id){status(li,'','Queued…');poll(li,x[1].id,0,function(){dropFromData(q);renderTree();fillModules(mSel.value);});}
        else{status(li,'bad','Rejected: '+(x[1].error||('HTTP '+x[0])));b.disabled=false;}
      }).catch(function(){status(li,'bad','Request failed (network)');b.disabled=false;});
  });
  function poll(li,id,tries,ondone){
    fetch('/api/upload?id='+id,{cache:'no-store'}).then(function(r){return r.json();}).then(function(r){
      if(r.state==='done'&&r.edited!==undefined){
        var eg={pushed:'saved to GitHub',committed:'committed',unchanged:'nothing changed','push-failed':'committed on the server, push to GitHub failed (retried by the next update)'}[r.git]||r.git;
        status(li,'ok',r.edited?'Saved · '+r.edited+' · '+eg+(r.answers_moved?' · '+r.answers_moved+' saved answer'+(r.answers_moved===1?'':'s')+' moved':''):'No change');
        if(ondone)ondone(r);
      }else if(r.state==='done'&&r.deleted){
        var g={pushed:'saved to GitHub',committed:'committed','push-failed':'committed on the server, push to GitHub failed (retried by the next update)'}[r.git]||r.git;
        status(li,'ok','Deleted · '+g+(r.answers_deleted?' · '+r.answers_deleted+' saved answer'+(r.answers_deleted===1?'':'s')+' removed':''));
        if(ondone)ondone();
      }else if(r.state==='done'){
        var git={pushed:'saved to GitHub',committed:'committed',unchanged:'identical to the current file, nothing to commit','push-failed':'committed on the server, push to GitHub failed (retried by the next update)'}[r.git]||r.git;
        status(li,'ok','Live · '+git+(r.replaced&&r.git!=='unchanged'?' · replaced the old file':''));
        var a=document.createElement('a');a.href=r.url;a.textContent='Open '+r.url;a.target='_blank';li.appendChild(a);
        if(ondone)ondone(r);
        if(r.warnings&&r.warnings.length){var ul=document.createElement('ul');r.warnings.forEach(function(w){var x=document.createElement('li');x.textContent=w;ul.appendChild(x);});li.appendChild(ul);}
      }else if(r.state==='error'||r.error){status(li,'bad','Failed: '+(r.error||'unknown error'));}
      else if(tries>180){status(li,'bad','Still '+r.state+' after 3 minutes. Is studysite-ingest.path running on the server?');}
      else{status(li,'',r.state==='processing'?'Building and committing…':'Queued…');setTimeout(function(){poll(li,id,tries+1,ondone);},1000);}
    }).catch(function(){setTimeout(function(){poll(li,id,tries+1,ondone);},2000);});
  }
  function addFile(q,url){
    var m=DATA.filter(function(x){return x.slug===q.module;})[0]; if(!m)return;
    var c=m.chapters.filter(function(x){return x.slug===q.chapter;})[0]; if(!c)return;
    var path=url.split('/').slice(3).join('/'), k=path.split('/')[0];
    if(!c.files.some(function(f){return f.path===path;}))
      c.files.push({path:path,kind:k.indexOf('.html')>0?k.replace('.html',''):k,label:path.split('/').pop()});
    renderTree();
  }
  function send(file,q,done){
    var li=row(file.name), x=new XMLHttpRequest(), p=Object.assign({kind:kind(),name:file.name},q);
    x.open('PUT','/api/upload?'+new URLSearchParams(p));
    x.upload.onprogress=function(e){if(e.lengthComputable)status(li,'','Uploading '+Math.round(100*e.loaded/e.total)+'%');};
    x.onload=function(){
      var r={};try{r=JSON.parse(x.responseText);}catch(e){}
      if(x.status===200&&r.id){status(li,'','Queued…');poll(li,r.id,0,function(res){addFile(q,res.url);});}
      else status(li,'bad','Rejected: '+(r.error||('HTTP '+x.status)));
      done();
    };
    x.onerror=function(){status(li,'bad','Upload failed (network)');done();};
    x.send(file);
  }
  $('up').addEventListener('submit',function(e){
    e.preventDefault(); fail('');
    var q=target(); if(!q)return;
    var list=[].slice.call(files.files), k=kind();
    if(!list.length)return fail('Choose a file first.');
    var ext=(k==='cours'||k==='td')?'.pdf':'.html';
    var bad=list.filter(function(f){return f.name.toLowerCase().slice(-ext.length)!==ext;});
    if(bad.length)return fail(bad[0].name+' is not a '+ext+' file.');
    if(ext==='.html'&&list.length>1)return fail('One HTML file at a time.');
    $('go').disabled=true;
    var m=DATA.filter(function(x){return x.slug===q.module;})[0];
    function start(){
      // remember a new module/chapter so the next upload can pick it
      if(!m){m={slug:q.module,code:q.module_code,title:q.module_title,chapters:[]};DATA.push(m);}
      if(!m.chapters.some(function(c){return c.slug===q.chapter;}))m.chapters.push({slug:q.chapter,label:q.chapter,title:q.title||'',files:[]});
      (function next(i){ if(i>=list.length){$('go').disabled=false;files.value='';fillModules(q.module);fillChapters(q.chapter);return;}
        send(list[i],q,function(){next(i+1);}); })(0);
    }
    if(ext!=='.html')return start();
    // ask before replacing a remake: the live site decides, because this page's list can be out of date
    var path=k+'.html', c=m&&m.chapters.filter(function(x){return x.slug===q.chapter;})[0];
    var listed=!!c&&c.files.some(function(f){return f.path===path;});
    fetch('/'+encodeURIComponent(q.module)+'/'+encodeURIComponent(q.chapter)+'/'+path,{method:'HEAD',cache:'no-store'})
      .then(function(r){return r.ok;},function(){return listed;})
      .then(function(exists){
        if(!exists||confirm((m?m.code:q.module)+' '+(c?c.label:q.chapter)+' already has a '+k+' page.\n\nReplace it with '+list[0].name+'?\n\nThe old version stays in git history.'))return start();
        $('go').disabled=false; fail('Nothing uploaded: the current '+k+' page stays.');
      });
  });
  var pre=new URLSearchParams(location.search).get('module');
  fillModules(DATA.some(function(m){return m.slug===pre;})?pre:(DATA[0]||{}).slug); setKind(); renderTree();
})();
</script>"""


def render_upload(tpl, modules, nav):
    def files(c):
        out = [{"path": p["file"], "kind": p["kind"], "label": p["kind"].capitalize() + " · " + p["file"]} for p in c["pages"]]
        for d in DOC_DIRS:
            out += [{"path": f"{d}/{x['file']}", "kind": d, "label": x["file"]} for x in c["docs"][d]]
        return out
    data = [{"slug": m["slug"], "code": m["code"], "title": m["title"] or m["code"], "blurb": m["blurb"],
             "chapters": [{"slug": c["slug"], "label": c["label"], "title": c["title"], "files": files(c)}
                          for c in m["chapters"]]}
            for m in modules]
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    head = (f'<header class="hero"><div class="hero-text"><div class="eyebrow">{html.escape(site_title())}</div>'
            '<h1>Manage modules</h1><p>Upload lessons, practice sheets and PDFs, or edit and delete them. '
            'Every change goes live and is committed to GitHub.</p></div></header>')
    return fill(tpl, **shell(nav, "manage"), HEAD=head, PAGETITLE=f"Manage modules · {html.escape(site_title())}",
                MAIN=UPLOAD_MAIN.replace("%%DATA%%", js))


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
        if s in ("assets", "upload", "viewer", "search", "search.json",
                 "manifest.webmanifest", "sw.js") or not NAME_RE.match(s):
            sys.exit(f"error: module folder name {s!r} is reserved or invalid")

    every = sorted((load_module(s) for s in slugs), key=lambda m: (m["order"], m["code"].lower()))
    modules = [m for m in every if m["chapters"]]  # empty modules stay hidden (but can be deleted on /upload/)
    base, warnings = remake_base(), []
    for m in modules:
        build_module(m, NEW, base, warnings, remake_theme(), modules)

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    def page(rel, text):
        path = os.path.join(NEW, rel, "index.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    page("", render_home(tpl, modules))
    page("search", render_search(tpl, modules))
    page("viewer", render_viewer())
    page("upload", render_upload(tpl, every, modules))
    for m in modules:
        page(m["slug"], render_module_page(tpl, m, modules))
    with open(os.path.join(NEW, "search.json"), "w", encoding="utf-8") as f:
        json.dump(search_index(modules), f, ensure_ascii=False, separators=(",", ":"))
    write_pwa(NEW)

    if os.path.exists(DIST):
        os.rename(DIST, OLD)
    os.rename(NEW, DIST)
    shutil.rmtree(OLD, ignore_errors=True)

    tokens_file = os.path.join(ASSETS, "tokens.css")
    with open(tokens_file, encoding="utf-8") as f, open(REMAKE_TEMPLATE, encoding="utf-8") as g:
        if f.read().strip() not in g.read():
            warnings.append("remake_template.html: its tokens copy differs from assets/tokens.css")
    n_ch = sum(len(m["chapters"]) for m in modules)
    n_pages = sum(len(c["pages"]) for m in modules for c in m["chapters"])
    print(f"built {len(modules)} module(s), {n_ch} chapter(s), {n_pages} page(s) -> dist/")
    for w in warnings:
        warn(w)


if __name__ == "__main__":
    main()
