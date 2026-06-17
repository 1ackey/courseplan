#!/usr/bin/env python3
"""Export course data from SQLite database to MkDocs Markdown files."""
import os
import re
import sqlite3
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "courseplan.db")
DOCS_DIR = os.path.join(BASE_DIR, "docs", "categories")
TEACHERS_DIR = os.path.join(BASE_DIR, "docs", "teachers")
MKCONFIG = os.path.join(BASE_DIR, "mkdocs.yml")

CATEGORY_DIRS = {
    "基础必修": "basic-required",
    "基础选修": "basic-elective",
    "专业方向课": "major-direction",
    "实验课": "lab",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_course_markdown(course, offerings, conn):
    """Build markdown for a single course page with all its offerings."""
    code = course["code"]
    name = course["name"]
    category = course["category"]

    # If no offerings, generate a placeholder page
    if not offerings:
        return f"""---
title: {name}
---

# {name}

| 字段 | 内容 |
|------|------|
| 课程代码 | {code} |
| 课程类别 | {category} |
| 任课教师 | 待补充 |
| 开课学院 | {course['department'] or '英语学院'} |
| 总课时 / 周课时 | 待补充 |
| 教学周数 | 待补充 |

## 考核方式

待补充。

## 教材及参考资料

待补充。

## 教学进度

待补充。

---

*最后更新：2026-06-17 · 信息来源：2023 级培养方案*
"""

    lines = [
        f"---",
        f"title: {name}",
        f"---",
        f"",
        f"# {name}",
        f"",
    ]

    # Show summary of all offerings at top
    lines.append("## 开课记录")
    lines.append("")
    lines.append("| 学期 | 任课教师 | 考核方式 |")
    lines.append("|------|----------|----------|")
    for o in offerings:
        assessment_preview = (o["assessment_method"] or "待补充")[:40]
        lines.append(f"| {o['semester_name']} | {o['teacher_name']} | {assessment_preview} |")
    lines.append("")

    # Primary offering (most recent) gets detailed display
    primary = offerings[0]

    lines.extend([
        "",
        "## 课程信息",
        "",
        "| 字段 | 内容 |",
        "|------|------|",
        f"| 课程代码 | {code} |",
        f"| 课程类别 | {category} |",
        f"| 开课学院 | {course['department'] or '英语学院'} |",
        f"| 总课时 / 周课时 | {primary['total_hours'] or '/'} / {primary['weekly_hours'] or '/'} |",
        f"| 教学周数 | {primary['teaching_weeks'] or '待补充'} |",
        "",
    ])

    # For each offering, show its details and weekly plan
    for idx, o in enumerate(offerings):
        section_suffix = f"（{o['semester_name']} · {o['teacher_name']}）" if len(offerings) > 1 else ""

        # Assessment method
        lines.append(f"## 考核方式{section_suffix}")
        lines.append("")
        lines.append(o["assessment_method"] or "待补充。")
        lines.append("")

        # Textbooks
        textbooks = conn.execute(
            "SELECT * FROM textbooks WHERE offering_id=? ORDER BY sort_order",
            (o["id"],),
        ).fetchall()
        if textbooks:
            lines.append(f"## 教材及参考资料{section_suffix}")
            lines.append("")
            for tb in textbooks:
                prefix = "教材" if tb["type"] == "教材" else "参考书"
                lines.append(f"- [{prefix}] {tb['description']}")
            lines.append("")

        # Weekly plan
        weekly_plans = conn.execute(
            "SELECT * FROM weekly_plans WHERE offering_id=? ORDER BY week_number",
            (o["id"],),
        ).fetchall()
        if weekly_plans:
            lines.append(f"## 教学进度{section_suffix}")
            lines.append("")
            lines.append("| 日期 | 周次 | 课时 | 教学方式 | 内容提要 | 备注 |")
            lines.append("|------|------|------|----------|----------|------|")
            for wp in weekly_plans:
                method = wp["teaching_method"] or ""
                content = wp["content"] or ""
                notes = wp["notes"] or ""
                lines.append(f"| {wp['date']} | {wp['week_number']} | {wp['hours']} | {method} | {content} | {notes} |")
            lines.append("")

    # Footer
    latest = offerings[0]
    lines.extend([
        "---",
        "",
        f"*最后更新：{latest['updated_at']} · 信息来源：{latest['info_source'] or '2023 级培养方案'}*",
        "",
    ])

    return "\n".join(lines)


def build_category_index(category, dir_name, conn):
    """Build index page for a category."""
    courses = conn.execute(
        "SELECT code, name, subcategory FROM courses WHERE category=? ORDER BY code",
        (category,),
    ).fetchall()

    # Get teachers for each course from offerings
    teacher_map = {}
    offerings = conn.execute("""
        SELECT c.code, t.name AS teacher_name, s.name AS semester_name
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        ORDER BY s.name DESC
    """).fetchall()
    for o in offerings:
        key = o["code"]
        if key not in teacher_map:
            teacher_map[key] = f"{o['teacher_name']} ({o['semester_name']})"

    lines = [f"# {category}", ""]

    # Group by subcategory if applicable
    subcategories = defaultdict(list)
    for c in courses:
        subcategories[c["subcategory"] or ""].append(c)

    for subcat, items in subcategories.items():
        if subcat:
            lines.append(f"## {subcat}")
            lines.append("")
        for c in items:
            teacher = teacher_map.get(c["code"], "待补充")
            lines.append(f"- [{c['name']} `{c['code']}`]({c['code']}.md) · {teacher}")
        lines.append("")

    return "\n".join(lines)


def build_teacher_index(conn):
    """Build teacher index page."""
    teachers = conn.execute("""
        SELECT DISTINCT t.id, t.name, t.department, t.title
        FROM teachers t
        JOIN course_offerings co ON co.teacher_id = t.id
        ORDER BY t.name
    """).fetchall()

    lines = ["# 教师索引", ""]
    for t in teachers:
        lines.append(f"## {t['name']}")
        if t["title"] or t["department"]:
            parts = [p for p in [t["title"], t["department"]] if p]
            lines.append(f"*{' · '.join(parts)}*")
        lines.append("")

        courses = conn.execute("""
            SELECT DISTINCT c.code, c.name, s.name AS semester_name
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            JOIN semesters s ON co.semester_id = s.id
            WHERE co.teacher_id = ?
            ORDER BY s.name DESC, c.code
        """, (t["id"],)).fetchall()

        for c in courses:
            cat_courses = conn.execute(
                "SELECT category FROM courses WHERE code=?", (c["code"],)
            ).fetchone()
            if cat_courses:
                cat_dir = CATEGORY_DIRS.get(cat_courses["category"], "other")
                lines.append(f"- [{c['name']} `{c['code']}`](../categories/{cat_dir}/{c['code']}.md) · {c['semester_name']}")
        lines.append("")

    if not teachers:
        lines.append("暂无教师数据。")
        lines.append("")

    return "\n".join(lines)


def update_mkdocs_nav(conn):
    """Update mkdocs.yml nav section with all course files."""
    courses = conn.execute("SELECT code, name, category FROM courses ORDER BY code").fetchall()

    # Build nav lines for each category
    cat_order = ["基础必修", "基础选修", "专业方向课", "实验课"]
    nav_sections = []

    for cat in cat_order:
        cat_courses = [c for c in courses if c["category"] == cat]
        dir_name = CATEGORY_DIRS[cat]
        lines = []
        lines.append(f"  - {cat}:")
        lines.append(f"      - categories/{dir_name}/index.md")
        for c in cat_courses:
            title = f"{c['code']} {c['name']}"
            lines.append(f"      - {title}: categories/{dir_name}/{c['code']}.md")
        nav_sections.append("\n".join(lines))

    nav_block = "\n".join(nav_sections)

    # Read current mkdocs.yml and replace nav section
    with open(MKCONFIG, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace from "nav:" to end of file
    new_nav = f"""nav:
  - 首页: index.md
{nav_block}
  - 教师索引: teachers/index.md
  - 贡献指南: contributing.md
  - 关于本站: about.md"""

    content = re.sub(r"^nav:.*", new_nav, content, flags=re.DOTALL)

    with open(MKCONFIG, "w", encoding="utf-8") as f:
        f.write(content)

    print("  mkdocs.yml nav updated")


def export_courses():
    conn = get_db()

    offerings = conn.execute("""
        SELECT co.*, c.code, c.name AS course_name, c.category, c.subcategory, c.department,
               t.name AS teacher_name, s.name AS semester_name, s.academic_year, s.term
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        ORDER BY s.name DESC, c.code
    """).fetchall()

    course_offerings = defaultdict(list)
    for o in offerings:
        course_offerings[o["code"]].append(o)

    all_courses = conn.execute("SELECT * FROM courses ORDER BY code").fetchall()

    generated = 0

    for course in all_courses:
        code = course["code"]
        category = course["category"]
        dir_name = CATEGORY_DIRS.get(category, "other")
        dir_path = os.path.join(DOCS_DIR, dir_name)
        os.makedirs(dir_path, exist_ok=True)

        offerings_for_course = course_offerings.get(code, [])
        content = build_course_markdown(course, offerings_for_course, conn)

        filepath = os.path.join(dir_path, f"{code}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        generated += 1

    for category, dir_name in CATEGORY_DIRS.items():
        dir_path = os.path.join(DOCS_DIR, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        index_content = build_category_index(category, dir_name, conn)
        with open(os.path.join(dir_path, "index.md"), "w", encoding="utf-8") as f:
            f.write(index_content)

    os.makedirs(TEACHERS_DIR, exist_ok=True)
    teacher_content = build_teacher_index(conn)
    with open(os.path.join(TEACHERS_DIR, "index.md"), "w", encoding="utf-8") as f:
        f.write(teacher_content)

    update_mkdocs_nav(conn)

    conn.close()
    print(f"\nTotal: {generated} course files + index files + nav updated.\n")


if __name__ == "__main__":
    export_courses()
