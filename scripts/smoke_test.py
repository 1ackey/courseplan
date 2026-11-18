#!/usr/bin/env python3
"""Smoke test for the CoursePlan admin panel. Requires the app running
at BASE_URL. Safe to re-run: it cleans up after itself.
"""
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "courseplan.db")


def make_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


admin = make_opener()      # logged in as admin
pub = make_opener()        # anonymous student

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def req(op, path, data=None):
    try:
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        r = op.open(BASE_URL + path, body, timeout=60)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def db(query, args=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, args).fetchall()
    conn.commit()
    conn.close()
    return rows


print("== 0. anonymous access ==")
s, body = req(pub, "/")
check("anonymous redirected to login", "管理员密码" in body, body[:200])

print("== 1. admin login ==")
s, body = req(admin, "/login", {"password": "wrong"})
check("wrong password rejected", "密码错误" in body)
s, body = req(admin, "/login", {"password": "admin123"})
check("admin login OK", s == 200)
s, body = req(admin, "/")
check("dashboard visible", "仪表盘" in body)

print("== 2. mode switching ==")
req(admin, "/settings", {"mode": "3"})
s, body = req(pub, "/public/offering/1")
check("mode 3 blocks anonymous edit", s == 403, f"status={s}")
s, body = req(admin, "/public/offering/1")
check("mode 3: admin still can edit", s == 200 and ("保存修改" in body))
req(admin, "/settings", {"mode": "2"})
s, body = req(pub, "/public/offering/1")
check("mode 2: anonymous sees submit form", s == 200 and ("提交审核" in body))

print("== 3. mode 2: student submits -> admin reviews -> approves ==")
s, body = req(pub, "/public/offering/1", {
    "total_hours": "32", "weekly_hours": "2", "teaching_weeks": "16",
    "assessment_method": "测试考核方式（smoke test）",
    "info_source": "smoke-test",
    "plans": "1|3.11|2|研讨|SmokeTestContent|学生主讲\n2|3.18|2|研讨|Defining Pragmatics|教师主讲",
    "textbooks": "教材|SmokeBook\n参考书|SmokePaper",
    "submitter_name": "测试同学", "submitter_contact": "test@example.com",
    "note": "smoke test edit",
})
check("submission accepted", s == 200 and ("提交成功" in body), body[:300])
rows = db("SELECT * FROM submissions WHERE status='pending'")
check("submission queued", len(rows) == 1, f"got {len(rows)}")
sid = rows[0]["id"]
s, body = req(admin, f"/submissions/{sid}")
check("review detail renders diff", "字段对比" in body and "SmokeTestContent" in body)
s, body = req(admin, f"/submissions/{sid}/approve", {"note": "ok"})
cur = db("SELECT assessment_method, info_source FROM course_offerings WHERE id=1")[0]
check("approved change applied", cur["assessment_method"] == "测试考核方式（smoke test）")
plans = db("SELECT content FROM weekly_plans WHERE offering_id=1 ORDER BY week_number")
check("weekly plans replaced", len(plans) == 2 and plans[0]["content"] == "SmokeTestContent", f"got {len(plans)}")
books = db("SELECT type, description FROM textbooks WHERE offering_id=1")
check("textbooks replaced", len(books) == 2)
row = db("SELECT status FROM submissions WHERE id=?", (sid,))[0]
check("submission marked approved", row["status"] == "approved")

print("== 4. mode 1: anonymous direct edit ==")
req(admin, "/settings", {"mode": "1"})
s, body = req(pub, "/public/offering/1", {
    "total_hours": "32", "weekly_hours": "2", "teaching_weeks": "16",
    "assessment_method": "直接生效（smoke test）", "info_source": "smoke-test-2",
    "plans": "1|3.11|2|研讨|DirectEdit|教师主讲",
    "textbooks": "",
})
cur = db("SELECT assessment_method FROM course_offerings WHERE id=1")[0]
check("mode 1 applies immediately", cur["assessment_method"] == "直接生效（smoke test）")
check("no submission queued in mode 1", len(db("SELECT * FROM submissions WHERE status='pending'")) == 0)
s, body = req(pub, "/public/offering/1")
check("mode 1 form shows 保存修改", "保存修改" in body)

print("== 5. create offering (mode 1) ==")
s, body = req(pub, "/public/new/ENG797", {
    "teacher_name": "测试教师", "semester_name": "2026-2027-1", "new_semester": "",
    "total_hours": "32", "weekly_hours": "2", "teaching_weeks": "16",
    "assessment_method": "新开课测试", "info_source": "smoke",
    "plans": "1|9.17|2|研讨|NewOffering|", "textbooks": "",
})
check("new offering created", s == 200 and "已添加" in body, body[:300])
row = db("SELECT co.id FROM course_offerings co JOIN teachers t ON co.teacher_id=t.id JOIN semesters s ON co.semester_id=s.id WHERE t.name='测试教师' AND s.name='2026-2027-1'")
check("offering row exists", len(row) == 1)
if row:
    db("DELETE FROM course_offerings WHERE id=?", (row[0]["id"],))
    db("DELETE FROM teachers WHERE name='测试教师'")
    db("DELETE FROM semesters WHERE name='2026-2027-1'")
    print("  (test offering cleaned up)")

print("== 6. mode 2 create -> reject flow ==")
req(admin, "/settings", {"mode": "2"})
s, body = req(pub, "/public/new/ENG797", {
    "teacher_name": "测试教师2", "semester_name": "2026-2027-1", "new_semester": "",
    "total_hours": "32", "weekly_hours": "2", "teaching_weeks": "16",
    "assessment_method": "待驳回", "info_source": "", "plans": "", "textbooks": "",
})
check("create submission queued", "提交成功" in body)
rows = db("SELECT * FROM submissions WHERE status='pending' AND action='create_offering'")
check("create submission exists", len(rows) == 1)
if rows:
    s, body = req(admin, f"/submissions/{rows[0]['id']}")
    check("create detail renders", "提交的内容" in body)
    s, body = req(admin, f"/submissions/{rows[0]['id']}/reject", {"note": "测试驳回"})
    check("rejected", "已驳回" in body)
check("nothing applied after reject", len(db("SELECT * FROM teachers WHERE name='测试教师2'")) == 0)

print("== 7. publish pipeline (build only) ==")
req(admin, "/settings", {"mode": "1"})
s, body = req(admin, "/publish", {})
check("publish pipeline ran", "发布成功" in body or "publish: done" in body, body[:400])

# restore original ENG820 data
db("UPDATE course_offerings SET assessment_method='待补充。', info_source='2023 级培养方案' WHERE id=1")
db("DELETE FROM textbooks WHERE offering_id=1")
db("DELETE FROM weekly_plans WHERE offering_id=1")
plans = [
    (1, "3.11", 2, "研讨", "General Introduction (1) — Defining Pragmatics", "教师主讲"),
    (2, "3.18", 2, "研讨", "Defining Pragmatics (2)", "教师主讲"),
    (3, "3.25", 2, "研讨", "Deixis 2.1-2.2 (1)", "学生主讲"),
    (4, "4.01", 2, "研讨", "Deixis 2.3-2.4 (2)", "学生主讲"),
    (5, "4.08", 2, "研讨", "Deixis (3)", "教师主讲"),
    (6, "4.15", 2, "研讨", "Presupposition（1）", "学生主讲"),
    (7, "4.22", 2, "研讨", "Presupposition（2）", "教师主讲"),
    (8, "4.29", 2, "研讨", "Implicature：4.1-4.4 (1)", "学生主讲"),
    (9, "5.06", 2, "研讨", "Implicature：4.5-4.7 (2)", "学生主讲"),
    (10, "5.13", 2, "研讨", "Implicature (3)", "教师主讲"),
    (11, "5.20", 2, "研讨", "Speech Acts（1）", "学生主讲"),
    (12, "5.27", 2, "研讨", "Speech Acts（2）", "教师主讲"),
    (13, "6.03", 2, "研讨", "Politeness（1）", "学生主讲"),
    (14, "6.10", 2, "研讨", "Politeness（2）", "教师主讲"),
    (15, "6.17", 2, "研讨", "Review & Discussion", "教师主讲"),
    (16, "待定", 2, "考试", "期末考核", ""),
]
for p in plans:
    db("INSERT INTO weekly_plans (offering_id, week_number, date, hours, teaching_method, content, notes) VALUES (1, ?, ?, ?, ?, ?, ?)", p)
db("DELETE FROM submissions")
db("INSERT OR REPLACE INTO site_settings (key, value) VALUES ('management_mode', '1')")
print("  (test data restored, submissions cleared)")

print(f"\nResult: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
