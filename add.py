#!/usr/bin/env python3
"""Add or update a chapter, check it, commit and push. Python 3 stdlib only.

    python3 add.py <module> <chapter> FILE... [--title "Chapter title"] [--td FILE...] [--no-push]

FILE can be a remake (*.html: "practice" in the name -> practice.html, otherwise lesson.html)
or a course PDF (-> cours/). --td files go to td/. A new module gets a module.json to edit.
The ThinkPad picks the push up within a few minutes (deploy/update.sh).

    python3 add.py thor ch2 ~/dl/lesson.html ~/dl/practice.html ~/dl/2-methodes.pdf --title "Methods"
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(ROOT, "modules")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,99}$")


def die(msg):
    sys.exit(f"error: {msg}")


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], check=True)


def target_name(path):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if ext == ".html":
        return "practice.html" if "practice" in name.lower() else "lesson.html"
    if ext == ".pdf":
        return os.path.join("cours", name)
    die(f"don't know where to put {name} (expected .html or .pdf)")


def main():
    ap = argparse.ArgumentParser(description="Add or update a chapter, then commit and push.")
    ap.add_argument("module", help="module folder, e.g. thor")
    ap.add_argument("chapter", help="chapter folder, e.g. ch2 or ch1-2")
    ap.add_argument("files", nargs="*", help="remakes (.html) and course PDFs")
    ap.add_argument("--td", nargs="+", default=[], metavar="FILE", help="exercise sheets for td/")
    ap.add_argument("--title", help="chapter title, stored in module.json")
    ap.add_argument("--no-push", action="store_true", help="commit but don't push")
    a = ap.parse_args()

    for name in (a.module, a.chapter):
        if not NAME_RE.match(name):
            die(f"{name!r}: use lowercase letters, digits, '-' and '.'")
    if not a.files and not a.td and not a.title:
        die("nothing to add")

    moves = [(src, target_name(src)) for src in a.files]
    moves += [(src, os.path.join("td", os.path.basename(src))) for src in a.td]
    targets = [t for _, t in moves]
    for t in set(targets):
        if targets.count(t) > 1:
            die(f"two files would become {t}")
    for src, _ in moves:
        if not os.path.isfile(src):
            die(f"no such file: {src}")

    mod_dir = os.path.join(MODULES, a.module)
    ch_dir = os.path.join(mod_dir, a.chapter)
    os.makedirs(os.path.join(ch_dir, "cours"), exist_ok=True)
    os.makedirs(os.path.join(ch_dir, "td"), exist_ok=True)

    for src, rel in moves:
        dst = os.path.join(ch_dir, rel)
        print(f"{'updated' if os.path.exists(dst) else 'added'}  {os.path.relpath(dst, ROOT)}")
        shutil.copyfile(src, dst)
    if not os.listdir(os.path.join(ch_dir, "td")):
        open(os.path.join(ch_dir, "td", ".gitkeep"), "a").close()

    meta_path = os.path.join(mod_dir, "module.json")
    new_module = not os.path.exists(meta_path)
    meta = {"code": a.module.upper(), "title": a.module.upper(), "blurb": "", "chapters": {}}
    if not new_module:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    chapters = meta.setdefault("chapters", {})
    if a.title:
        chapters[a.chapter] = a.title
    if new_module or a.title:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
    if new_module:
        print(f"new module: fill in title and blurb in {os.path.relpath(meta_path, ROOT)}")
    if a.chapter not in chapters:
        print(f"note: no title for {a.chapter}; pass --title to set one")

    # The build lints every page; read its warnings before the push.
    subprocess.run([sys.executable, os.path.join(ROOT, "build.py")], check=True)

    git("add", os.path.relpath(mod_dir, ROOT))
    if subprocess.run(["git", "-C", ROOT, "diff", "--cached", "--quiet"]).returncode == 0:
        print("nothing changed")
        return
    pages = ", ".join(os.path.splitext(os.path.basename(t))[0] for t in targets if t.endswith(".html"))
    git("commit", "-q", "-m", f"{a.module.upper()} {a.chapter}: {pages or 'update'}")
    if a.no_push:
        print("committed, not pushed")
    else:
        git("push", "-q")
        print("pushed; live within 5 minutes")


if __name__ == "__main__":
    main()
