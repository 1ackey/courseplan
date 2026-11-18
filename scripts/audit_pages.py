#!/usr/bin/env python3
"""Audit hand-written course pages: what content exists, what teacher /
semester evidence is available. Read-only."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_existing import (  # noqa: E402
    DOCS_DIR, parse_first_field_table, parse_opening_table,
    parse_weekly_table, split_sections,
)

rows = []
for dir_name in sorted(os.listdir(DOCS_DIR)):
    dir_path = os.path.join(DOCS_DIR, dir_name)
    if not os.path.isdir(dir_path):
        continue
    for fname in sorted(os.listdir(dir_path)):
        if not re.match(r"^[A-Z]{2,4}\d{3}\.md$", fname):
            continue
        code = fname[:-3]
        with open(os.path.join(dir_path, fname), encoding="utf-8") as f:
            text = f.read()

        fields = parse_first_field_table(text)
        sections = split_sections(text)
        opening = parse_opening_table(sections.get("开课记录", ""))
        plans = parse_weekly_table(sections.get("教学进度", ""))

        teacher = fields.get("任课教师", "").strip()
        if not teacher or teacher in ("待补充", "—", "-"):
            named = [t for _, t, _ in opening if t and t not in ("待补充", "—", "-")]
            teacher = named[0] if named else ""
        semesters_named = [s for s, t, _ in opening
                           if t and t not in ("待补充", "—", "-") and re.match(r"^\d{4}-\d{4}-\d$", s)]
        months = []
        for p in plans:
            m = re.match(r"^(\d{1,2})\.\d+", p["date"] or "")
            if m:
                months.append(int(m.group(1)))
        term_hint = ""
        if months:
            if any(9 <= m <= 12 for m in months):
                term_hint = "秋季(第1学期)"
            elif any(1 <= m <= 7 for m in months):
                term_hint = "春季(第2学期)"
        fm = re.search(r"最后更新：(\d{4})-\d{2}-\d{2}", text)
        footer_year = fm.group(1) if fm else ""
        has_img = "../../images/" in text or "](images/" in text
        assessment_len = len(sections.get("考核方式", "").strip())

        rows.append({
            "dir": dir_name, "code": code,
            "teacher": teacher or "—",
            "sem_named": ",".join(semesters_named) or "—",
            "term_hint": term_hint or "—",
            "footer_year": footer_year or "—",
            "plans": len(plans),
            "assess": assessment_len,
            "img": "Y" if has_img else "",
        })

has_content = [r for r in rows if r["plans"] > 0 or r["assess"] > 60 or r["img"]]
empty = [r for r in rows if r not in has_content]

def show(title, group):
    print(f"\n==== {title} ({len(group)}) ====")
    print(f"{'代码':8}{'教师':10}{'学期线索':14}{'日期提示':12}{'进度':5}{'考核字数':8}{'图':3}{'更新年'}")
    for r in group:
        print(f"{r['code']:8}{r['teacher']:10}{r['sem_named']:14}{r['term_hint']:12}"
              f"{r['plans']:<5}{r['assess']:<8}{r['img']:3}{r['footer_year']}")

show("有内容的页面", has_content)
show("空页面(骨架)", empty)
