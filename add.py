#!/usr/bin/env python3
"""Add or update a chapter, check it, commit and push. Python 3 stdlib only.

    python3 add.py <module> <chapter> FILE... [--title "Chapter title"] [--td FILE...] [--no-push]

FILE can be a remake (*.html: "practice" in the name -> practice.html, otherwise lesson.html)
or a course PDF (-> cours/). --td files go to td/. PDFs are named <n>-<topic>.pdf, numbered
after the ones already there. A new module gets a module.json to edit.
The ThinkPad picks the push up within a few minutes (deploy/update.sh).

    python3 add.py thor ch2 ~/dl/lesson.html ~/dl/practice.html ~/dl/methodes.pdf --title "Methods"

The same functions back the website's upload page (deploy/ingest.py).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(ROOT, "modules")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,99}$")
KINDS = ("lesson", "practice", "cours", "td")
RESERVED = ("assets", "upload", "viewer", "search", "search.json",
            "manifest.webmanifest", "sw.js")  # site paths that build.py generates


class AddError(Exception):
    pass


def check_slug(name, what):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise AddError(f"{what} {name!r}: use lowercase letters, digits, '-' and '.'")
    return name


def check_module(name):
    check_slug(name, "module")
    if name in RESERVED:
        raise AddError(f"module {name!r} is reserved, pick another name")
    return name


def git(*args, capture=False):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise AddError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip() if capture else None


def kind_of(path):
    """CLI guess: lesson/practice from an .html name, cours for a .pdf."""
    name = os.path.basename(path).lower()
    if name.endswith(".html"):
        return "practice" if "practice" in name else "lesson"
    if name.endswith(".pdf"):
        return "cours"
    raise AddError(f"don't know where to put {os.path.basename(path)} (expected .html or .pdf)")


def doc_name(folder, filename):
    """'Crypto classique.pdf' -> '<next n>-Crypto-classique.pdf'; a name that already starts
    with a number keeps it, so re-adding 2-methodes.pdf replaces that file."""
    stem, ext = os.path.splitext(os.path.basename(filename))
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9.\-]+", "-", stem).strip("-.") or "document"
    stem = re.sub(r"-{2,}", "-", stem)
    if not re.match(r"^\d+-", stem):
        taken = [int(m.group(1)) for f in (os.listdir(folder) if os.path.isdir(folder) else [])
                 if (m := re.match(r"^(\d+)-", f))]
        stem = f"{max(taken, default=0) + 1}-{stem}"
    return stem + ext.lower()


def place(module, chapter, kind, src, filename=None):
    """Copy src into modules/<module>/<chapter>/. Returns (path relative to the chapter, replaced?)."""
    check_module(module)
    check_slug(chapter, "chapter")
    if kind not in KINDS:
        raise AddError(f"unknown kind {kind!r}")
    ch_dir = os.path.join(MODULES, module, chapter)
    for d in ("cours", "td"):
        os.makedirs(os.path.join(ch_dir, d), exist_ok=True)
    if kind in ("lesson", "practice"):
        rel = f"{kind}.html"
    else:
        rel = f"{kind}/{doc_name(os.path.join(ch_dir, kind), filename or src)}"
    dst = os.path.join(ch_dir, rel)
    replaced = os.path.exists(dst)
    shutil.copyfile(src, dst)
    td = os.path.join(ch_dir, "td")
    keep = os.path.join(td, ".gitkeep")
    if any(f != ".gitkeep" for f in os.listdir(td)):
        if os.path.exists(keep):
            os.remove(keep)
    else:
        open(keep, "a").close()
    return rel, replaced


def check_file(path):
    """A file inside a chapter: lesson.html, practice.html, cours/<name> or td/<name>."""
    parts = path.split("/") if isinstance(path, str) else []
    ok = (parts in (["lesson.html"], ["practice.html"])
          or (len(parts) == 2 and parts[0] in ("cours", "td") and parts[1] and not parts[1].startswith(".")
              and len(parts[1]) <= 200 and "\\" not in parts[1]))
    if not ok:
        raise AddError(f"invalid file {path!r}")
    return path


def remove(module, chapter=None, path=None):
    """Delete a file, a chapter or a whole module from modules/. A chapter left with no files
    goes too. Returns a short description for the commit message."""
    check_module(module)
    mod_dir = os.path.join(MODULES, module)
    if not os.path.isdir(mod_dir):
        raise AddError(f"no module {module}")
    if chapter is None:
        shutil.rmtree(mod_dir)
        return f"{module.upper()} (whole module)"
    check_slug(chapter, "chapter")
    ch_dir = os.path.join(mod_dir, chapter)
    if not os.path.isdir(ch_dir):
        raise AddError(f"no chapter {module}/{chapter}")
    what = f"{module.upper()} {chapter}"
    if path is not None:
        target = os.path.join(ch_dir, check_file(path))
        if not os.path.isfile(target):
            raise AddError(f"no file {module}/{chapter}/{path}")
        os.remove(target)
        what += f" {path}"
        left = [f for _, _, fs in os.walk(ch_dir) for f in fs if f != ".gitkeep"]
        if left:
            td = os.path.join(ch_dir, "td")
            if os.path.isdir(td) and not os.listdir(td):
                open(os.path.join(td, ".gitkeep"), "a").close()
            return what
    shutil.rmtree(ch_dir)
    meta_path = os.path.join(mod_dir, "module.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if (meta.get("chapters") or {}).pop(chapter, None) is not None:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
                f.write("\n")
    return what if path is not None else f"{what} (whole chapter)"


def set_meta(module, chapter, title=None, module_title=None, module_code=None, blurb=None):
    """Create or update modules/<module>/module.json. Returns True for a new module."""
    mod_dir = os.path.join(MODULES, module)
    path = os.path.join(mod_dir, "module.json")
    new = not os.path.exists(path)
    if new:
        orders = []
        for m in os.listdir(MODULES):
            try:
                with open(os.path.join(MODULES, m, "module.json"), encoding="utf-8") as f:
                    orders.append(int(json.load(f).get("order", 0)))
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        meta = {"code": module.upper(), "title": module.upper(), "blurb": "",
                "order": max(orders, default=0) + 1, "chapters": {}}
    else:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
    before = json.dumps(meta, sort_keys=True)
    for key, value in (("code", module_code), ("title", module_title), ("blurb", blurb)):
        if value:
            meta[key] = value
    if title:
        meta.setdefault("chapters", {})[chapter] = title
    if new or json.dumps(meta, sort_keys=True) != before:
        os.makedirs(mod_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return new


LIMITS = {"code": 20, "title": 200, "blurb": 300}


def check_edit(module, chapter=None, code=None, title=None, blurb=None, folder=None):
    """Validate an edit without touching anything. `folder` renames the chapter's folder (or the
    module's, without a chapter). Returns (cleaned fields, new folder or None); None = unchanged."""
    check_module(module)
    mod_dir = os.path.join(MODULES, module)
    if not os.path.isdir(mod_dir):
        raise AddError(f"no module {module}")
    fields = {"code": code, "title": title, "blurb": blurb}
    for key, value in fields.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise AddError(f"{key} must be text")
        fields[key] = value = " ".join(value.split())
        if len(value) > LIMITS[key]:
            raise AddError(f"{key} is too long (max {LIMITS[key]} characters)")
        if not value and key != "blurb":
            raise AddError(f"{key} can't be empty")
    current = chapter if chapter is not None else module
    if folder == current:
        folder = None
    if chapter is not None:
        check_slug(chapter, "chapter")
        if not os.path.isdir(os.path.join(mod_dir, chapter)):
            raise AddError(f"no chapter {module}/{chapter}")
        if code is not None or blurb is not None:
            raise AddError("a chapter only has a title and a folder to edit")
        if folder is not None:
            check_slug(folder, "chapter folder")
            if os.path.exists(os.path.join(mod_dir, folder)):
                raise AddError(f"{module}/{folder} already exists")
    elif folder is not None:
        check_module(folder)
        if os.path.exists(os.path.join(MODULES, folder)):
            raise AddError(f"module {folder} already exists")
    if folder is None and all(v is None for v in fields.values()):
        raise AddError("nothing to edit")
    return fields, folder


def edit_meta(module, chapter=None, code=None, title=None, blurb=None, folder=None):
    """Edit module.json text (a module's code, title and blurb, or a chapter's title) and optionally
    rename the chapter's or module's folder. Only the blurb may be emptied. A rename changes the
    page URLs and the keys of saved answers, so deploy/ingest.py moves the answers in the same job.
    Returns what changed ('' for nothing)."""
    fields, folder = check_edit(module, chapter, code, title, blurb, folder)
    changed = []
    if folder is not None and chapter is None:
        os.rename(os.path.join(MODULES, module), os.path.join(MODULES, folder))
        changed.append(f"folder {module} → {folder}")
        module = folder
    mod_dir = os.path.join(MODULES, module)
    set_meta(module, chapter)  # makes sure module.json exists
    path = os.path.join(mod_dir, "module.json")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    if chapter is not None:
        chapters = meta.setdefault("chapters", {})
        if folder is not None:
            os.rename(os.path.join(mod_dir, chapter), os.path.join(mod_dir, folder))
            # same position in module.json, new key
            meta["chapters"] = chapters = {(folder if k == chapter else k): v for k, v in chapters.items()}
            changed.append(f"folder {chapter} → {folder}")
            chapter = folder
        if fields["title"] is not None and chapters.get(chapter) != fields["title"]:
            chapters[chapter] = fields["title"]
            changed.append("title")
    else:
        for key, value in fields.items():
            if value is not None and meta.get(key, "") != value:
                meta[key] = value
                changed.append(key)
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return ", ".join(changed)


def build():
    """Run build.py. Returns (stdout, warnings)."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "build.py")], capture_output=True, text=True)
    if r.returncode != 0:
        raise AddError(f"build failed: {(r.stderr or r.stdout).strip()}")
    warnings = [line[len("warning: "):] for line in r.stderr.splitlines() if line.startswith("warning: ")]
    return r.stdout.strip(), warnings


def has_upstream():
    return subprocess.run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "@{u}"],
                          capture_output=True).returncode == 0


def sync():
    """Pull first, so this machine and the server never push over each other."""
    if has_upstream():
        git("pull", "-q", "--rebase", "--autostash")


def commit_and_push(paths, message, push=True, ident=None):
    """Commit paths; push (rebasing once if the remote moved).
    Returns 'unchanged', 'committed', 'pushed' or 'push-failed' (the commit stays local)."""
    git("add", "-A", "--", *paths)  # -A also stages deletions
    if subprocess.run(["git", "-C", ROOT, "diff", "--cached", "--quiet"]).returncode == 0:
        return "unchanged"
    who = ["-c", f"user.name={ident[0]}", "-c", f"user.email={ident[1]}"] if ident else []
    git(*who, "commit", "-q", "-m", message)
    if not push or not has_upstream():
        return "committed"
    try:
        git("push", "-q")
    except AddError:
        try:
            git("pull", "-q", "--rebase", "--autostash")
            git("push", "-q")
        except AddError:
            return "push-failed"
    return "pushed"


def main():
    ap = argparse.ArgumentParser(description="Add or update a chapter, then commit and push.")
    ap.add_argument("module", help="module folder, e.g. thor")
    ap.add_argument("chapter", help="chapter folder, e.g. ch2 or ch1-2")
    ap.add_argument("files", nargs="*", help="remakes (.html) and course PDFs")
    ap.add_argument("--td", nargs="+", default=[], metavar="FILE", help="exercise sheets for td/")
    ap.add_argument("--title", help="chapter title, stored in module.json")
    ap.add_argument("--no-push", action="store_true", help="commit but don't push")
    a = ap.parse_args()

    try:
        check_module(a.module)
        check_slug(a.chapter, "chapter")
        if not a.files and not a.td and not a.title:
            raise AddError("nothing to add")
        jobs = [(src, kind_of(src)) for src in a.files] + [(src, "td") for src in a.td]
        html = [k for _, k in jobs if k in ("lesson", "practice")]
        if len(html) != len(set(html)):
            raise AddError("two files would become the same lesson.html or practice.html")
        for src, _ in jobs:
            if not os.path.isfile(src):
                raise AddError(f"no such file: {src}")

        sync()
        for src, kind in jobs:
            rel, replaced = place(a.module, a.chapter, kind, src)
            print(f"{'updated' if replaced else 'added'}  modules/{a.module}/{a.chapter}/{rel}")
        if set_meta(a.module, a.chapter, a.title):
            print(f"new module: fill in title and blurb in modules/{a.module}/module.json")
        with open(os.path.join(MODULES, a.module, "module.json"), encoding="utf-8") as f:
            if a.chapter not in json.load(f).get("chapters", {}):
                print(f"note: no title for {a.chapter}; pass --title to set one")

        out, warnings = build()  # the build lints every page; read its warnings before the push
        print(out)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)

        msg = f"{a.module.upper()} {a.chapter}: {', '.join(html) or 'update'}"
        state = commit_and_push([os.path.join("modules", a.module)], msg, push=not a.no_push)
        print({"unchanged": "nothing changed", "committed": "committed, not pushed",
               "pushed": "pushed; live within 5 minutes",
               "push-failed": "committed, but the push failed; run git push"}[state])
    except AddError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
