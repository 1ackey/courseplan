#!/usr/bin/env python3
"""Flask admin panel for CoursePlan database management."""
import csv
import io
import os
import sys
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, flash, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import DB_PATH

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "courseplan-admin-secret-key")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
