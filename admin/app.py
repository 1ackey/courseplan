#!/usr/bin/env python3
"""Flask admin panel for CoursePlan database management.

Also hosts the public editing UI and the management-mode system:

- Mode 1: everyone can edit anything, changes apply immediately.
- Mode 2: everyone can propose changes; admin reviews then publishes.
- Mode 3: read-only for everyone except the admin panel.
"""
import csv
import io
import json
import os
import subprocess
import sys
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, Response,
    session,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import DB_PATH

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "courseplan-admin-secret-key")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MAX_PLANS_PER_SUBMISSION = 200
RATE_LIMIT_WINDOW_MINUTES = 10
RATE_LIMIT_MAX_SUBMISSIONS = 3


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── Auth, settings & mode ────────────────────────────────────────────


def is_admin():
    return bool(session.get("is_admin"))


def current_mode():
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM site_settings WHERE key='management_mode'"
    ).fetchone()
    conn.close()
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return 1


def set_mode(mode):
    conn = get_db()
    conn.execute(
        """INSERT INTO site_settings (key, value) VALUES ('management_mode', ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (str(mode),),
    )
    conn.commit()
    conn.close()


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.before_request
def auth_guard():
    public_prefixes = ("/login", "/logout", "/static", "/public")
    if request.path.startswith(public_prefixes):
        return None
    if not is_admin():
        return redirect(url_for("login", next=request.path))
    return None


@app.context_processor
def inject_globals():
    pending = 0
    if is_admin():
        conn = get_db()
        pending = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
    return {
        "is_admin": is_admin(),
        "current_mode_value": current_mode(),
        "pending_count": pending,
    }


# ─── Payload helpers (public submissions) ─────────────────────────────


def parse_plans_text(text):
    """Parse weekly plan lines: 周次 | 日期 | 课时 | 教学方式 | 内容 | 备注."""
    plans = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("|") and set(line) <= set("|- "):
            continue
        parts = [p.strip() for p in line.replace("\t", "|").strip("|").split("|")]
        parts = [p for p in parts if p != ""]
        if len(parts) < 1:
            continue
        try:
            week = int(parts[0])
        except ValueError:
            continue
        plans.append({
            "week_number": week,
            "date": parts[1] if len(parts) > 1 else "",
            "hours": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 2,
            "teaching_method": parts[3] if len(parts) > 3 else "",
            "content": parts[4] if len(parts) > 4 else "",
            "notes": parts[5] if len(parts) > 5 else "",
        })
        if len(plans) >= MAX_PLANS_PER_SUBMISSION:
            break
    return plans


def parse_textbooks_text(text):
    """Parse textbook lines: 教材|... / 参考书|... / plain text."""
    books = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:]
        if "|" in line:
            btype, desc = line.split("|", 1)
            btype = btype.strip()
            if btype in ("教材", "参考书"):
                books.append({"type": btype, "description": desc.strip()})
                continue
        books.append({"type": "参考书", "description": line.strip()})
    return books


def serialize_textbooks(textbooks):
    return "\n".join(f"{b['type']}|{b['description']}" for b in textbooks)


def serialize_plans(plans):
    lines = []
    for p in plans:
        lines.append(
            f"{p['week_number']}|{p['date'] or ''}|{p['hours'] or 2}|"
            f"{p['teaching_method'] or ''}|{p['content'] or ''}|{p['notes'] or ''}"
        )
    return "\n".join(lines)


def snapshot_offering(conn, offering_id):
    """Current state of an offering as JSON-able dict (for review diffs)."""
    o = conn.execute("""
        SELECT co.*, c.code, c.name AS course_name,
               t.name AS teacher_name, s.name AS semester_name
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        WHERE co.id=?
    """, (offering_id,)).fetchone()
    if not o:
        return None
    return {
        "action": "edit_offering",
        "offering_id": offering_id,
        "label": f"{o['code']} {o['course_name']} · {o['teacher_name']} · {o['semester_name']}",
        "fields": {
            "total_hours": o["total_hours"],
            "weekly_hours": o["weekly_hours"],
            "teaching_weeks": o["teaching_weeks"],
            "assessment_method": o["assessment_method"] or "",
            "info_source": o["info_source"] or "",
        },
        "textbooks": [
            {"type": b["type"], "description": b["description"]}
            for b in conn.execute(
                "SELECT * FROM textbooks WHERE offering_id=? ORDER BY sort_order",
                (offering_id,),
            )
        ],
        "weekly_plans": [
            {"week_number": p["week_number"], "date": p["date"], "hours": p["hours"],
             "teaching_method": p["teaching_method"], "content": p["content"], "notes": p["notes"]}
            for p in conn.execute(
                "SELECT * FROM weekly_plans WHERE offering_id=? ORDER BY week_number",
                (offering_id,),
            )
        ],
    }


def insert_offering_children(conn, offering_id, payload):
    for i, b in enumerate(payload.get("textbooks") or []):
        conn.execute(
            "INSERT INTO textbooks (offering_id, type, description, sort_order) VALUES (?, ?, ?, ?)",
            (offering_id, b["type"], b["description"], i),
        )
    for p in payload.get("weekly_plans") or []:
        conn.execute(
            """INSERT INTO weekly_plans
               (offering_id, week_number, date, hours, teaching_method, content, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (offering_id, p["week_number"], p["date"], p["hours"],
             p["teaching_method"], p["content"], p["notes"]),
        )


def apply_payload(conn, payload):
    """Apply an approved (or mode-1 direct) payload to the database."""
    action = payload["action"]
    if action == "edit_offering":
        oid = payload["offering_id"]
        f = payload["fields"]
        conn.execute(
            """UPDATE course_offerings SET total_hours=?, weekly_hours=?, teaching_weeks=?,
               assessment_method=?, info_source=?, updated_at=date('now') WHERE id=?""",
            (f["total_hours"], f["weekly_hours"], f["teaching_weeks"],
             f["assessment_method"], f["info_source"], oid),
        )
        conn.execute("DELETE FROM textbooks WHERE offering_id=?", (oid,))
        conn.execute("DELETE FROM weekly_plans WHERE offering_id=?", (oid,))
        insert_offering_children(conn, oid, payload)
        return oid
    if action == "create_offering":
        f = payload["fields"]
        course = conn.execute(
            "SELECT id FROM courses WHERE code=?", (payload["course_code"],)
        ).fetchone()
        if not course:
            raise ValueError(f"课程 {payload['course_code']} 不存在")
        teacher = conn.execute(
            "SELECT id FROM teachers WHERE name=?", (payload["teacher_name"],)
        ).fetchone()
        if not teacher:
            teacher = conn.execute(
                "INSERT INTO teachers (name, department) VALUES (?, '英语学院')",
                (payload["teacher_name"],),
            )
            teacher_id = teacher.lastrowid
        else:
            teacher_id = teacher["id"]
        semester = conn.execute(
            "SELECT id FROM semesters WHERE name=?", (payload["semester_name"],)
        ).fetchone()
        if not semester:
            import re as _re
            m = _re.match(r"^(\d{4})-(\d{4})-(\d)$", payload["semester_name"])
            if not m:
                raise ValueError("学期格式应为 2026-2027-1 这样的形式")
            semester = conn.execute(
                "INSERT INTO semesters (name, academic_year, term) VALUES (?, ?, ?)",
                (payload["semester_name"], m.group(1) + "-" + m.group(2), int(m.group(3))),
            )
            semester_id = semester.lastrowid
        else:
            semester_id = semester["id"]
        dup = conn.execute(
            """SELECT id FROM course_offerings WHERE course_id=? AND teacher_id=? AND semester_id=?""",
            (course["id"], teacher_id, semester_id),
        ).fetchone()
        if dup:
            raise ValueError("该课程-教师-学期组合已存在")
        cur = conn.execute(
            """INSERT INTO course_offerings
               (course_id, teacher_id, semester_id, total_hours, weekly_hours,
                teaching_weeks, assessment_method, info_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (course["id"], teacher_id, semester_id, f["total_hours"], f["weekly_hours"],
             f["teaching_weeks"], f["assessment_method"], f["info_source"]),
        )
        insert_offering_children(conn, cur.lastrowid, payload)
        return cur.lastrowid
    if action == "delete_offering":
        conn.execute("DELETE FROM course_offerings WHERE id=?", (payload["offering_id"],))
        return payload["offering_id"]
    raise ValueError(f"未知操作: {action}")


def run_publish():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(base, "scripts", "publish.py")
    return subprocess.run(
        [sys.executable, script], capture_output=True, text=True, timeout=600, cwd=base
    )


def maybe_publish():
    """Publish automatically when enabled via env (server sets this)."""
    if os.environ.get("COURSEPLAN_AUTO_PUBLISH") == "1":
        return run_publish()
    return None



# ─── Dashboard ────────────────────────────────────────────────────────


@app.route("/")
def dashboard():
    conn = get_db()
    teacher_count = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    course_count = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    semester_count = conn.execute("SELECT COUNT(*) FROM semesters").fetchone()[0]
    offering_count = conn.execute("SELECT COUNT(*) FROM course_offerings").fetchone()[0]
    plan_count = conn.execute("SELECT COUNT(*) FROM weekly_plans").fetchone()[0]
    conn.close()
    return render_template(
        "dashboard.html",
        teacher_count=teacher_count,
        course_count=course_count,
        semester_count=semester_count,
        offering_count=offering_count,
        plan_count=plan_count,
    )


# ─── Teachers ─────────────────────────────────────────────────────────

@app.route("/teachers")
def teacher_list():
    conn = get_db()
    teachers = conn.execute("SELECT * FROM teachers ORDER BY name").fetchall()
    conn.close()
    return render_template("teachers.html", teachers=teachers)


@app.route("/teachers/new", methods=["GET", "POST"])
def teacher_new():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO teachers (name, department, title) VALUES (?, ?, ?)",
            (request.form["name"], request.form["department"], request.form["title"]),
        )
        conn.commit()
        conn.close()
        flash("教师已添加", "success")
        return redirect(url_for("teacher_list"))
    return render_template("teacher_form.html", teacher=None)


@app.route("/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
def teacher_edit(teacher_id):
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "UPDATE teachers SET name=?, department=?, title=? WHERE id=?",
            (request.form["name"], request.form["department"], request.form["title"], teacher_id),
        )
        conn.commit()
        conn.close()
        flash("教师已更新", "success")
        return redirect(url_for("teacher_list"))
    teacher = conn.execute("SELECT * FROM teachers WHERE id=?", (teacher_id,)).fetchone()
    conn.close()
    if not teacher:
        flash("教师不存在", "error")
        return redirect(url_for("teacher_list"))
    return render_template("teacher_form.html", teacher=teacher)


@app.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
def teacher_delete(teacher_id):
    conn = get_db()
    conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    flash("教师已删除", "success")
    return redirect(url_for("teacher_list"))


# ─── Semesters ────────────────────────────────────────────────────────

@app.route("/semesters")
def semester_list():
    conn = get_db()
    semesters = conn.execute("SELECT * FROM semesters ORDER BY name DESC").fetchall()
    conn.close()
    return render_template("semesters.html", semesters=semesters)


@app.route("/semesters/new", methods=["GET", "POST"])
def semester_new():
    if request.method == "POST":
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO semesters (name, academic_year, term) VALUES (?, ?, ?)",
                (request.form["name"], request.form["academic_year"], int(request.form["term"])),
            )
            conn.commit()
            flash("学期已添加", "success")
        except sqlite3.IntegrityError:
            flash("学期名称已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("semester_list"))
    return render_template("semester_form.html", semester=None)


@app.route("/semesters/<int:semester_id>/edit", methods=["GET", "POST"])
def semester_edit(semester_id):
    conn = get_db()
    if request.method == "POST":
        try:
            conn.execute(
                "UPDATE semesters SET name=?, academic_year=?, term=? WHERE id=?",
                (request.form["name"], request.form["academic_year"], int(request.form["term"]), semester_id),
            )
            conn.commit()
            flash("学期已更新", "success")
        except sqlite3.IntegrityError:
            flash("学期名称已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("semester_list"))
    semester = conn.execute("SELECT * FROM semesters WHERE id=?", (semester_id,)).fetchone()
    conn.close()
    if not semester:
        flash("学期不存在", "error")
        return redirect(url_for("semester_list"))
    return render_template("semester_form.html", semester=semester)


@app.route("/semesters/<int:semester_id>/delete", methods=["POST"])
def semester_delete(semester_id):
    conn = get_db()
    conn.execute("DELETE FROM semesters WHERE id=?", (semester_id,))
    conn.commit()
    conn.close()
    flash("学期已删除", "success")
    return redirect(url_for("semester_list"))


# ─── Courses ──────────────────────────────────────────────────────────

@app.route("/courses")
def course_list():
    category = request.args.get("category", "")
    conn = get_db()
    if category:
        courses = conn.execute(
            "SELECT * FROM courses WHERE category=? ORDER BY code", (category,)
        ).fetchall()
    else:
        courses = conn.execute("SELECT * FROM courses ORDER BY code").fetchall()
    categories = [
        "基础必修", "基础选修", "专业方向课", "实验课"
    ]
    conn.close()
    return render_template("courses.html", courses=courses, categories=categories, current_category=category)


@app.route("/courses/new", methods=["GET", "POST"])
def course_new():
    if request.method == "POST":
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO courses (code, name, category, subcategory, department) VALUES (?, ?, ?, ?, ?)",
                (
                    request.form["code"],
                    request.form["name"],
                    request.form["category"],
                    request.form.get("subcategory") or None,
                    request.form.get("department", ""),
                ),
            )
            conn.commit()
            flash("课程已添加", "success")
        except sqlite3.IntegrityError:
            flash("课程代码已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("course_list"))
    return render_template("course_form.html", course=None)


@app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    conn = get_db()
    if request.method == "POST":
        try:
            conn.execute(
                "UPDATE courses SET code=?, name=?, category=?, subcategory=?, department=? WHERE id=?",
                (
                    request.form["code"],
                    request.form["name"],
                    request.form["category"],
                    request.form.get("subcategory") or None,
                    request.form.get("department", ""),
                    course_id,
                ),
            )
            conn.commit()
            flash("课程已更新", "success")
        except sqlite3.IntegrityError:
            flash("课程代码已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("course_list"))
    course = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    conn.close()
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("course_list"))
    return render_template("course_form.html", course=course)


@app.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    conn = get_db()
    conn.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()
    conn.close()
    flash("课程已删除", "success")
    return redirect(url_for("course_list"))


# ─── Course Offerings ─────────────────────────────────────────────────

@app.route("/offerings")
def offering_list():
    course_id = request.args.get("course_id", "")
    teacher_id = request.args.get("teacher_id", "")
    semester_id = request.args.get("semester_id", "")

    conn = get_db()
    query = """
        SELECT co.*, c.code, c.name AS course_name, c.category,
               t.name AS teacher_name, s.name AS semester_name
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        WHERE 1=1
    """
    params = []
    if course_id:
        query += " AND co.course_id = ?"
        params.append(course_id)
    if teacher_id:
        query += " AND co.teacher_id = ?"
        params.append(teacher_id)
    if semester_id:
        query += " AND co.semester_id = ?"
        params.append(semester_id)
    query += " ORDER BY s.name DESC, c.code"

    offerings = conn.execute(query, params).fetchall()
    courses = conn.execute("SELECT id, code, name FROM courses ORDER BY code").fetchall()
    teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
    semesters = conn.execute("SELECT id, name FROM semesters ORDER BY name DESC").fetchall()
    conn.close()

    return render_template(
        "offerings.html",
        offerings=offerings,
        courses=courses,
        teachers=teachers,
        semesters=semesters,
        filter_course=course_id,
        filter_teacher=teacher_id,
        filter_semester=semester_id,
    )


@app.route("/offerings/new", methods=["GET", "POST"])
def offering_new():
    conn = get_db()
    if request.method == "POST":
        try:
            conn.execute(
                """INSERT INTO course_offerings
                   (course_id, teacher_id, semester_id, total_hours, weekly_hours,
                    teaching_weeks, assessment_method, info_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(request.form["course_id"]),
                    int(request.form["teacher_id"]),
                    int(request.form["semester_id"]),
                    int(request.form["total_hours"]),
                    int(request.form["weekly_hours"]),
                    int(request.form["teaching_weeks"]),
                    request.form["assessment_method"],
                    request.form.get("info_source", ""),
                ),
            )
            conn.commit()
            flash("开课记录已添加", "success")
        except sqlite3.IntegrityError:
            flash("该课程-教师-学期组合已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("offering_list"))

    courses = conn.execute("SELECT id, code, name, category FROM courses ORDER BY code").fetchall()
    teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
    semesters = conn.execute("SELECT id, name FROM semesters ORDER BY name DESC").fetchall()
    conn.close()
    return render_template(
        "offering_form.html", offering=None,
        courses=courses, teachers=teachers, semesters=semesters,
    )


@app.route("/offerings/<int:offering_id>/edit", methods=["GET", "POST"])
def offering_edit(offering_id):
    conn = get_db()
    if request.method == "POST":
        try:
            conn.execute(
                """UPDATE course_offerings SET
                   course_id=?, teacher_id=?, semester_id=?, total_hours=?, weekly_hours=?,
                   teaching_weeks=?, assessment_method=?, info_source=?, updated_at=date('now')
                   WHERE id=?""",
                (
                    int(request.form["course_id"]),
                    int(request.form["teacher_id"]),
                    int(request.form["semester_id"]),
                    int(request.form["total_hours"]),
                    int(request.form["weekly_hours"]),
                    int(request.form["teaching_weeks"]),
                    request.form["assessment_method"],
                    request.form.get("info_source", ""),
                    offering_id,
                ),
            )
            conn.commit()
            flash("开课记录已更新", "success")
        except sqlite3.IntegrityError:
            flash("该课程-教师-学期组合已存在", "error")
        finally:
            conn.close()
        return redirect(url_for("offering_list"))

    offering = conn.execute(
        """SELECT co.*, c.code, c.name AS course_name, t.name AS teacher_name, s.name AS semester_name
           FROM course_offerings co
           JOIN courses c ON co.course_id = c.id
           JOIN teachers t ON co.teacher_id = t.id
           JOIN semesters s ON co.semester_id = s.id
           WHERE co.id=?""",
        (offering_id,),
    ).fetchone()

    if not offering:
        conn.close()
        flash("开课记录不存在", "error")
        return redirect(url_for("offering_list"))

    courses = conn.execute("SELECT id, code, name, category FROM courses ORDER BY code").fetchall()
    teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
    semesters = conn.execute("SELECT id, name FROM semesters ORDER BY name DESC").fetchall()
    conn.close()
    return render_template(
        "offering_form.html", offering=offering,
        courses=courses, teachers=teachers, semesters=semesters,
    )


@app.route("/offerings/<int:offering_id>/delete", methods=["POST"])
def offering_delete(offering_id):
    conn = get_db()
    conn.execute("DELETE FROM course_offerings WHERE id=?", (offering_id,))
    conn.commit()
    conn.close()
    flash("开课记录已删除", "success")
    return redirect(url_for("offering_list"))


# ─── Offering Detail (with weekly plans & textbooks) ──────────────────

@app.route("/offerings/<int:offering_id>")
def offering_detail(offering_id):
    conn = get_db()
    offering = conn.execute(
        """SELECT co.*, c.code, c.name AS course_name, c.category, c.subcategory, c.department,
                  t.name AS teacher_name, s.name AS semester_name
           FROM course_offerings co
           JOIN courses c ON co.course_id = c.id
           JOIN teachers t ON co.teacher_id = t.id
           JOIN semesters s ON co.semester_id = s.id
           WHERE co.id=?""",
        (offering_id,),
    ).fetchone()

    if not offering:
        conn.close()
        flash("开课记录不存在", "error")
        return redirect(url_for("offering_list"))

    weekly_plans = conn.execute(
        "SELECT * FROM weekly_plans WHERE offering_id=? ORDER BY week_number",
        (offering_id,),
    ).fetchall()

    textbooks = conn.execute(
        "SELECT * FROM textbooks WHERE offering_id=? ORDER BY sort_order",
        (offering_id,),
    ).fetchall()

    conn.close()
    return render_template(
        "offering_detail.html",
        offering=offering,
        weekly_plans=weekly_plans,
        textbooks=textbooks,
    )


# ─── Weekly Plans (inline in offering detail) ─────────────────────────

@app.route("/offerings/<int:offering_id>/plans/new", methods=["POST"])
def weekly_plan_new(offering_id):
    conn = get_db()
    conn.execute(
        """INSERT INTO weekly_plans (offering_id, week_number, date, hours, teaching_method, content, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            offering_id,
            int(request.form["week_number"]),
            request.form["date"],
            int(request.form["hours"]),
            request.form["teaching_method"],
            request.form["content"],
            request.form.get("notes", ""),
        ),
    )
    conn.commit()
    conn.close()
    flash("教学周期已添加", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


@app.route("/offerings/<int:offering_id>/plans/<int:plan_id>/edit", methods=["POST"])
def weekly_plan_edit(offering_id, plan_id):
    conn = get_db()
    conn.execute(
        """UPDATE weekly_plans SET week_number=?, date=?, hours=?, teaching_method=?, content=?, notes=?
           WHERE id=? AND offering_id=?""",
        (
            int(request.form["week_number"]),
            request.form["date"],
            int(request.form["hours"]),
            request.form["teaching_method"],
            request.form["content"],
            request.form.get("notes", ""),
            plan_id,
            offering_id,
        ),
    )
    conn.commit()
    conn.close()
    flash("教学周期已更新", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


@app.route("/offerings/<int:offering_id>/plans/<int:plan_id>/delete", methods=["POST"])
def weekly_plan_delete(offering_id, plan_id):
    conn = get_db()
    conn.execute("DELETE FROM weekly_plans WHERE id=? AND offering_id=?", (plan_id, offering_id))
    conn.commit()
    conn.close()
    flash("教学周期已删除", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


# ─── Textbooks ────────────────────────────────────────────────────────

@app.route("/offerings/<int:offering_id>/textbooks/new", methods=["POST"])
def textbook_new(offering_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO textbooks (offering_id, type, description, sort_order) VALUES (?, ?, ?, ?)",
        (
            offering_id,
            request.form["type"],
            request.form["description"],
            int(request.form.get("sort_order", 0)),
        ),
    )
    conn.commit()
    conn.close()
    flash("教材已添加", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


@app.route("/offerings/<int:offering_id>/textbooks/<int:textbook_id>/edit", methods=["POST"])
def textbook_edit(offering_id, textbook_id):
    conn = get_db()
    conn.execute(
        "UPDATE textbooks SET type=?, description=?, sort_order=? WHERE id=? AND offering_id=?",
        (
            request.form["type"],
            request.form["description"],
            int(request.form.get("sort_order", 0)),
            textbook_id,
            offering_id,
        ),
    )
    conn.commit()
    conn.close()
    flash("教材已更新", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


@app.route("/offerings/<int:offering_id>/textbooks/<int:textbook_id>/delete", methods=["POST"])
def textbook_delete(offering_id, textbook_id):
    conn = get_db()
    conn.execute("DELETE FROM textbooks WHERE id=? AND offering_id=?", (textbook_id, offering_id))
    conn.commit()
    conn.close()
    flash("教材已删除", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


# ─── Auth routes ──────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if is_admin():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            nxt = request.args.get("next") or request.form.get("next") or url_for("dashboard")
            if not nxt.startswith("/"):
                nxt = url_for("dashboard")
            return redirect(nxt)
        flash("密码错误", "error")
    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("login"))


# ─── Site settings (management mode) ──────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        try:
            mode = int(request.form.get("mode", "1"))
            assert mode in (1, 2, 3)
        except (ValueError, AssertionError):
            flash("无效的管理模式", "error")
            return redirect(url_for("settings_page"))
        set_mode(mode)
        flash(f"管理模式已切换为模式 {mode}", "success")
        return redirect(url_for("settings_page"))
    return render_template("settings.html", mode=current_mode())


# ─── Submissions review queue ─────────────────────────────────────────

@app.route("/submissions")
def submission_list():
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    conn = get_db()
    if status == "all":
        rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    conn.close()
    items = []
    for r in rows:
        try:
            label = json.loads(r["payload"]).get("label", "")
        except Exception:
            label = ""
        items.append({"row": r, "label": label})
    return render_template("submissions.html", items=items, status=status)


@app.route("/submissions/<int:sid>")
def submission_detail(sid):
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not sub:
        flash("提交不存在", "error")
        return redirect(url_for("submission_list"))
    payload = json.loads(sub["payload"])
    before = json.loads(sub["before"]) if sub["before"] else None
    return render_template(
        "submission_detail.html", sub=sub, payload=payload, before=before,
        fields=list(payload.get("fields", {}).items()),
        before_fields=dict(before["fields"].items()) if before else {},
    )


@app.route("/submissions/<int:sid>/approve", methods=["POST"])
def submission_approve(sid):
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id=? AND status='pending'", (sid,)).fetchone()
    if not sub:
        conn.close()
        flash("提交不存在或已处理", "error")
        return redirect(url_for("submission_list"))
    payload = json.loads(sub["payload"])
    try:
        apply_payload(conn, payload)
        conn.execute(
            "UPDATE submissions SET status='approved', reviewed_at=datetime('now','localtime'), review_note=? WHERE id=?",
            (request.form.get("note", ""), sid),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"应用失败: {e}", "error")
        conn.close()
        return redirect(url_for("submission_detail", sid=sid))
    conn.close()
    result = maybe_publish()
    if result and result.returncode != 0:
        flash(f"审核通过，但发布失败:\n{result.stderr[-800:]}", "error")
    else:
        flash("已通过并应用" + ("，已自动发布" if result else "（自动发布未开启，请到「导出/发布」手动发布）"), "success")
    return redirect(url_for("submission_list"))


@app.route("/submissions/<int:sid>/reject", methods=["POST"])
def submission_reject(sid):
    conn = get_db()
    cur = conn.execute(
        "UPDATE submissions SET status='rejected', reviewed_at=datetime('now','localtime'), review_note=? WHERE id=? AND status='pending'",
        (request.form.get("note", ""), sid),
    )
    conn.commit()
    conn.close()
    flash("已驳回" if cur.rowcount else "提交不存在或已处理", "success" if cur.rowcount else "error")
    return redirect(url_for("submission_list"))


# ─── Public editing UI ────────────────────────────────────────────────


def public_locked():
    return current_mode() == 3 and not is_admin()


def rate_limited():
    conn = get_db()
    since = (datetime.now() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    n = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE ip=? AND created_at > ?",
        (request.remote_addr, since),
    ).fetchone()[0]
    conn.close()
    return n >= RATE_LIMIT_MAX_SUBMISSIONS


def submission_blocked():
    return rate_limited()


@app.route("/public/offering/<int:offering_id>", methods=["GET", "POST"])
def public_offering_edit(offering_id):
    if public_locked():
        return render_template("public_locked.html"), 403
    conn = get_db()
    snap = snapshot_offering(conn, offering_id)
    if not snap:
        conn.close()
        flash("开课记录不存在", "error")
        return redirect(url_for("login"))
    mode = current_mode()

    if request.method == "POST":
        if mode == 2 and not is_admin() and submission_blocked():
            conn.close()
            return render_template("public_locked.html", reason="提交太频繁，请稍后再试"), 429

        plans = parse_plans_text(request.form.get("plans", ""))
        books = parse_textbooks_text(request.form.get("textbooks", ""))
        if len(plans) >= MAX_PLANS_PER_SUBMISSION:
            conn.close()
            return render_template("public_locked.html", reason="教学进度行数超出上限"), 400

        fields = {
            "total_hours": int(request.form.get("total_hours") or 0) or None,
            "weekly_hours": int(request.form.get("weekly_hours") or 0) or None,
            "teaching_weeks": int(request.form.get("teaching_weeks") or 0) or None,
            "assessment_method": (request.form.get("assessment_method") or "")[:8000],
            "info_source": (request.form.get("info_source") or "")[:300],
        }
        new_payload = {
            "action": "edit_offering",
            "offering_id": offering_id,
            "label": snap["label"],
            "fields": fields,
            "textbooks": books,
            "weekly_plans": plans,
        }

        if mode == 1 or is_admin():
            try:
                apply_payload(conn, new_payload)
                conn.commit()
            except Exception as e:
                conn.rollback()
                conn.close()
                return render_template("public_done.html", ok=False, message=f"保存失败: {e}"), 500
            conn.close()
            result = maybe_publish()
            msg = "修改已保存"
            if result:
                msg += "并已自动发布" if result.returncode == 0 else "，但自动发布失败，请联系管理员"
            return render_template("public_done.html", ok=True, message=msg)

        # mode 2 → queue a submission
        conn.execute(
            """INSERT INTO submissions
               (action, offering_id, payload, before, submitter_name, submitter_contact, note, ip)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "edit_offering", offering_id,
                json.dumps(new_payload, ensure_ascii=False),
                json.dumps(snap, ensure_ascii=False),
                (request.form.get("submitter_name") or "")[:100],
                (request.form.get("submitter_contact") or "")[:200],
                (request.form.get("note") or "")[:2000],
                request.remote_addr,
            ),
        )
        conn.commit()
        conn.close()
        return render_template(
            "public_done.html", ok=True,
            message="提交成功！管理员审核通过后会发布到网站上，感谢你的贡献。",
        )

    conn.close()
    return render_template(
        "public_offering_form.html",
        snap=snap,
        plans_text=serialize_plans(snap["weekly_plans"]),
        textbooks_text=serialize_textbooks(snap["textbooks"]),
        mode=mode,
    )


@app.route("/public/new/<code>", methods=["GET", "POST"])
def public_offering_new(code):
    if public_locked():
        return render_template("public_locked.html"), 403
    conn = get_db()
    course = conn.execute("SELECT * FROM courses WHERE code=?", (code,)).fetchone()
    if not course:
        conn.close()
        return render_template("public_done.html", ok=False, message="课程不存在"), 404
    semesters = conn.execute("SELECT * FROM semesters ORDER BY name DESC").fetchall()
    mode = current_mode()

    if request.method == "POST":
        teacher_name = (request.form.get("teacher_name") or "").strip()
        semester_name = (request.form.get("semester_name") or "").strip()
        new_semester = (request.form.get("new_semester") or "").strip()
        if new_semester:
            semester_name = new_semester
        if not teacher_name or not semester_name:
            conn.close()
            return render_template("public_done.html", ok=False, message="教师和学期不能为空"), 400

        if mode == 2 and not is_admin() and submission_blocked():
            conn.close()
            return render_template("public_locked.html", reason="提交太频繁，请稍后再试"), 429

        plans = parse_plans_text(request.form.get("plans", ""))
        books = parse_textbooks_text(request.form.get("textbooks", ""))
        fields = {
            "total_hours": int(request.form.get("total_hours") or 0) or None,
            "weekly_hours": int(request.form.get("weekly_hours") or 0) or None,
            "teaching_weeks": int(request.form.get("teaching_weeks") or 0) or None,
            "assessment_method": (request.form.get("assessment_method") or "")[:8000],
            "info_source": (request.form.get("info_source") or "")[:300],
        }
        payload = {
            "action": "create_offering",
            "course_code": code,
            "teacher_name": teacher_name,
            "semester_name": semester_name,
            "label": f"{code} {course['name']} · {teacher_name} · {semester_name}",
            "fields": fields,
            "textbooks": books,
            "weekly_plans": plans,
        }

        if mode == 1 or is_admin():
            try:
                apply_payload(conn, payload)
                conn.commit()
                oid = conn.execute(
                    """SELECT id FROM course_offerings WHERE course_id=(SELECT id FROM courses WHERE code=?)
                       AND teacher_id=(SELECT id FROM teachers WHERE name=?)
                       AND semester_id=(SELECT id FROM semesters WHERE name=?)""",
                    (code, teacher_name, semester_name),
                ).fetchone()["id"]
            except Exception as e:
                conn.rollback()
                conn.close()
                return render_template("public_done.html", ok=False, message=f"保存失败: {e}"), 500
            conn.close()
            result = maybe_publish()
            msg = "新开课记录已添加"
            if result:
                msg += "并已自动发布" if result.returncode == 0 else "，但自动发布失败，请联系管理员"
            return render_template("public_done.html", ok=True, message=msg)

        conn.execute(
            """INSERT INTO submissions
               (action, offering_id, payload, before, submitter_name, submitter_contact, note, ip)
               VALUES (?, NULL, ?, NULL, ?, ?, ?, ?)""",
            (
                "create_offering",
                json.dumps(payload, ensure_ascii=False),
                (request.form.get("submitter_name") or "")[:100],
                (request.form.get("submitter_contact") or "")[:200],
                (request.form.get("note") or "")[:2000],
                request.remote_addr,
            ),
        )
        conn.commit()
        conn.close()
        return render_template(
            "public_done.html", ok=True,
            message="提交成功！管理员审核通过后会发布到网站上，感谢你的贡献。",
        )

    conn.close()
    return render_template(
        "public_new_form.html", course=course, semesters=semesters, mode=mode,
    )


# ─── Publish ──────────────────────────────────────────────────────────

@app.route("/publish", methods=["POST"])
def publish_run():
    result = run_publish()
    if result.returncode == 0:
        flash(f"发布成功\n{(result.stdout or '')[-1200:]}", "success")
    else:
        flash(f"发布失败:\n{(result.stderr or result.stdout or '')[-1200:]}", "error")
    return redirect(url_for("export_page"))


# ─── Export ───────────────────────────────────────────────────────────

@app.route("/export")
def export_page():
    return render_template("export.html")


@app.route("/export/run", methods=["POST"])
def export_run():
    import subprocess
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "export_courses.py",
    )
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            flash(f"导出成功\n{result.stdout}", "success")
        else:
            flash(f"导出失败:\n{result.stderr}", "error")
    except Exception as e:
        flash(f"导出出错: {e}", "error")
    return redirect(url_for("export_page"))


# ─── CSV Import/Export ─────────────────────────────────────────────────

@app.route("/csv")
def csv_page():
    return render_template("csv.html")


@app.route("/csv/export/offerings")
def csv_export_offerings():
    conn = get_db()
    offerings = conn.execute("""
        SELECT c.code, c.name AS course_name, t.name AS teacher_name,
               s.name AS semester_name, co.total_hours, co.weekly_hours,
               co.teaching_weeks, co.assessment_method, co.info_source, co.updated_at
        FROM course_offerings co
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        ORDER BY s.name DESC, c.code
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["课程代码", "课程名称", "任课教师", "学期", "总课时", "周课时", "教学周数", "考核方式", "信息来源", "更新日期"])
    for o in offerings:
        writer.writerow([o[0], o[1], o[2], o[3], o[4], o[5], o[6], o[7], o[8], o[9]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=course_offerings.csv"},
    )


@app.route("/csv/export/weekly-plans/template")
def csv_export_weekly_plan_template():
    """Download a template CSV with headers for weekly plans."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["course_code", "teacher_name", "semester_name", "week_number", "date", "hours", "teaching_method", "content", "notes"])
    writer.writerow(["ENG820", "向明友", "2025-2026-2", "1", "3.11", "2", "研讨", "Introduction", "教师主讲"])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=weekly_plan_template.csv"},
    )


@app.route("/csv/export/weekly-plans")
def csv_export_weekly_plans():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.code, t.name AS teacher_name, s.name AS semester_name,
               wp.week_number, wp.date, wp.hours, wp.teaching_method, wp.content, wp.notes
        FROM weekly_plans wp
        JOIN course_offerings co ON wp.offering_id = co.id
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters s ON co.semester_id = s.id
        ORDER BY s.name DESC, c.code, wp.week_number
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["course_code", "teacher_name", "semester_name", "week_number", "date", "hours", "teaching_method", "content", "notes"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=weekly_plans.csv"},
    )


@app.route("/csv/import/weekly-plans", methods=["POST"])
def csv_import_weekly_plans():
    if "file" not in request.files:
        flash("请选择CSV文件", "error")
        return redirect(url_for("csv_page"))

    file = request.files["file"]
    if file.filename == "":
        flash("请选择CSV文件", "error")
        return redirect(url_for("csv_page"))

    try:
        content = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        conn = get_db()

        imported = 0
        skipped = 0
        for row in reader:
            course_code = row.get("course_code", "").strip()
            teacher_name = row.get("teacher_name", "").strip()
            semester_name = row.get("semester_name", "").strip()

            if not course_code or not teacher_name or not semester_name:
                skipped += 1
                continue

            # Find offering
            offering = conn.execute("""
                SELECT co.id FROM course_offerings co
                JOIN courses c ON co.course_id = c.id
                JOIN teachers t ON co.teacher_id = t.id
                JOIN semesters s ON co.semester_id = s.id
                WHERE c.code=? AND t.name=? AND s.name=?
            """, (course_code, teacher_name, semester_name)).fetchone()

            if not offering:
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO weekly_plans (offering_id, week_number, date, hours, teaching_method, content, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    offering["id"],
                    int(row.get("week_number", 0) or 0),
                    row.get("date", "").strip(),
                    int(row.get("hours", "2") or 2),
                    row.get("teaching_method", "").strip(),
                    row.get("content", "").strip(),
                    row.get("notes", "").strip(),
                ),
            )
            imported += 1

        conn.commit()
        conn.close()
        flash(f"导入完成：{imported} 条成功，{skipped} 条跳过", "success")
    except Exception as e:
        flash(f"导入失败: {e}", "error")

    return redirect(url_for("csv_page"))


@app.route("/offerings/<int:offering_id>/plans/bulk", methods=["POST"])
def weekly_plan_bulk(offering_id):
    text = request.form.get("data", "").strip()
    if not text:
        flash("请输入教学进度数据", "error")
        return redirect(url_for("offering_detail", offering_id=offering_id))

    conn = get_db()
    imported = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", "|").split("|")]
        if len(parts) < 4:
            continue
        try:
            week = int(parts[0])
            date = parts[1]
            hours = int(parts[2]) if len(parts) > 2 and parts[2] else 2
            method = parts[3] if len(parts) > 3 else ""
            content = parts[4] if len(parts) > 4 else ""
            notes = parts[5] if len(parts) > 5 else ""

            conn.execute(
                "INSERT INTO weekly_plans (offering_id, week_number, date, hours, teaching_method, content, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (offering_id, week, date, hours, method, content, notes),
            )
            imported += 1
        except (ValueError, IndexError):
            continue

    conn.commit()
    conn.close()
    flash(f"批量导入完成：{imported} 周", "success")
    return redirect(url_for("offering_detail", offering_id=offering_id))


class PrefixMiddleware:
    """Support running behind a sub-path proxy, e.g. /notebook-admin/ → app."""

    def __init__(self, wsgi_app, prefix=""):
        self.app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if self.prefix and (path == self.prefix or path.startswith(self.prefix + "/")):
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
        return self.app(environ, start_response)


app.wsgi_app = PrefixMiddleware(
    app.wsgi_app, os.environ.get("COURSEPLAN_URL_PREFIX", "")
)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "8766")),
    )
