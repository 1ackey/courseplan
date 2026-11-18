#!/usr/bin/env python3
"""One-off migration: import existing hand-written course pages into the DB.

Parses docs/categories/<dir>/<CODE>.md files and creates offerings
(teacher × semester) plus textbooks and weekly plans, so that the
export script can regenerate them as per-offering pages.

Rules:
- A page is migrated only if a teacher name can be determined
  (field table "任课教师" or the 开课记录 table).
- Courses that already have offerings in the DB are skipped.
- Semester is taken from the 开课记录 table, or inferred from weekly
  plan dates (Sep-Dec → term 1, Mar-Jun → term 2) and the footer's
  最后更新 year.
"""
import os
import re
import sqlite3
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "courseplan.db")
DOCS_DIR = os.path.join(BASE_DIR, "docs", "categories")

CATEGORY_DIRS = {
    "basic-required": "基础必修",
    "basic-elective": "基础选修",
    "major-direction": "专业方向课",
    "lab": "实验课",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def parse_field_table(section_text):
    fields = {}
    for line in section_text.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if key in ("字段", "---", "---:") or key.startswith("-") or val.startswith("-"):
            continue
        fields[key] = val
    return fields


def parse_first_field_table(text):
    """Find the first markdown table whose header starts with 字段 (it may sit
    directly under the H1 without its own ## heading)."""
    blocks = []
    cur = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            cur.append(s)
        else:
            if cur:
                blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    for block in blocks:
        if len(block) < 2:
            continue
        header = [p.strip() for p in block[0].strip("|").split("|")]
        if header and header[0] == "字段":
            fields = {}
            for row in block[1:]:
                parts = [p.strip() for p in row.strip("|").split("|")]
                if len(parts) >= 2 and not set(parts[0]) <= set("- "):
                    fields[parts[0]] = parts[1].strip()
            return fields
    return {}


def parse_opening_table(section_text):
    """Parse 开课记录 rows: | semester | teacher | assessment |"""
    rows = []
    for line in section_text.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 2:
            continue
        semester, teacher = parts[0], parts[1]
        if not semester or semester == "学期" or set(semester) <= {"-", " "}:
            continue
        rows.append((semester, teacher, parts[2] if len(parts) > 2 else ""))
    return rows


def parse_weekly_table(section_text):
    """Parse 教学进度 rows: | date | week | hours | method | content | notes |"""
    plans = []
    for line in section_text.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 6 or not parts[1]:
            continue
        if parts[0] == "日期" or set(parts[1]) <= {"-", " "}:
            continue
        try:
            week = int(parts[1])
        except ValueError:
            continue
        try:
            hours = int(parts[2]) if parts[2] else 2
        except ValueError:
            hours = 2
        plans.append({
            "week_number": week,
            "date": parts[0],
            "hours": hours,
            "teaching_method": parts[3] if len(parts) > 3 else "",
            "content": parts[4] if len(parts) > 4 else "",
            "notes": parts[5] if len(parts) > 5 else "",
        })
    return plans


def parse_textbook_list(section_text):
    books = []
    for line in section_text.splitlines():
        m = re.match(r"^-\s*\[(教材|参考书)\]\s*(.+)$", line.strip())
        if m:
            books.append((m.group(1), m.group(2).strip()))
            continue
        m = re.match(r"^-\s+(.+)$", line.strip())
        if m:
            books.append(("参考书", m.group(1).strip()))
    return books


def split_sections(md_text):
    """Split markdown body into {heading: text}."""
    sections = {}
    current = None
    buf = []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf)
            current = m.group(1).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def infer_semester(plans, footer_year):
    """Infer (semester_name, academic_year) from weekly dates + footer year."""
    if not plans or not footer_year:
        return None
    months = []
    for p in plans:
        m = re.match(r"^(\d{1,2})\.\d+", p["date"] or "")
        if m:
            months.append(int(m.group(1)))
    if not months:
        return None
    if any(9 <= m <= 12 for m in months):
        term = 1
    elif any(1 <= m <= 7 for m in months):
        term = 2
    else:
        return None
    ay = f"{footer_year - 1}-{footer_year}"
    return (f"{ay}-{term}", ay, term)


def get_or_create_teacher(conn, name):
    row = conn.execute("SELECT id FROM teachers WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO teachers (name, department) VALUES (?, '英语学院')", (name,)
    )
    return cur.lastrowid


def get_or_create_semester(conn, name):
    row = conn.execute("SELECT id FROM semesters WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    m = re.match(r"^(\d{4})-(\d{4})-(\d)$", name)
    if not m:
        return None
    cur = conn.execute(
        "INSERT INTO semesters (name, academic_year, term) VALUES (?, ?, ?)",
        (name, m.group(1) + "-" + m.group(2), int(m.group(3))),
    )
    return cur.lastrowid


def migrate_file(conn, path, code, category):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Already has an offering? skip.
    existing = conn.execute(
        "SELECT id FROM course_offerings WHERE course_id=(SELECT id FROM courses WHERE code=?)",
        (code,),
    ).fetchone()
    if existing:
        return "skipped_existing"

    sections = split_sections(text)
    fields = parse_first_field_table(text)
    if not fields:
        fields = parse_field_table(sections.get("课程信息", ""))

    teacher = fields.get("任课教师", "").strip()
    if not teacher or teacher in ("待补充", "—", "-"):
        teacher = ""
        # try 开课记录 for a named teacher
        for semester_name, row_teacher, _ in parse_opening_table(sections.get("开课记录", "")):
            if row_teacher and row_teacher not in ("待补充", "—", "-"):
                teacher = row_teacher
                break
    if not teacher:
        return "skipped_no_teacher"

    # footer
    m = re.search(r"最后更新：(\d{4})-(\d{2})-(\d{2})", text)
    updated_at = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else date.today().isoformat()
    footer_year = int(m.group(1)) if m else None
    m2 = re.search(r"信息来源：([^\n*]+)", text)
    info_source = m2.group(1).strip().rstrip("*") if m2 else "2023 级培养方案"

    assessment = sections.get("考核方式", "").strip() or None

    weekly_plans = parse_weekly_table(sections.get("教学进度", ""))
    textbooks = parse_textbook_list(sections.get("教材及参考资料", ""))

    # semester
    semester_name = None
    opening_rows = parse_opening_table(sections.get("开课记录", ""))
    for sem, row_teacher, _ in opening_rows:
        if row_teacher == teacher and sem not in ("待补充", "—", "-"):
            semester_name = sem
            break
    if not semester_name:
        for sem, row_teacher, _ in opening_rows:
            if sem not in ("待补充", "—", "-") and re.match(r"^\d{4}-\d{4}-\d$", sem):
                semester_name = sem
                break
    if not semester_name:
        inferred = infer_semester(weekly_plans, footer_year)
        if inferred:
            semester_name, ay, term = inferred
            if not conn.execute("SELECT id FROM semesters WHERE name=?", (semester_name,)).fetchone():
                conn.execute(
                    "INSERT INTO semesters (name, academic_year, term) VALUES (?, ?, ?)",
                    (semester_name, ay, term),
                )
    if not semester_name:
        return "skipped_no_semester"

    hours = fields.get("总课时 / 周课时", "") or ""
    total_hours = weekly_hours = teaching_weeks = None
    hm = re.match(r"^(\d+)\s*/\s*(\d+)$", hours.replace("／", "/"))
    if hm:
        total_hours, weekly_hours = int(hm.group(1)), int(hm.group(2))
    wm = fields.get("教学周数", "")
    if wm and wm not in ("待补充",):
        try:
            teaching_weeks = int(wm)
        except ValueError:
            teaching_weeks = None

    teacher_id = get_or_create_teacher(conn, teacher)
    semester_id = get_or_create_semester(conn, semester_name)
    if not semester_id:
        return "skipped_bad_semester"
    course_row = conn.execute("SELECT id FROM courses WHERE code=?", (code,)).fetchone()
    if not course_row:
        # Course code from a page not yet registered in the DB (e.g. new pages
        # added directly on GitHub). Register it with the page's category.
        tm = re.match(r"^---\n.*?^title:\s*(.+?)$", text, flags=re.MULTILINE | re.DOTALL)
        course_name = tm.group(1).strip() if tm else code
        cat = CATEGORY_DIRS.get(os.path.basename(os.path.dirname(path)), "")
        cur = conn.execute(
            "INSERT INTO courses (code, name, category, subcategory, department) VALUES (?, ?, ?, NULL, '英语学院')",
            (code, course_name, cat),
        )
        course_id = cur.lastrowid
    else:
        course_id = course_row["id"]

    cur = conn.execute(
        """INSERT INTO course_offerings
           (course_id, teacher_id, semester_id, total_hours, weekly_hours,
            teaching_weeks, assessment_method, info_source, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (course_id, teacher_id, semester_id, total_hours, weekly_hours,
         teaching_weeks, assessment, info_source, updated_at),
    )
    offering_id = cur.lastrowid

    for i, (btype, desc) in enumerate(textbooks):
        conn.execute(
            "INSERT INTO textbooks (offering_id, type, description, sort_order) VALUES (?, ?, ?, ?)",
            (offering_id, btype, desc, i),
        )
    for wp in weekly_plans:
        conn.execute(
            """INSERT INTO weekly_plans
               (offering_id, week_number, date, hours, teaching_method, content, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (offering_id, wp["week_number"], wp["date"], wp["hours"],
             wp["teaching_method"], wp["content"], wp["notes"]),
        )

    return f"imported ({teacher} · {semester_name}, {len(weekly_plans)} weeks)"


def main():
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO site_settings (key, value) VALUES ('management_mode', '1')")
    conn.commit()

    migrated = skipped = 0
    for dir_name in sorted(os.listdir(DOCS_DIR)):
        dir_path = os.path.join(DOCS_DIR, dir_name)
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".md") or fname == "index.md":
                continue
            code = os.path.splitext(fname)[0]
            if not re.match(r"^[A-Z]{2,4}\d{3}$", code):
                continue
            result = migrate_file(conn, os.path.join(dir_path, fname), code, CATEGORY_DIRS.get(dir_name))
            if result.startswith("imported"):
                migrated += 1
                print(f"  {code}: {result}")
            else:
                skipped += 1
                print(f"  {code}: {result}")

    conn.commit()
    conn.close()
    print(f"\nMigration done: {migrated} imported, {skipped} skipped.\n")


if __name__ == "__main__":
    main()
