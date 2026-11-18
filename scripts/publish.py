#!/usr/bin/env python3
"""Build and publish the site. Steps are controlled by environment variables:

- COURSEPLAN_PUBLISH_TARGET  rsync target (e.g. /var/www/jackeywiki/slides/notebook).
                             Empty/unset → skip deployment, build only.
- COURSEPLAN_PUBLISH_GIT     "1" → commit docs changes and push to GitHub main.
- COURSEPLAN_GIT_BIN         git binary (default: git)

Run from the repo root by the admin panel (`admin/app.py → /publish`).
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
GIT = os.environ.get("COURSEPLAN_GIT_BIN", "git")


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=BASE, **kw)
    out = (r.stdout or "").strip()
    if out:
        print(out)
    if r.returncode != 0:
        sys.stderr.write((r.stderr or "").strip() + "\n")
        raise SystemExit(f"step failed ({r.returncode}): {' '.join(cmd)}")
    return r


def main():
    # 1. regenerate markdown from the database
    run([PY, os.path.join(BASE, "scripts", "export_courses.py")])

    # 2. build the static site
    run([PY, "-m", "mkdocs", "build"])

    # 3. deploy to the web root
    target = os.environ.get("COURSEPLAN_PUBLISH_TARGET", "")
    if target:
        run(["rsync", "-a", "--delete",
             os.path.join(BASE, "site") + "/", target])
        print(f"deployed to {target}")
    else:
        print("PUBLISH_TARGET not set, skipped deploy")

    # 4. commit & push to GitHub so the repo stays in sync with the site
    if os.environ.get("COURSEPLAN_PUBLISH_GIT") == "1":
        dirty = subprocess.run(
            [GIT, "status", "--porcelain", "--", "docs", "mkdocs.yml"],
            capture_output=True, text=True, cwd=BASE,
        ).stdout.strip()
        if dirty:
            run([GIT, "add", "-A", "--", "docs", "mkdocs.yml"])
            run([GIT, "commit", "-m", "publish: update course pages (auto)"])
            run([GIT, "push", "origin", "main"])
            print("pushed to GitHub")
        else:
            print("no content changes, skipped git commit")
    else:
        print("PUBLISH_GIT not set, skipped git push")

    print("publish: done")


if __name__ == "__main__":
    main()
