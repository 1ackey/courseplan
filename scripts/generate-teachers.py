"""Generate teacher index page from all course files."""

import re
from collections import defaultdict
from pathlib import Path

CATEGORY_NAMES = {
    "basic-required": "基础必修",
    "basic-elective": "基础选修",
    "major-direction": "专业方向课",
    "lab": "实验课",
}

COURSE_META_PATTERN = re.compile(
    r"\|\s*课程名称\s*\|\s*(.+?)\s*\|"
    r".*?"
    r"\|\s*课程代码\s*\|\s*(.+?)\s*\|"
    r".*?"
    r"\|\s*课程类别\s*\|\s*(.+?)\s*\|"
    r".*?"
    r"\|\s*任课教师\s*\|\s*(.+?)\s*\|",
    re.DOTALL,
)


def extract_teacher(content: str) -> str | None:
    """Extract teacher name from course markdown content."""
    match = re.search(r"\|\s*任课教师\s*\|\s*(.+?)\s*\|", content)
    if match:
        return match.group(1).strip()
    return None


def extract_course_name(content: str) -> str | None:
    match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_course_code(content: str) -> str | None:
    match = re.search(r"\|\s*课程代码\s*\|\s*(.+?)\s*\|", content)
    if match:
        return match.group(1).strip()
    return None


def extract_category(content: str) -> str | None:
    match = re.search(r"\|\s*课程类别\s*\|\s*(.+?)\s*\|", content)
    if match:
        return match.group(1).strip()
    return None


def build_teacher_index(categories_dir: Path) -> dict:
    """Build teacher→courses mapping from all course files."""
    teacher_courses = defaultdict(list)

    for category_dir in sorted(categories_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        category_slug = category_dir.name
        for md_file in sorted(category_dir.glob("*.md")):
            if md_file.name == "index.md":
                continue

            content = md_file.read_text(encoding="utf-8")
            teacher = extract_teacher(content)
            course_name = extract_course_name(content)
            course_code = extract_course_code(content)
            relative_path = f"../categories/{category_slug}/{md_file.name}"

            if teacher and course_name:
                teacher_courses[teacher].append({
                    "name": course_name,
                    "code": course_code or "",
                    "path": relative_path,
                })

    return dict(sorted(teacher_courses.items()))


def generate_markdown(teacher_courses: dict) -> str:
    """Generate teacher index markdown content."""
    lines = ["# 按授课教师浏览", "", "<!-- 此页面由脚本自动生成，请勿手动编辑 -->", ""]

    for teacher, courses in teacher_courses.items():
        lines.append(f"## {teacher}")
        lines.append("")
        for c in courses:
            code = f" `{c['code']}`" if c["code"] else ""
            lines.append(f"- [{c['name']}{code}]({c['path']})")
        lines.append("")

    if not teacher_courses:
        lines.append("")
        lines.append("!!! info \"暂无数据\"")
        lines.append("    还没有收录任何课程信息。[贡献第一门课 →](../contributing/)")

    return "\n".join(lines)


def main():
    docs_dir = Path("docs")
    categories_dir = docs_dir / "categories"
    teachers_file = docs_dir / "teachers" / "index.md"

    teacher_courses = build_teacher_index(categories_dir)
    content = generate_markdown(teacher_courses)

    teachers_file.write_text(content, encoding="utf-8")
    print(f"Generated teacher index: {len(teacher_courses)} teachers, "
          f"{sum(len(v) for v in teacher_courses.values())} courses")


if __name__ == "__main__":
    main()
