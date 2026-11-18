#!/usr/bin/env python3
"""把课程页上的「待补充」占位文案替换成「—」，保留字段结构。

只处理 docs/categories 下的页面；由 export_courses.py 生成的页面
会在导出时被重新写入，这里一并处理也无副作用。
"""
import os

DOCS = "/home/appuser/notebook/docs/categories"

TABLE_PAIRS = [
    ("待补充 / 待补充", "— / —"),   # 总课时 / 周课时 两格都缺
    ("/ 待补充 |", "/ — |"),         # 32 / 待补充
    ("| 教师待补充 |", "| — |"),     # 任课教师 = 教师待补充
    ("| 待补充 |", "| — |"),         # 其余表格单元格
]

BODY_LINES = {"待补充。", "待补充"}


def fix(text):
    for old, new in TABLE_PAIRS:
        text = text.replace(old, new)
    out = []
    for line in text.split("\n"):
        out.append("—" if line.strip() in BODY_LINES else line)
    return "\n".join(out)


def main():
    files = 0
    for root, _dirs, names in os.walk(DOCS):
        for name in names:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if "待补充" not in text:
                continue
            new = fix(text)
            if new != text:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
                files += 1
    print(f"updated {files} files")


if __name__ == "__main__":
    main()
