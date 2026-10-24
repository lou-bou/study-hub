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
# Back button on every remake: the theme toggle's look, mirrored to the top-left corner.
BACK_STYLE = (
    "position:fixed;top:14px;left:max(14px,env(safe-area-inset-left,0px));z-index:20;"
    "border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;"
    "padding:6px 14px;font:500 .8rem var(--f-body);text-decoration:none;cursor:pointer"
)
# Pages render bigger on wide screens, like a browser zoom of 125% / 150%; phones are unchanged.
ZOOM_STYLE = ("<style>@media (min-width:1200px){html{zoom:1.25}}"
              "@media (min-width:1500px){html{zoom:1.5}}</style>\n")
# The theme toggle and the nav bar follow the viewport until they reach the end of the contents
# (.toc, else .hero), then each parks just below that line and scrolls away with the page.
PARK_SCRIPT = (
    '(function(){var els=[document.getElementById("theme-toggle"),document.getElementById("studyhub-nav")]'
    '.filter(Boolean),orig=els.map(function(el){return el.style.cssText});'
    'function park(){var a=document.querySelector(".toc")||document.querySelector(".hero");'
    'if(!a)return;var line=a.getBoundingClientRect().bottom+scrollY;els.forEach(function(el,i){'
    'var s=el.style;s.cssText=orig[i];var r=el.getBoundingClientRect();if(!r.height)return;'
    # rects are in screen px, `top` in the page's px (divided by the html zoom); park 10px below the line
    'var k=1/(parseFloat(getComputedStyle(document.documentElement).zoom)||1);'
    'if(scrollY+r.top<line+10/k)return;s.setProperty("position","absolute","important");'
    's.setProperty("top",line*k+10+"px","important");s.setProperty("bottom","auto","important");});}'
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
    i = data.lower().find(b"</head>")
    if i >= 0:
        data = data[:i] + ZOOM_STYLE.encode("utf-8") + data[i:]
    with open(dst, "wb") as f:
        f.write(data)


def back_button(module):
    """Top-left "←" back to the module page, styled like the theme toggle; it parks after the
    contents like the toggle (PARK_SCRIPT). The body gets room at the top so it never covers the hero."""
    e = html.escape
    label = f'Back to {e(module["code"])}'
    css = ("<style>body{padding-top:62px}#studyhub-nav:hover{border-color:var(--accent)}"
           "@media print{#studyhub-nav{display:none}}</style>")
    return (f'{css}<a id="studyhub-nav" href="/{e(module["slug"])}/" data-no-save aria-label="{label}" '
            f'title="{label}" style="{BACK_STYLE}">&larr;</a>\n<script>{PARK_SCRIPT}</script>')


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
                snippet = "\n" + back_button(module)
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


ALL_MODULES = '<a class="pbtn back" href="/" aria-label="All modules" title="All modules">&larr;</a>'
SAVED_STAT = '<span><b id="saved-total">0</b> <span id="saved-word">answers</span> saved</span>'


def fill(tpl, **parts):
    for k, v in parts.items():
        tpl = tpl.replace(f"%%{k}%%", v)
    return tpl.replace("</head>", ZOOM_STYLE + "</head>", 1)


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
    return fill(tpl, PAGETITLE=title, BACK="", ACTIONS='<a class="pbtn" href="/upload/">Manage modules</a>',
                EYEBROW="Master Big Data Analytics · USTHB", TITLE=title,
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
                BACK=ALL_MODULES,
                ACTIONS=f'<a class="pbtn" href="/upload/?module={e(module["slug"])}">Manage {e(module["code"])}</a>',
                EYEBROW=e(module["code"]),
                TITLE=e(module["title"] or module["code"]), SUB=e(module["blurb"]), STATS=stats,
                MAIN=f'<main class="chapters">\n{chapters}\n</main>')
    return page.replace("<body>", f'<body data-module="{e(module["slug"])}">', 1)


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
    f.innerHTML=(c?'<label class="f">Chapter title<input type="text" name="title" maxlength="200" autocomplete="off"></label>'
      :'<div class="row"><label class="f">Code<input type="text" name="code" maxlength="20" autocomplete="off"></label>'
       +'<label class="f">Title<input type="text" name="title" maxlength="200" autocomplete="off"></label></div>'
       +'<label class="f">Blurb<input type="text" name="blurb" maxlength="300" autocomplete="off"></label>')
      +'<p class="hint">The folder name ('+esc(c?m.slug+'/'+c.slug:m.slug)+') stays the same: saved answers and links use it.</p>'
      +'<p class="err" hidden></p><div class="edit-actions"><button class="btn sm" type="submit">Save</button>'
      +'<button class="pbtn" type="button" data-cancel>Cancel</button></div>';
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
    if(c){q.chapter=c.slug; q.title=clean('title'); if(!q.title){err.textContent='The title can\u2019t be empty.';err.hidden=false;return;}
      if(q.title===c.title){f.remove();return;}}
    else{
      ['code','title','blurb'].forEach(function(n){var v=clean(n);if(v!==(n==='blurb'?(m.blurb||''):m[n]))q[n]=v;});
      if(q.code===''||q.title===''){err.textContent='Code and title can\u2019t be empty.';err.hidden=false;return;}
      if(Object.keys(q).length===2){f.remove();return;}
    }
    f.querySelector('button[type=submit]').disabled=true;
    var li=row('Edit '+m.code+(c?' '+c.slug:''));
    fetch('/api/manage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)})
      .then(function(r){return r.json().then(function(j){return [r.status,j];});})
      .then(function(x){
        if(x[0]===200&&x[1].id){status(li,'','Queued…');poll(li,x[1].id,0,function(){
          if(c)c.title=q.title; else ['code','title','blurb'].forEach(function(n){if(q[n]!==undefined)m[n]=q[n];});
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
        status(li,'ok',r.edited?'Saved · '+r.edited+' · '+eg:'No change');
        if(ondone)ondone();
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
    // remember a new module/chapter so the next upload can pick it
    var m=DATA.filter(function(x){return x.slug===q.module;})[0];
    if(!m){m={slug:q.module,code:q.module_code,title:q.module_title,chapters:[]};DATA.push(m);}
    if(!m.chapters.some(function(c){return c.slug===q.chapter;}))m.chapters.push({slug:q.chapter,label:q.chapter,title:q.title||'',files:[]});
    (function next(i){ if(i>=list.length){$('go').disabled=false;files.value='';fillModules(q.module);fillChapters(q.chapter);return;}
      send(list[i],q,function(){next(i+1);}); })(0);
  });
  var pre=new URLSearchParams(location.search).get('module');
  fillModules(DATA.some(function(m){return m.slug===pre;})?pre:(DATA[0]||{}).slug); setKind(); renderTree();
})();
</script>"""


def render_upload(tpl, modules):
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
    return fill(tpl, PAGETITLE="Manage modules · Study Hub", BACK=ALL_MODULES, ACTIONS="",
                EYEBROW="Study Hub", TITLE="Manage modules",
                SUB="Upload lessons, practice sheets and PDFs, or delete them. Every change goes live and is committed to GitHub.",
                STATS="", MAIN=UPLOAD_MAIN.replace("%%DATA%%", js))


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
        if s in ("assets", "upload") or not NAME_RE.match(s):
            sys.exit(f"error: module folder name {s!r} is reserved or invalid")

    every = sorted((load_module(s) for s in slugs), key=lambda m: (m["order"], m["code"].lower()))
    modules = [m for m in every if m["chapters"]]  # empty modules stay hidden (but can be deleted on /upload/)
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
    os.makedirs(os.path.join(NEW, "upload"))
    with open(os.path.join(NEW, "upload", "index.html"), "w", encoding="utf-8") as f:
        f.write(render_upload(tpl, every))

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
