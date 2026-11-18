#!/usr/bin/env python3
"""Sync edits made directly in Markdown files (GitHub web UI, local editor)
back into the SQLite database, so that the DB stays the single source of
truth while the repo remains the sync hub.

Covers both layouts:
- generated per-offering pages  docs/categories/<dir>/<CODE>/o<id>-*.md
- hand-written flat pages       docs/categories/<dir>/<CODE>.md

Everything is upsert-based and idempotent; safe to run on every pull.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_existing import (  # noqa: E402
    DB_PATH,
    DOCS_DIR,
    CATEGORY_DIRS,
    get_db,
    parse_first_field_table,
    parse_weekly_table,
    parse_textbook_list,
    split_sections,
    get_or_create_teacher,
    get_or_create_semester,
)


def parse_offering_page(text):
    """Parse a generated (or legacy) page into offering data."""
    fields = parse_first_field_table(text)
    sections = split_sections(text)

    assessment = sections.get("考核方式", "").strip() or None
    plans = parse_weekly_table(sections.get("教学进度", ""))
    books = parse_textbook_list(sections.get("教材及参考资料", ""))

    hours = fields.get("总课时 / 周课时", "") or fields.get("总课时/周课时", "") or ""
    total_hours = weekly_hours = teaching_weeks = None
    hm = re.match(r"^(\d+)\s*/\s*(\d+)$", hours.replace("／", "/"))
    if hm:
        total_hours, weekly_hours = int(hm.group(1)), int(hm.group(2))
    wm = fields.get("教学周数", "")
    if wm and wm != "待补充":
        try:
            teaching_weeks = int(wm)
        except ValueError:
            teaching_weeks = None

    updated_at = None
    m = re.search(r"最后更新：(\d{4}-\d{2}-\d{2})", text)
    if m:
        updated_at = m.group(1)
    info_source = None
    m = re.search(r"信息来源：([^\n*]+)", text)
    if m:
        info_source = m.group(1).strip().rstrip("*").strip()

    return {
        "code": fields.get("课程代码", "").strip(),
        "teacher": fields.get("任课教师", "").strip(),
        "semester": fields.get("学期", "").strip(),
        "total_hours": total_hours,
        "weekly_hours": weekly_hours,
        "teaching_weeks": teaching_weeks,
        "assessment_method": assessment,
        "info_source": info_source,
        "updated_at": updated_at,
        "textbooks": books,
        "weekly_plans": plans,
    }


def ensure_course(conn, code, dir_name, text):
    row = conn.execute("SELECT id FROM courses WHERE code=?", (code,)).fetchone()
    if row:
        return row["id"]
    tm = re.match(r"^---\n.*?^title:\s*(.+?)$", text, flags=re.MULTILINE | re.DOTALL)
    name = tm.group(1).strip() if tm else code
    cur = conn.execute(
        "INSERT INTO courses (code, name, category, subcategory, department) VALUES (?, ?, ?, NULL, '英语学院')",
        (code, name, CATEGORY_DIRS.get(dir_name, "")),
    )
    return cur.lastrowid


def replace_children(conn, offering_id, data):
    conn.execute("DELETE FROM textbooks WHERE offering_id=?", (offering_id,))
    conn.execute("DELETE FROM weekly_plans WHERE offering_id=?", (offering_id,))
    for i, (btype, desc) in enumerate(data["textbooks"]):
        conn.execute(
            "INSERT INTO textbooks (offering_id, type, description, sort_order) VALUES (?, ?, ?, ?)",
            (offering_id, btype, desc, i),
        )
    for p in data["weekly_plans"]:
        conn.execute(
            """INSERT INTO weekly_plans
               (offering_id, week_number, date, hours, teaching_method, content, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (offering_id, p["week_number"], p["date"], p["hours"],
             p["teaching_method"], p["content"], p["notes"]),
        )


def upsert_offering(conn, data, dir_name, offering_id_hint=None):
    code = data["code"]
    teacher = data["teacher"]
    semester = data["semester"]
    if not code or not teacher or teacher in ("待补充", "—", "-") or not semester:
        return None

    course_id = ensure_course(conn, code, dir_name, "")
    teacher_id = get_or_create_teacher(conn, teacher)
    semester_id = get_or_create_semester(conn, semester)
    if not semester_id:
        return None

    row = None
    if offering_id_hint:
        row = conn.execute(
            "SELECT * FROM course_offerings WHERE id=?", (offering_id_hint,)
        ).fetchone()
        if row and (row["course_id"] != course_id or row["teacher_id"] != teacher_id
                    or row["semester_id"] != semester_id):
            row = None  # stale id in filename, fall back to matching
    if not row:
        row = conn.execute(
            """SELECT * FROM course_offerings
               WHERE course_id=? AND teacher_id=? AND semester_id=?""",
            (course_id, teacher_id, semester_id),
        ).fetchone()

    if row:
        oid = row["id"]
        conn.execute(
            """UPDATE course_offerings
               SET total_hours=?, weekly_hours=?, teaching_weeks=?, assessment_method=?,
                   info_source=?, updated_at=COALESCE(?, updated_at)
               WHERE id=?""",
            (data["total_hours"], data["weekly_hours"], data["teaching_weeks"],
             data["assessment_method"], data["info_source"], data["updated_at"], oid),
        )
    else:
        cur = conn.execute(
            """INSERT INTO course_offerings
               (course_id, teacher_id, semester_id, total_hours, weekly_hours,
                teaching_weeks, assessment_method, info_source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (course_id, teacher_id, semester_id, data["total_hours"],
             data["weekly_hours"], data["teaching_weeks"], data["assessment_method"],
             data["info_source"], data["updated_at"]),
        )
        oid = cur.lastrowid

    replace_children(conn, oid, data)
    return oid


def sync_all():
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO site_settings (key, value) VALUES ('management_mode', '1')")
    conn.commit()

    updated = 0
    for dir_name in sorted(os.listdir(DOCS_DIR)):
        dir_path = os.path.join(DOCS_DIR, dir_name)
        if not os.path.isdir(dir_path):
            continue
        for root, _dirs, files in os.walk(dir_path):
            for fname in sorted(files):
                if not fname.endswith(".md") or fname == "index.md":
                    continue
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()

                hint = None
                if root != dir_path:  # generated per-offering page: o<id>-...
                    m = re.match(r"^o(\d+)-", fname)
                    if m:
                        hint = int(m.group(1))

                data = parse_offering_page(text)
                if hint:
                    data["code"] = data["code"] or os.path.basename(root)
                oid = upsert_offering(conn, data, dir_name, offering_id_hint=hint)
                if oid:
                    updated += 1

    conn.commit()
    conn.close()
    print(f"sync_from_files: {updated} offerings synced from markdown")


if __name__ == "__main__":
    sync_all()
