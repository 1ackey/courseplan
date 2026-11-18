CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT
);

CREATE TABLE IF NOT EXISTS semesters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    academic_year TEXT NOT NULL,
    term INTEGER NOT NULL CHECK(term IN (1, 2))
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('基础必修', '基础选修', '专业方向课', '实验课')),
    subcategory TEXT,
    department TEXT
);

CREATE TABLE IF NOT EXISTS course_offerings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    semester_id INTEGER NOT NULL,
    total_hours INTEGER,
    weekly_hours INTEGER,
    teaching_weeks INTEGER,
    assessment_method TEXT,
    info_source TEXT,
    updated_at TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (teacher_id) REFERENCES teachers(id),
    FOREIGN KEY (semester_id) REFERENCES semesters(id),
    UNIQUE(course_id, teacher_id, semester_id)
);

CREATE TABLE IF NOT EXISTS textbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offering_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('教材', '参考书')),
    description TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (offering_id) REFERENCES course_offerings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weekly_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offering_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    date TEXT,
    hours INTEGER DEFAULT 2,
    teaching_method TEXT,
    content TEXT,
    notes TEXT,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (offering_id) REFERENCES course_offerings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL CHECK(action IN ('create_offering', 'edit_offering', 'delete_offering')),
    offering_id INTEGER,
    payload TEXT NOT NULL,
    before TEXT,
    submitter_name TEXT,
    submitter_contact TEXT,
    note TEXT,
    ip TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    review_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
