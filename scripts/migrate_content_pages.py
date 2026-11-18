#!/usr/bin/env python3
"""Migrate content-bearing hand-written course pages into the
course × teacher × semester structure.

Every page listed below gets one offering on a placeholder semester
(待考据) because the pages carry no reliable semester evidence. Content
(assessment, textbooks, hours) is carried over verbatim; image links are
normalised for the deeper page location. Courses whose teacher is unknown
use a 教师待补充 placeholder.

Idempotent: existing (course, teacher, semester) offerings are skipped.
Stray duplicate pages (same course code in a second category directory)
are merged into the canonical copy and removed.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_existing import (  # noqa: E402
    get_db, get_or_create_teacher, get_or_create_semester,
    normalize_image_paths, parse_first_field_table, parse_textbook_list,
    parse_weekly_table, split_sections,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(BASE, "docs", "categories")
PLACEHOLDER_SEMESTER = "待考据"
PLACEHOLDER_TEACHER = "教师待补充"

# code -> (teachers, page dirs in priority order)
MIGRATIONS = {
    "ENG631": (["李啸初"], ["basic-elective"]),
    "ENG366": (["李若珊"], ["major-direction"]),
    "ENG450": (["石小军"], ["major-direction"]),
    "ENG519": (["付涛"], ["major-direction"]),
    "ENG798": (["马欣欣"], ["major-direction"]),
    "ENG817": (["史兴松"], ["basic-elective", "major-direction"]),
    "ENG818": (["付涛"], ["major-direction"]),
    "ENG821": (["董琳"], ["major-direction"]),
    "ENG824": ([PLACEHOLDER_TEACHER], ["major-direction"]),
    "ENG833": (["郭巍"], ["major-direction"]),
    "ENG837": (["石小军"], ["major-direction"]),
    "ENG845": ([PLACEHOLDER_TEACHER], ["major-direction"]),
    "ENG819": (["李晨乐"], ["basic-elective", "major-direction"]),
    "ENG822": (["张东冰", "赵丹彤"], ["major-direction"]),
}

# courses that only have an empty skeleton duplicated in a wrong category dir
STRAYS_ONLY = ["ENG360", "ENG361", "ENG470", "ENG628", "ENG823", "ENG827"]

PLACEHOLDER_VALUES = {"", "待补充", "待补充。", "—", "-", "／"}


def real(text):
    return bool(text) and text.strip() not in PLACEHOLDER_VALUES


def read_page(code, dir_name):
    return normalize_image_paths(open(os.path.join(DOCS, dir_name, f"{code}.md"),
                                      encoding="utf-8").read())


def parse_hours(text):
    text = (text or "").strip().replace("／", "/")
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d+)$", text)
    if m:
        return int(m.group(1)), None
    return None, None


def textbook_entries(section_text):
    entries = parse_textbook_list(section_text)
    if entries:
        return entries
    if not real(section_text):
        return []
    blocks = [re.sub(r"\s*\n\s*", " ", b).strip()
              for b in re.split(r"\n\s*\n", section_text.strip()) if b.strip()]
    return [("参考书", b) for b in blocks]


def main():
    conn = get_db()
    semester_id = get_or_create_semester(conn, PLACEHOLDER_SEMESTER)
    created = 0

    for code, (teachers, dirs) in MIGRATIONS.items():
        course = conn.execute("SELECT id FROM courses WHERE code=?", (code,)).fetchone()
        if not course:
            print(f"  !! {code} not in DB, skipped")
            continue

        hours_total = hours_weekly = weeks = None
        assessment = None
        info_source = ""
        updated_at = None
        textbooks = []

        for dir_name in dirs:
            text = read_page(code, dir_name)
            fields = parse_first_field_table(text)
            sections = split_sections(text)
            if hours_total is None:
                hours_total, hours_weekly = parse_hours(fields.get("总课时 / 周课时", ""))
            if weeks is None and real(fields.get("教学周数", "")):
                try:
                    weeks = int(re.sub(r"\D", "", fields.get("教学周数", "")))
                except ValueError:
                    pass
            if assessment is None and real(sections.get("考核方式", "")):
                assessment = sections.get("考核方式", "").strip()
            if not textbooks:
                textbooks = textbook_entries(sections.get("教材及参考资料", ""))
            m = re.search(r"信息来源：([^\n*]+)", text)
            if m and not info_source:
                info_source = m.group(1).strip()
            m = re.search(r"最后更新：(\d{4}-\d{2}-\d{2})", text)
            if m and not updated_at:
                updated_at = m.group(1)

        info_source = info_source or "2023 级培养方案"
        updated_at = updated_at or "2026-07-01"

        for teacher_name in teachers:
            teacher_id = get_or_create_teacher(conn, teacher_name)
            exists = conn.execute(
                """SELECT id FROM course_offerings
                   WHERE course_id=? AND teacher_id=? AND semester_id=?""",
                (course["id"], teacher_id, semester_id),
            ).fetchone()
            if exists:
                print(f"  = {code} {teacher_name}: already migrated")
                continue
            cur = conn.execute(
                """INSERT INTO course_offerings
                   (course_id, teacher_id, semester_id, total_hours, weekly_hours,
                    teaching_weeks, assessment_method, info_source, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (course["id"], teacher_id, semester_id, hours_total, hours_weekly,
                 weeks, assessment, info_source, updated_at),
            )
            offering_id = cur.lastrowid
            for i, (btype, desc) in enumerate(textbooks):
                conn.execute(
                    """INSERT INTO textbooks (offering_id, type, description, sort_order)
                       VALUES (?, ?, ?, ?)""",
                    (offering_id, btype, desc, i),
                )
            created += 1
            print(f"  + {code} {teacher_name} -> offering {offering_id}"
                  f" (考核 {len(assessment or '')} 字, 教材 {len(textbooks)} 条)")

    # stray duplicate pages: always keep the copy matching the DB category
    codes = list(MIGRATIONS) + STRAYS_ONLY
    for code in codes:
        course = conn.execute("SELECT category FROM courses WHERE code=?", (code,)).fetchone()
        if not course:
            continue
        canon_dir = {"基础必修": "basic-required", "基础选修": "basic-elective",
                     "专业方向课": "major-direction", "实验课": "lab"}[course["category"]]
        if not os.path.exists(os.path.join(DOCS, canon_dir, f"{code}.md")):
            print(f"  !! {code}: canonical page missing in {canon_dir}, strays left alone")
            continue
        for dir_name in ("basic-required", "basic-elective", "major-direction", "lab"):
            path = os.path.join(DOCS, dir_name, f"{code}.md")
            if dir_name != canon_dir and os.path.exists(path):
                os.remove(path)
                print(f"  - removed stray {dir_name}/{code}.md")

    conn.commit()
    conn.close()
    print(f"migrate_content_pages: {created} offerings created")


if __name__ == "__main__":
    main()
