"""Validate a course Markdown file for required fields and correct format."""

import re
import sys
from pathlib import Path

REQUIRED_FIELDS = [
    "课程代码",
    "课程类别",
    "任课教师",
    "开课学院",
    "总课时 / 周课时",
    "教学周数",
    "考核方式",
]

REQUIRED_TABLE_HEADERS = [
    "日期",
    "周次",
    "课时",
    "教学方式",
    "内容提要",
    "备注",
]


def extract_yaml_frontmatter(content: str) -> tuple[str, str]:
    """Extract YAML frontmatter if present."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
    return "", content


def check_required_fields(content: str) -> list[str]:
    """Check that all required fields are present in the course meta table."""
    errors = []

    meta_match = re.search(r"\|.*课程代码.*\|", content)
    if not meta_match:
        errors.append("Missing course meta info table")
        return errors

    for field in REQUIRED_FIELDS:
        if field not in content:
            errors.append(f"Missing required field: {field}")

    return errors


def check_schedule_table(content: str) -> list[str]:
    """Check that the teaching schedule table is present and has proper headers."""
    errors = []

    table_match = re.search(r"\|.*日期.*\|", content)
    if not table_match:
        errors.append("Missing teaching schedule table")
        return errors

    for header in REQUIRED_TABLE_HEADERS:
        if header not in table_match.group():
            errors.append(f"Missing table header column: {header}")

    rows = re.findall(r"\| \d+\.\d+ \|", content)
    if not rows:
        errors.append("No teaching schedule rows found (expected date format: mm.dd)")

    return errors


def validate_course(filepath: str) -> bool:
    """Validate a course markdown file."""
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: File not found: {filepath}")
        return False

    content = path.read_text(encoding="utf-8")
    _, body = extract_yaml_frontmatter(content)

    errors = check_required_fields(body) + check_schedule_table(body)

    if errors:
        print(f"Validation failed for {path.name}:")
        for e in errors:
            print(f"  - {e}")
        return False

    print(f"OK: {path.name}")
    return True


if __name__ == "__main__":
    exit_code = 0
    if len(sys.argv) < 2:
        # Validate all course files
        docs_dir = Path("docs/categories")
        for md_file in sorted(docs_dir.rglob("*.md")):
            if md_file.name == "index.md":
                continue
            if not validate_course(str(md_file)):
                exit_code = 1
    else:
        for filepath in sys.argv[1:]:
            if not validate_course(filepath):
                exit_code = 1

    sys.exit(exit_code)
