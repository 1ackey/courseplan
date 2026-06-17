#!/usr/bin/env python3
"""Generate placeholder course Markdown files from the 2023 training plan."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs", "categories")
TEMPLATE_DIR = os.path.join(BASE_DIR, "docs", "templates")

COURSE_TEMPLATE = """---
title: {name}
---

# {name}

| 字段 | 内容 |
|------|------|
| 课程代码 | {code} |
| 课程类别 | {category} |
| 任课教师 | 待补充 |
| 开课学院 | 英语学院 |
| 总课时 / 周课时 | {hours} / {weekly} |
| 教学周数 | 待补充 |
| 开课学期 | 第{semester}学期 |

## 考核方式

待补充。

## 教材及参考资料

待补充。

## 教学进度

待补充。

---

*最后更新：2026-06-17 · 信息来源：2023 级培养方案*
"""


def compute_weekly(hours, credits):
    """Estimate weekly hours: typically 2h/week for 32h/16w courses, 1h/w for 16h, 3h/w for 48h."""
    if hours == 16:
        return 1
    if hours == 48:
        return 3
    if hours == 96:
        return 6
    return hours // 16


def write_course(directory, code, name, hours, credits, semester, category, extra=None):
    weekly = compute_weekly(hours, credits)
    content = COURSE_TEMPLATE.format(
        name=name, code=code, category=category,
        hours=hours, weekly=weekly, semester=semester,
    )
    if extra:
        content += extra
    path = os.path.join(directory, f"{code}.md")
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def generate():
    # ── Basic Required ──────────────────────────────────────────────
    br_dir = os.path.join(DOCS_DIR, "basic-required")
    basic_required = [
        ("ENG183", "综合商务英语（一）", 96, 6, 1),
        ("ENG184", "综合商务英语（二）", 96, 6, 2),
        ("ENG185", "综合商务英语（三）", 96, 6, 3),
        ("ENG186", "综合商务英语（四）", 96, 6, 4),
        ("ENG775", "商务英语听说（一）", 32, 2, 1),
        ("ENG776", "英语阅读指导与实践", 32, 2, 1),
        ("ENG777", "英语语法与写作", 32, 2, 1),
        ("ENG778", "商务英语听说（二）", 32, 2, 2),
        ("ENG779", "英语文学阅读（一）", 32, 2, 2),
        ("ENG780", "英语修辞与写作", 32, 2, 2),
        ("ENG781", "英语演讲与辩论", 32, 2, 3),
        ("ENG783", "英汉笔译基础", 32, 2, 3),
        ("ENG786", "普通语言学导论", 32, 2, 4),
        ("ENG493", "英语论文写作", 32, 2, 6),
        ("ENG790", "文学研究方法与论文写作", 32, 2, 6),
        ("ESP320", "第二外语（西）（一）", 48, 3, 3),
        ("ESP321", "第二外语（西）（二）", 48, 3, 4),
        ("FRA343", "第二外语（法）（一）", 48, 3, 3),
        ("FRA344", "第二外语（法）（二）", 48, 3, 4),
        ("GER348", "第二外语（德）（一）", 48, 3, 3),
        ("GER349", "第二外语（德）（二）", 48, 3, 4),
        ("JAP325", "第二外语（日）（一）", 48, 3, 3),
        ("JAP326", "第二外语（日）（二）", 48, 3, 4),
    ]
    br_entries = []
    for code, name, hours, credits, sem in basic_required:
        write_course(br_dir, code, name, hours, credits, sem, "基础必修")
        br_entries.append((code, name, sem))

    # ── Basic Elective ──────────────────────────────────────────────
    be_dir = os.path.join(DOCS_DIR, "basic-elective")
    be_subs = {
        "语言技能": [
            ("ENG187", "商务英语写作（一）", 32, 2, 4),
            ("ENG188", "商务英语写作（二）", 32, 2, 5),
            ("ENG301", "高级商务英语听说", 32, 2, 4),
            ("ENG323", "金融英语阅读", 32, 2, 5),
            ("ENG360", "商务翻译（英译汉）", 32, 2, 5),
            ("ENG361", "商务翻译（汉译英）", 32, 2, 6),
            ("ENG465", "实用法律文书翻译（英）", 32, 2, 7),
            ("ENG526", "翻译概论（英）", 32, 2, 5),
            ("ENG645", "学术英语阅读与写作", 32, 2, 5),
            ("ENG756", "基础英语测试", 16, 1, 4),
            ("ENG787", "汉英笔译基础", 32, 2, 4),
            ("ENG794", "商务英语阅读", 32, 2, 4),
            ("ENG795", "英语听译", 32, 2, 4),
            ("ENG796", "金融英语技能训练", 32, 2, 5),
            ("ENG807", "英语文学阅读（三）", 32, 2, 4),
            ("ENG827", "文学翻译（英）", 32, 2, 6),
        ],
        "文学与文化": [
            ("ENG194", "莎士比亚入门（英）", 32, 2, 6),
            ("ENG491", "名著名译选读（英）", 32, 2, 6),
            ("ENG599", "美国短篇小说选读（英）", 32, 2, 3),
            ("ENG631", "欧美戏剧（英）", 32, 2, 4),
            ("ENG633", "散文分析", 32, 2, 5),
            ("ENG799", "英国社会与文化", 32, 2, 3),
            ("ENG800", "美国历史", 32, 2, 3),
            ("ENG808", "美国社会与文化", 32, 2, 4),
            ("ENG809", "19世纪晚期英国小说与社会", 32, 2, 4),
            ("ENG810", "西方哲学史（英）", 32, 2, 5),
            ("CLL402", "中外文学交流专题", 32, 2, 6),
            ("HUM428", "西方文论", 32, 2, 6),
        ],
        "商务": [
            ("ENG263", "国际商业文化（英）", 32, 2, 5),
            ("ENG299", "国际金融导论（英）", 32, 2, 5),
            ("ENG356", "商业伦理学（英）", 32, 2, 5),
            ("ENG359", "高级金融英语", 32, 2, 5),
            ("ENG463", "国际商务礼仪（英）", 32, 2, 6),
            ("ENG470", "商法导论（英）", 32, 2, 6),
            ("ENG487", "商科经典名著选读（英）", 32, 2, 6),
            ("ENG628", "国际贸易（英）", 32, 2, 6),
            ("ENG733", "创新与创业管理（英）", 32, 2, 6),
            ("ENG734", "创业计划书（英）", 16, 1, 7),
            ("ENG784", "商学导论（英）", 32, 2, 4),
            ("ENG812", "管理学（英）", 32, 2, 4),
            ("ENG813", "营销学（英）", 32, 2, 5),
            ("ENG815", "经济外交（英）", 32, 2, 6),
            ("ENG817", "跨文化交际导论（英）", 32, 2, 4),
            ("ENG819", "经济学原理（英）", 32, 2, 5),
            ("ENG848", "组织行为学（英）", 32, 2, 6),
            ("ENT307", "翻译创业管理", 32, 2, 6),
        ],
        "语言学与国际传播": [
            ("ENG540", "文化人类学（英）", 32, 2, 4),
            ("ENG648", "英语词汇学导论", 32, 2, 3),
            ("ENG742", "新闻传播伦理", 32, 2, 6),
            ("ENG766", "国际组织概况", 32, 2, 2),
            ("ENG772", "当代财经新闻实务（英）", 32, 2, 5),
            ("ENG773", "媒介经营与管理（英）", 32, 2, 6),
            ("ENG811", "当代中国与媒体（英）", 32, 2, 6),
            ("ENG814", "社会语言学", 32, 2, 4),
            ("ENG816", "互联网与全球性议题", 32, 2, 6),
            ("ENG823", "对比语言学", 32, 2, 4),
        ],
    }
    be_entries = {}
    for sub_cat, courses in be_subs.items():
        be_entries[sub_cat] = []
        for code, name, hours, credits, sem in courses:
            write_course(be_dir, code, name, hours, credits, sem, "基础选修")
            be_entries[sub_cat].append((code, name, sem))

    # ── Major Direction ─────────────────────────────────────────────
    md_dir = os.path.join(DOCS_DIR, "major-direction")
    md_directions = {
        "文学方向": [
            ("ENG357", "英美文学导论（英）", 32, 2, 4),
            ("ENG765", "西方文明史（英）", 32, 2, 5),
            ("ENG831", "英国文学", 32, 2, 5),
            ("ENG833", "美国文学", 32, 2, 6),
            ("ENG834", "文学批评导论", 32, 2, 6),
            ("ENG836", "英语诗歌", 32, 2, 7),
        ],
        "语言学方向": [
            ("ENG837", "英语语言史", 32, 2, 4),
            ("ENG797", "句法学", 32, 2, 5),
            ("ENG798", "语义学", 32, 2, 5),
            ("ENG366", "英语文体学", 32, 2, 6),
            ("ENG822", "话语分析", 32, 2, 6),
        ],
        "国际传播方向": [
            ("ENG824", "国际政治（英）", 32, 2, 4),
            ("ENG845", "英语新闻采访与写作", 32, 2, 4),
            ("ENG519", "传播学导论（英）", 32, 2, 5),
            ("ENG818", "新媒体理论与实践", 32, 2, 5),
            ("ENG450", "新闻编辑（英）", 32, 2, 6),
            ("ENG821", "话语修辞与谈判", 32, 2, 6),
        ],
    }
    md_entries = {}
    for direction, courses in md_directions.items():
        md_entries[direction] = []
        for code, name, hours, credits, sem in courses:
            write_course(md_dir, code, name, hours, credits, sem, "专业方向课")
            md_entries[direction].append((code, name, sem))

    # ── Lab ─────────────────────────────────────────────────────────
    lab_dir = os.path.join(DOCS_DIR, "lab")
    lab_courses = [
        ("ENG549", "英语语音与会话", 32, 2, 1),
        ("ENG847", "英语歌曲与跨文化沟通", 32, 2, 2),
        ("ENG846", "英语戏剧欣赏与实践", 32, 2, 5),
        ("ENG838", "语料库语言学", 32, 2, 5),
        ("ENG839", "财经新闻写作实践（英）", 32, 2, 6),
        ("ENG495", "进出口实务（英）", 32, 2, 5),
        ("ENG531", "机辅翻译（英）", 32, 2, 7),
        ("ENG598", "口译实践", 32, 2, 7),
        ("ENG740", "商务英语谈判", 32, 2, 7),
    ]
    lab_entries = []
    for code, name, hours, credits, sem in lab_courses:
        write_course(lab_dir, code, name, hours, credits, sem, "实验课")
        lab_entries.append((code, name, sem))

    # ── Handle ENG820 special case ──────────────────────────────────
    # Read existing file to preserve teaching progress
    eng820_path = os.path.join(md_dir, "ENG820.md")
    eng820_original = ""
    if os.path.exists(eng820_path):
        with open(eng820_path, "r", encoding="utf-8") as f:
            eng820_original = f.read()

    # Extract teaching progress section from original
    import re
    progress_match = re.search(
        r"## 教学进度\n\n(.*?)(?:\n\n---|\Z)",
        eng820_original, re.DOTALL
    )
    existing_progress_table = progress_match.group(1).rstrip() if progress_match else ""

    # Recreate ENG820 with updated metadata + existing teaching progress
    eng820_content = COURSE_TEMPLATE.format(
        name="语用学", code="ENG820", category="专业方向课",
        hours=32, weekly=2, semester=6,
    )
    if existing_progress_table:
        eng820_content = eng820_content.replace(
            "## 教学进度\n\n待补充。\n",
            f"## 教学进度\n\n{existing_progress_table}\n"
        )
    eng820_content = eng820_content.replace("任课教师 | 待补充", "任课教师 | 向明友")

    with open(eng820_path, "w", encoding="utf-8") as f:
        f.write(eng820_content)

    md_entries.setdefault("语言学方向", []).append(("ENG820", "语用学", 6))
    # Sort so ENG820 appears in proper position (by semester then code)
    md_entries["语言学方向"].sort(key=lambda x: (x[2], x[0]))

    # ── Write index files ───────────────────────────────────────────

    # basic-required index
    br_lines = ["# 基础必修\n"]
    for code, name, sem in br_entries:
        br_lines.append(f"- [{name} `{code}`]({code}.md) · 第{sem}学期 · 待补充")
    br_lines.append("")
    with open(os.path.join(br_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(br_lines))

    # basic-elective index (grouped by sub-category)
    be_lines = ["# 基础选修\n"]
    for sub_cat, entries in be_entries.items():
        be_lines.append(f"\n## {sub_cat}\n")
        for code, name, sem in entries:
            be_lines.append(f"- [{name} `{code}`]({code}.md) · 第{sem}学期 · 待补充")
    be_lines.append("")
    with open(os.path.join(be_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(be_lines))

    # major-direction index (grouped by direction)
    md_lines = ["# 专业方向课\n"]
    for direction, entries in md_entries.items():
        md_lines.append(f"\n## {direction}\n")
        for code, name, sem in entries:
            teacher = "向明友" if code == "ENG820" else "待补充"
            md_lines.append(f"- [{name} `{code}`]({code}.md) · 第{sem}学期 · {teacher}")
    md_lines.append(f"\n[贡献课程 →](../../contributing.md)")
    md_lines.append("")
    with open(os.path.join(md_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # lab index
    lab_lines = ["# 实验课\n"]
    for code, name, sem in lab_entries:
        lab_lines.append(f"- [{name} `{code}`]({code}.md) · 第{sem}学期 · 待补充")
    lab_lines.append("")
    with open(os.path.join(lab_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lab_lines))

    # Summary
    total = len(br_entries)
    total += sum(len(v) for v in be_entries.values())
    total += sum(len(v) for v in md_entries.values())
    total += len(lab_entries)
    print(f"Generated {total} course files + 4 index files.")
    print(f"  basic-required: {len(br_entries)} courses")
    for sub, entries in be_entries.items():
        print(f"  basic-elective/{sub}: {len(entries)} courses")
    for d, entries in md_entries.items():
        print(f"  major-direction/{d}: {len(entries)} courses")
    print(f"  lab: {len(lab_entries)} courses")


if __name__ == "__main__":
    generate()
