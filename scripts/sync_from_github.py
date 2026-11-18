#!/usr/bin/env python3
"""Pull GitHub main, sync markdown edits into the DB, rebuild and deploy.

Triggered by the GitHub webhook (admin/app.py → /webhook/github) and safe
to run manually. Uses a lock file so overlapping runs are skipped.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
GIT = os.environ.get("COURSEPLAN_GIT_BIN", "git")
LOCK = os.path.join(BASE, ".sync.lock")
LOCK_STALE_SECONDS = 900


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=BASE)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        print(out)
    if check and r.returncode != 0:
        raise SystemExit(f"step failed ({r.returncode}): {' '.join(cmd)}")
    return r


def run_with_retry(cmd, attempts=3, delay=5):
    for i in range(attempts):
        r = run(cmd, check=False)
        if r.returncode == 0:
            return r
        print(f"  attempt {i + 1}/{attempts} failed, retrying in {delay}s")
        time.sleep(delay)
    raise SystemExit(f"step failed after {attempts} attempts: {' '.join(cmd)}")


def git_out(*args):
    r = subprocess.run([GIT, *args], capture_output=True, text=True, cwd=BASE)
    return (r.stdout or "").strip()


def acquire_lock():
    if os.path.exists(LOCK):
        if time.time() - os.path.getmtime(LOCK) < LOCK_STALE_SECONDS:
            print("sync already running, skipping")
            return False
        os.remove(LOCK)
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def main():
    if not acquire_lock():
        return

    try:
        run_with_retry([GIT, "fetch", "origin", "main"])

        behind = git_out("rev-list", "--count", "HEAD..origin/main")
        ahead = git_out("rev-list", "--count", "origin/main..HEAD")
        behind = int(behind or 0)
        ahead = int(ahead or 0)

        if behind == 0 and ahead == 0:
            print("already up to date")
            return

        if ahead > 0:
            # local commits (e.g. an earlier publish whose push failed)
            try:
                run_with_retry([GIT, "push", "origin", "main"])
            except SystemExit:
                pass

        if behind > 0:
            if ahead > 0:
                r = run([GIT, "rebase", "origin/main"], check=False)
                if r.returncode != 0:
                    run([GIT, "rebase", "--abort"], check=False)
                    run([GIT, "reset", "--hard", "origin/main"])
            else:
                run([GIT, "reset", "--hard", "origin/main"])

            # restart the panel when the code it runs changed
            old_head = git_out("rev-parse", "ORIG_HEAD") or git_out("rev-parse", "HEAD~1")
            code_changed = git_out("diff", "--name-only", old_head, "HEAD", "--", "admin", "scripts")
            if code_changed and os.environ.get("COURSEPLAN_RESTART_PANEL") == "1":
                run(["sudo", "-n", "systemctl", "restart", "notebook-admin"], check=False)

            # 1. md edits from GitHub → DB
            run([PY, os.path.join(BASE, "scripts", "sync_from_files.py")])
            # 2. DB → md (normalizes the working tree to match the DB)
            run([PY, os.path.join(BASE, "scripts", "export_courses.py")])
            # 3. rebuild + deploy
            run([PY, "-m", "mkdocs", "build"])
            target = os.environ.get("COURSEPLAN_PUBLISH_TARGET", "")
            if target:
                run(["rsync", "-a", "--delete",
                     os.path.join(BASE, "site") + "/", target])
            print("sync_from_github: done")
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    main()
