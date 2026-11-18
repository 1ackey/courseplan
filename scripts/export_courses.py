#!/usr/bin/env python3
"""Export course data from SQLite database to MkDocs Markdown files.

Page structure (per-offering, i.e. one teacher in one semester):

    docs/categories/<dir>/<CODE>/index.md                     course overview, links every offering
    docs/categories/<dir>/<CODE>/o<id>-<semester>-<slug>.md   one offering (teacher × semester)

Courses that have NO offerings in the database are left untouched, so
hand-written pages in the repository are preserved until their content
is migrated/entered through the admin panel.
"""
import os
import re
import sqlite3
from collections import defaultdict

try:
    from pypinyin import lazy_pinyin

    def teacher_slug(name):
        s = re.sub(r"[^a-z0-9]+", "-", "".join(lazy_pinyin(name)).lower()).strip("-")
        return s or "teacher"
except ImportError:  # pragma: no cover
    def teacher_slug(name):
        return "teacher"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "courseplan.db")
DOCS_DIR = os.path.join(BASE_DIR, "docs", "categories")
TEACHERS_DIR = os.path.join(BASE_DIR, "docs", "teachers")
MKCONFIG = os.path.join(BASE_DIR, "mkdocs.yml")

# Public edit UI prefix served behind nginx (see deploy docs).
EDIT_BASE = os.environ.get("COURSEPLAN_EDIT_BASE", "/notebook-admin")

CATEGORY_DIRS = {
    "基础必修": "basic-required",
    "基础选修": "basic-elective",
    "专业方向课": "major-direction",
    "实验课": "lab",
}
CATEGORY_ORDER = list(CATEGORY_DIRS)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def offering_filename(offering):
    sem = offering["semester_name"] or ""
    if not re.match(r"^\d{4}-\d{4}-\d$", sem):
        sem = teacher_slug(sem)
    return f"o{offering['id']}-{sem}-{teacher_slug(offering['teacher_name'])}.md"


# ─── Course overview page ─────────────────────────────────────────────


def build_course_index(course, offerings):
    code = course["code"]
    name = course["name"]
    category = course["category"]

    lines = [
        "---",
        f"title: {name}",
        "---",
        "",
        f"# {name}",
        "",
        "| 字段 | 内容 |",
        "|------|------|",
        f"| 课程代码 | {code} |",
        f"| 课程类别 | {category} |",
        f"| 开课学院 | {course['department'] or '英语学院'} |",
        "",
        f"> 同一门课可能由不同老师在不用学期开设，内容与考核方式可能有差异。"
        f"请选择你想查看的开课记录：",
        "",
    ]

    if offerings:
        lines.extend([
            "## 开课记录",
            "",
            "| 学期 | 任课教师 | 总课时/周课时 | 详情 |",
            "|------|----------|----------------|------|",
        ])
        for o in offerings:
            link = f"[查看]({offering_filename(o)})"
            hours = f"{o['total_hours'] or '—'} / {o['weekly_hours'] or '—'}"
            lines.append(f"| {o['semester_name']} | {o['teacher_name']} | {hours} | {link} |")
        lines.append("")
    else:
        lines.extend([
            "## 开课记录",
            "",
            "暂无收录的开课记录。",
            "",
        ])

    lines.extend([
        f"> ✏️ 有这门课的新开课记录？[提交新开课记录]({EDIT_BASE}/public/new/{code})",
        "",
    ])
    return "\n".join(lines)


# ─── Offering detail page ─────────────────────────────────────────────


def build_offering_markdown(course, offering, conn):
    name = course["name"]

    lines = [
        "---",
        f"title: {name} · {offering['teacher_name']} · {offering['semester_name']}",
        "---",
        "",
        f"# {name}",
        "",
        f"**{offering['semester_name']} · {offering['teacher_name']}**",
        "",
        "| 字段 | 内容 |",
        "|------|------|",
        f"| 课程代码 | {course['code']} |",
        f"| 课程类别 | {course['category']} |",
        f"| 任课教师 | {offering['teacher_name']} |",
        f"| 学期 | {offering['semester_name']} |",
        f"| 开课学院 | {course['department'] or '英语学院'} |",
        f"| 总课时 / 周课时 | {offering['total_hours'] or '待补充'} / {offering['weekly_hours'] or '待补充'} |",
        f"| 教学周数 | {offering['teaching_weeks'] or '待补充'} |",
        "",
    ]

    # Assessment
    lines.extend([
        "## 考核方式",
        "",
        offering["assessment_method"] or "待补充。",
        "",
    ])

    # Textbooks
    textbooks = conn.execute(
        "SELECT * FROM textbooks WHERE offering_id=? ORDER BY sort_order",
        (offering["id"],),
    ).fetchall()
    if textbooks:
        lines.extend(["## 教材及参考资料", ""])
        for tb in textbooks:
            prefix = "教材" if tb["type"] == "教材" else "参考书"
            lines.append(f"- [{prefix}] {tb['description']}")
        lines.append("")

    # Weekly plan
    weekly_plans = conn.execute(
        "SELECT * FROM weekly_plans WHERE offering_id=? ORDER BY week_number",
        (offering["id"],),
    ).fetchall()
    if weekly_plans:
        lines.extend([
            "## 教学进度",
            "",
            "| 日期 | 周次 | 课时 | 教学方式 | 内容提要 | 备注 |",
            "|------|------|------|----------|----------|------|",
        ])
        for wp in weekly_plans:
            method = wp["teaching_method"] or ""
            content = wp["content"] or ""
            notes = wp["notes"] or ""
            lines.append(
                f"| {wp['date']} | {wp['week_number']} | {wp['hours']} | {method} | {content} | {notes} |"
            )
        lines.append("")

    # Comments (rendered client-side, stored in the admin DB)
    lines.extend([
        "## 留言",
        "",
        f'<div class="course-comments" data-offering="{offering["id"]}"'
        f' data-api="{EDIT_BASE}/api/comments"></div>',
        "",
    ])

    # The edit entry sits at the very bottom so the page reads as content first.
    lines.extend([
        "---",
        "",
        f"*最后更新：{offering['updated_at']} · 信息来源：{offering['info_source'] or '2023 级培养方案'}*",
        "",
        f"[✏️ 编辑本页信息]({EDIT_BASE}/public/offering/{offering['id']}){{: .edit-page-link }}",
        "",
    ])
    return "\n".join(lines)


# ─── Category index ───────────────────────────────────────────────────


def page_exists(dir_path, code, managed_codes):
    return (
        code in managed_codes
        or os.path.exists(os.path.join(dir_path, f"{code}.md"))
    )


def build_category_index(category, dir_name, conn):
    """Build index page for a category."""
    dir_path = os.path.join(DOCS_DIR, dir_name)
    courses = conn.execute(
        "SELECT code, name, subcategory FROM courses WHERE category=? ORDER BY code",
        (category,),
    ).fetchall()

    # Latest offering per course (for teacher preview)
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

    managed_codes = {
        row["code"]
        for row in conn.execute(
            "SELECT DISTINCT c.code FROM course_offerings co JOIN courses c ON co.course_id = c.id"
        )
    }

    lines = [f"# {category}", ""]

    subcategories = defaultdict(list)
    for c in courses:
        if page_exists(dir_path, c["code"], managed_codes):
            subcategories[c["subcategory"] or ""].append(c)

    for subcat, items in subcategories.items():
        if subcat:
            lines.append(f"## {subcat}")
            lines.append("")
        for c in items:
            teacher = teacher_map.get(c["code"])
            if c["code"] in managed_codes:
                lines.append(f"- [{c['name']} `{c['code']}`]({c['code']}/index.md)" + (f" · {teacher}" if teacher else ""))
            else:
                lines.append(f"- [{c['name']} `{c['code']}`]({c['code']}.md)" + (f" · {teacher}" if teacher else ""))
        lines.append("")

    return "\n".join(lines)


# ─── Teacher index ────────────────────────────────────────────────────


def build_teacher_index(conn):
    teachers = conn.execute("""
        SELECT DISTINCT t.id, t.name, t.department, t.title
        FROM teachers t
        JOIN course_offerings co ON co.teacher_id = t.id
        ORDER BY t.name
    """).fetchall()

    course_dir = {}
    for c in conn.execute("SELECT code, category FROM courses"):
        course_dir[c["code"]] = CATEGORY_DIRS.get(c["category"], "other")

    offering_files = {
        row["id"]: offering_filename(row)
        for row in conn.execute("""
            SELECT co.id, co.course_id, s.name AS semester_name, t.name AS teacher_name
            FROM course_offerings co
            JOIN teachers t ON co.teacher_id = t.id
            JOIN semesters s ON co.semester_id = s.id
        """)
    }

    lines = ["# 教师索引", ""]
    for t in teachers:
        lines.append(f"## {t['name']}")
        if t["title"] or t["department"]:
            parts = [p for p in [t["title"], t["department"]] if p]
            lines.append(f"*{' · '.join(parts)}*")
        lines.append("")

        offerings = conn.execute("""
            SELECT co.id, c.code, c.name, s.name AS semester_name
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            JOIN semesters s ON co.semester_id = s.id
            WHERE co.teacher_id = ?
            ORDER BY s.name DESC, c.code
        """, (t["id"],)).fetchall()

        for o in offerings:
            cat_dir = course_dir.get(o["code"], "other")
            fname = offering_files.get(o["id"], "")
            lines.append(
                f"- [{o['name']} `{o['code']}`](../categories/{cat_dir}/{o['code']}/{fname})"
                f" · {o['semester_name']}"
            )
        lines.append("")

    if not teachers:
        lines.append("暂无教师数据。")
        lines.append("")

    return "\n".join(lines)


# ─── mkdocs.yml nav ───────────────────────────────────────────────────


def update_mkdocs_nav(conn):
    """Regenerate the nav section of mkdocs.yml."""
    courses = conn.execute("SELECT code, name, category FROM courses ORDER BY code").fetchall()
    managed = defaultdict(list)
    for o in conn.execute("""
        SELECT co.id, c.code, s.name AS semester_name, t.name AS teacher_name
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        ORDER BY s.name DESC, co.id
    """):
        managed[o["code"]].append(o)

    managed_codes = set(managed)

    nav_sections = []
    for cat in CATEGORY_ORDER:
        dir_name = CATEGORY_DIRS[cat]
        dir_path = os.path.join(DOCS_DIR, dir_name)
        lines = [f"  - {cat}:", f"    - categories/{dir_name}/index.md"]
        for c in [c for c in courses if c["category"] == cat]:
            code, name = c["code"], c["name"]
            if code in managed:
                lines.append(f"    - {code} {name}:")
                lines.append(f"      - 课程总览: categories/{dir_name}/{code}/index.md")
                for o in managed[code]:
                    label = f"{o['semester_name']} · {o['teacher_name']}"
                    lines.append(
                        f"      - {label}: categories/{dir_name}/{code}/{offering_filename(o)}"
                    )
            elif os.path.exists(os.path.join(dir_path, f"{code}.md")):
                lines.append(f"    - {code} {name}: categories/{dir_name}/{code}.md")
            # Courses without any page on disk are skipped entirely
        nav_sections.append("\n".join(lines))

    nav_block = "\n".join(nav_sections)
    new_nav = f"""nav:
  - 首页: index.md
{nav_block}
  - 教师索引: teachers/index.md
  - 贡献指南: contributing.md
  - 关于本站: about.md"""

    with open(MKCONFIG, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"^nav:.*", new_nav, content, flags=re.DOTALL | re.MULTILINE)

    with open(MKCONFIG, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    print("  mkdocs.yml nav updated")


# ─── Main export ──────────────────────────────────────────────────────


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
    removed_legacy = 0

    for course in all_courses:
        code = course["code"]
        dir_name = CATEGORY_DIRS.get(course["category"], "other")
        dir_path = os.path.join(DOCS_DIR, dir_name)
        os.makedirs(dir_path, exist_ok=True)

        offerings_for_course = course_offerings.get(code, [])

        if not offerings_for_course:
            # Hand-written page stays untouched.
            continue

        # Course becomes DB-managed: use directory layout.
        course_dir = os.path.join(dir_path, code)
        os.makedirs(course_dir, exist_ok=True)

        expected = set()
        for o in offerings_for_course:
            fname = offering_filename(o)
            expected.add(fname)
            with open(os.path.join(course_dir, fname), "w", encoding="utf-8", newline="\n") as f:
                f.write(build_offering_markdown(course, o, conn))
            generated += 1

        with open(os.path.join(course_dir, "index.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(build_course_index(course, offerings_for_course))

        # Remove stale offering files (deleted offerings)
        for existing in os.listdir(course_dir):
            if existing.startswith("o") and existing.endswith(".md") and existing not in expected:
                os.remove(os.path.join(course_dir, existing))
                print(f"  removed stale {dir_name}/{code}/{existing}")

        # Remove legacy flat page now that a directory page exists
        legacy = os.path.join(dir_path, f"{code}.md")
        if os.path.exists(legacy):
            os.remove(legacy)
            removed_legacy += 1
            print(f"  removed legacy {dir_name}/{code}.md")

    for category, dir_name in CATEGORY_DIRS.items():
        dir_path = os.path.join(DOCS_DIR, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        index_content = build_category_index(category, dir_name, conn)
        with open(os.path.join(dir_path, "index.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(index_content)

    os.makedirs(TEACHERS_DIR, exist_ok=True)
    teacher_content = build_teacher_index(conn)
    with open(os.path.join(TEACHERS_DIR, "index.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(teacher_content)

    update_mkdocs_nav(conn)

    conn.close()
    print(f"\nTotal: {generated} offering pages generated, {removed_legacy} legacy pages migrated.\n")


if __name__ == "__main__":
    export_courses()
