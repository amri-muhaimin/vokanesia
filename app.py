from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from flask import Flask, g, redirect, render_template, request, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "data.db")

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def exec_script(db: sqlite3.Connection, sql: str) -> None:
    db.executescript(sql)
    db.commit()


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schools (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  city TEXT
);

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sector TEXT,
  city TEXT
);

CREATE TABLE IF NOT EXISTS competencies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT
);

-- curriculum items are owned by a school+program
CREATE TABLE IF NOT EXISTS curriculum_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id INTEGER NOT NULL,
  program TEXT NOT NULL,
  competency_id INTEGER NOT NULL,
  target_level INTEGER NOT NULL CHECK(target_level BETWEEN 1 AND 5),
  FOREIGN KEY(school_id) REFERENCES schools(id) ON DELETE CASCADE,
  FOREIGN KEY(competency_id) REFERENCES competencies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  city TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS role_requirements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_id INTEGER NOT NULL,
  competency_id INTEGER NOT NULL,
  min_level INTEGER NOT NULL CHECK(min_level BETWEEN 1 AND 5),
  required INTEGER NOT NULL CHECK(required IN (0,1)),
  FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE,
  FOREIGN KEY(competency_id) REFERENCES competencies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  school_id INTEGER NOT NULL,
  program TEXT NOT NULL,
  city TEXT,
  availability TEXT,
  about TEXT,
  FOREIGN KEY(school_id) REFERENCES schools(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_skills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  competency_id INTEGER NOT NULL,
  level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 5),
  verified INTEGER NOT NULL CHECK(verified IN (0,1)),
  FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY(competency_id) REFERENCES competencies(id) ON DELETE CASCADE,
  UNIQUE(student_id, competency_id)
);

CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  type TEXT,
  FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  role_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'applied',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE,
  UNIQUE(student_id, role_id)
);
"""


def seed_if_empty(db: sqlite3.Connection) -> None:
    # if already seeded, do nothing
    cur = db.execute("SELECT COUNT(*) AS c FROM schools")
    if cur.fetchone()["c"] > 0:
        return

    # Schools
    db.execute("INSERT INTO schools (name, city) VALUES (?,?)", ("SMK Negeri 1 Jakarta", "Jakarta"))
    db.execute("INSERT INTO schools (name, city) VALUES (?,?)", ("SMK Telkom Bandung", "Bandung"))

    # Companies (DUDI)
    db.execute("INSERT INTO companies (name, sector, city) VALUES (?,?,?)", ("PT Nusantara Tech", "Software / IT Services", "Jakarta"))
    db.execute("INSERT INTO companies (name, sector, city) VALUES (?,?,?)", ("Bali Manufacturing", "Manufacturing", "Denpasar"))
    db.execute("INSERT INTO companies (name, sector, city) VALUES (?,?,?)", ("Surabaya Automation Labs", "Industrial Automation", "Surabaya"))

    # Competencies (a shared language)
    comps = [
        ("HTML", "Web Development"),
        ("CSS", "Web Development"),
        ("JavaScript", "Web Development"),
        ("SQL", "Data & Databases"),
        ("Git Basics", "Tools"),
        ("UI/UX Basics", "Design"),
        ("Communication", "Soft Skills"),
        ("Teamwork", "Soft Skills"),
        ("PLC Basics", "Industrial Automation"),
        ("Sensor & Actuator Basics", "Industrial Automation"),
        ("CNC Basics", "Manufacturing"),
        ("Safety (K3)", "Manufacturing"),
    ]
    for name, cat in comps:
        db.execute("INSERT INTO competencies (name, category) VALUES (?,?)", (name, cat))

    # Curriculum items (school POV)
    # Map some competencies to programs and target levels (1-5)
    # school_id 1: SMK Negeri 1 Jakarta, program RPL
    cur_items = [
        (1, "RPL (Software Engineering)", "HTML", 4),
        (1, "RPL (Software Engineering)", "CSS", 4),
        (1, "RPL (Software Engineering)", "JavaScript", 3),
        (1, "RPL (Software Engineering)", "SQL", 3),
        (1, "RPL (Software Engineering)", "Git Basics", 3),
        (1, "RPL (Software Engineering)", "Communication", 3),
        (1, "RPL (Software Engineering)", "Teamwork", 3),
        # school_id 2: SMK Telkom Bandung, program TKJ
        (2, "TKJ (Computer & Network)", "SQL", 2),
        (2, "TKJ (Computer & Network)", "Git Basics", 2),
        (2, "TKJ (Computer & Network)", "Communication", 3),
        (2, "TKJ (Computer & Network)", "Teamwork", 3),
        # automation program example
        (2, "Mechatronics", "PLC Basics", 3),
        (2, "Mechatronics", "Sensor & Actuator Basics", 3),
        (2, "Mechatronics", "Safety (K3)", 4),
    ]
    # helper: get competency_id by name
    comp_map = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM competencies").fetchall()}
    for school_id, program, comp_name, target_level in cur_items:
        db.execute(
            "INSERT INTO curriculum_items (school_id, program, competency_id, target_level) VALUES (?,?,?,?)",
            (school_id, program, comp_map[comp_name], target_level),
        )

    # Industry roles + requirements (industry POV)
    roles = [
        (1, "Web Intern (Frontend)", "Build and improve simple web pages. Work with UI components and basic APIs.", "Jakarta"),
        (1, "Junior Data Assistant", "Help clean data, write simple SQL queries, and create basic reports.", "Jakarta"),
        (2, "CNC Operator Trainee", "Assist in CNC setup, basic operation, and safety procedures.", "Denpasar"),
        (3, "PLC Technician Intern", "Support PLC wiring, sensor checks, and basic troubleshooting with a mentor.", "Surabaya"),
    ]
    for company_id, title, desc, city in roles:
        db.execute("INSERT INTO roles (company_id, title, description, city) VALUES (?,?,?,?)", (company_id, title, desc, city))

    role_ids = {row["title"]: row["id"] for row in db.execute("SELECT id, title FROM roles").fetchall()}

    reqs = [
        # Web Intern
        ("Web Intern (Frontend)", "HTML", 3, 1),
        ("Web Intern (Frontend)", "CSS", 3, 1),
        ("Web Intern (Frontend)", "JavaScript", 2, 1),
        ("Web Intern (Frontend)", "Git Basics", 2, 0),
        ("Web Intern (Frontend)", "UI/UX Basics", 2, 0),
        ("Web Intern (Frontend)", "Communication", 3, 0),

        # Data Assistant
        ("Junior Data Assistant", "SQL", 3, 1),
        ("Junior Data Assistant", "Communication", 3, 1),
        ("Junior Data Assistant", "Teamwork", 3, 0),

        # CNC
        ("CNC Operator Trainee", "CNC Basics", 2, 1),
        ("CNC Operator Trainee", "Safety (K3)", 3, 1),
        ("CNC Operator Trainee", "Teamwork", 3, 0),

        # PLC
        ("PLC Technician Intern", "PLC Basics", 3, 1),
        ("PLC Technician Intern", "Sensor & Actuator Basics", 2, 1),
        ("PLC Technician Intern", "Safety (K3)", 3, 1),
        ("PLC Technician Intern", "Communication", 3, 0),
    ]
    for role_title, comp_name, min_level, required in reqs:
        db.execute(
            "INSERT INTO role_requirements (role_id, competency_id, min_level, required) VALUES (?,?,?,?)",
            (role_ids[role_title], comp_map[comp_name], min_level, required),
        )

    # Students + skills (student POV)
    students = [
        (1, "Ayu Pratama", 1, "RPL (Software Engineering)", "Jakarta", "Jun–Aug", "Frontend-focused, likes UI work and teamwork."),
        (2, "Bagus Santoso", 1, "RPL (Software Engineering)", "Bekasi", "Jul–Sep", "Interested in databases and reporting, careful and detail-oriented."),
        (3, "Citra Maharani", 2, "Mechatronics", "Surabaya", "Jun–Aug", "Hands-on learner, interested in automation and maintenance."),
        (4, "Dewa Putra", 2, "Mechatronics", "Denpasar", "Jun–Aug", "Interested in manufacturing and safety-first work environments."),
    ]
    for _, name, school_id, program, city, avail, about in students:
        db.execute(
            "INSERT INTO students (name, school_id, program, city, availability, about) VALUES (?,?,?,?,?,?)",
            (name, school_id, program, city, avail, about),
        )

    student_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM students").fetchall()}

    skills = [
        ("Ayu Pratama", "HTML", 4, 1),
        ("Ayu Pratama", "CSS", 4, 1),
        ("Ayu Pratama", "JavaScript", 3, 0),
        ("Ayu Pratama", "Git Basics", 3, 1),
        ("Ayu Pratama", "UI/UX Basics", 3, 0),
        ("Ayu Pratama", "Communication", 4, 1),
        ("Ayu Pratama", "Teamwork", 4, 1),

        ("Bagus Santoso", "SQL", 4, 1),
        ("Bagus Santoso", "JavaScript", 2, 0),
        ("Bagus Santoso", "Git Basics", 2, 1),
        ("Bagus Santoso", "Communication", 3, 1),
        ("Bagus Santoso", "Teamwork", 3, 1),

        ("Citra Maharani", "PLC Basics", 4, 1),
        ("Citra Maharani", "Sensor & Actuator Basics", 3, 1),
        ("Citra Maharani", "Safety (K3)", 4, 1),
        ("Citra Maharani", "Communication", 3, 1),
        ("Citra Maharani", "Teamwork", 4, 1),

        ("Dewa Putra", "CNC Basics", 3, 1),
        ("Dewa Putra", "Safety (K3)", 4, 1),
        ("Dewa Putra", "Teamwork", 4, 1),
        ("Dewa Putra", "Communication", 3, 1),
    ]
    for student_name, comp_name, level, verified in skills:
        db.execute(
            "INSERT INTO student_skills (student_id, competency_id, level, verified) VALUES (?,?,?,?)",
            (student_ids[student_name], comp_map[comp_name], level, verified),
        )

    evidence_rows = [
        ("Ayu Pratama", "Portfolio: Simple Landing Page", "https://example.com/ayu-landing", "Portfolio"),
        ("Ayu Pratama", "Certificate: Basic Git", "https://example.com/ayu-git", "Certificate"),
        ("Bagus Santoso", "Mini Project: Sales Report (SQL)", "https://example.com/bagus-sql", "Project"),
        ("Citra Maharani", "Workshop: PLC Ladder Basics", "https://example.com/citra-plc", "Workshop"),
        ("Dewa Putra", "Safety Training (K3) Badge", "https://example.com/dewa-k3", "Certificate"),
    ]
    for student_name, title, url, typ in evidence_rows:
        db.execute(
            "INSERT INTO evidence (student_id, title, url, type) VALUES (?,?,?,?)",
            (student_ids[student_name], title, url, typ),
        )

    # A couple of example applications
    db.execute(
        "INSERT INTO applications (student_id, role_id, status) VALUES (?,?,?)",
        (student_ids["Ayu Pratama"], role_ids["Web Intern (Frontend)"], "applied"),
    )
    db.execute(
        "INSERT INTO applications (student_id, role_id, status) VALUES (?,?,?)",
        (student_ids["Citra Maharani"], role_ids["PLC Technician Intern"], "shortlisted"),
    )

    db.commit()


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    exec_script(db, SCHEMA_SQL)
    seed_if_empty(db)
    db.close()


def fetch_all(db: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    return db.execute(sql, params).fetchall()


def fetch_one(db: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return db.execute(sql, params).fetchone()


def get_student_skill_map(db: sqlite3.Connection, student_id: int) -> Dict[int, Dict[str, Any]]:
    rows = fetch_all(
        db,
        """
        SELECT ss.competency_id, ss.level, ss.verified, c.name AS competency_name, c.category
        FROM student_skills ss
        JOIN competencies c ON c.id = ss.competency_id
        WHERE ss.student_id = ?
        """,
        (student_id,),
    )
    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        out[int(r["competency_id"])] = {
            "level": int(r["level"]),
            "verified": int(r["verified"]),
            "name": r["competency_name"],
            "category": r["category"],
        }
    return out


def get_role_requirements(db: sqlite3.Connection, role_id: int) -> List[Dict[str, Any]]:
    rows = fetch_all(
        db,
        """
        SELECT rr.competency_id, rr.min_level, rr.required, c.name AS competency_name, c.category
        FROM role_requirements rr
        JOIN competencies c ON c.id = rr.competency_id
        WHERE rr.role_id = ?
        ORDER BY rr.required DESC, c.category ASC, c.name ASC
        """,
        (role_id,),
    )
    return [
        {
            "competency_id": int(r["competency_id"]),
            "min_level": int(r["min_level"]),
            "required": int(r["required"]),
            "name": r["competency_name"],
            "category": r["category"],
        }
        for r in rows
    ]


def compute_match_score(
    student_city: str | None,
    role_city: str | None,
    student_skills: Dict[int, Dict[str, Any]],
    requirements: List[Dict[str, Any]],
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Returns (score_0_to_100, gaps)
    gaps: list of {name, required, needed_level, student_level}
    """
    score = 50  # start neutral
    gaps: List[Dict[str, Any]] = []

    # location bonus (very simple)
    if student_city and role_city and student_city.strip().lower() == role_city.strip().lower():
        score += 10

    for req in requirements:
        cid = req["competency_id"]
        needed = req["min_level"]
        is_required = req["required"] == 1

        s = student_skills.get(cid)
        student_level = s["level"] if s else 0
        verified = (s["verified"] == 1) if s else False

        if student_level >= needed:
            score += 12 if is_required else 6
            if verified:
                score += 2
        else:
            if is_required:
                score -= 18
            else:
                score -= 4
            gaps.append(
                {
                    "name": req["name"],
                    "required": is_required,
                    "needed_level": needed,
                    "student_level": student_level,
                }
            )

    # clamp
    if score < 0:
        score = 0
    if score > 100:
        score = 100
    return score, gaps


@app.route("/")
def home():
    db = get_db()
    stats = {
        "schools": fetch_one(db, "SELECT COUNT(*) AS c FROM schools")["c"],
        "companies": fetch_one(db, "SELECT COUNT(*) AS c FROM companies")["c"],
        "students": fetch_one(db, "SELECT COUNT(*) AS c FROM students")["c"],
        "roles": fetch_one(db, "SELECT COUNT(*) AS c FROM roles")["c"],
        "competencies": fetch_one(db, "SELECT COUNT(*) AS c FROM competencies")["c"],
    }
    return render_template("home.html", stats=stats)


@app.route("/schools")
def schools():
    db = get_db()
    rows = fetch_all(db, "SELECT * FROM schools ORDER BY name ASC")
    return render_template("schools.html", schools=rows)


@app.route("/school/<int:school_id>/curriculum")
def curriculum(school_id: int):
    db = get_db()
    school = fetch_one(db, "SELECT * FROM schools WHERE id = ?", (school_id,))
    if not school:
        return render_template("not_found.html", title="School not found"), 404

    items = fetch_all(
        db,
        """
        SELECT ci.program, c.name AS competency_name, c.category, ci.target_level
        FROM curriculum_items ci
        JOIN competencies c ON c.id = ci.competency_id
        WHERE ci.school_id = ?
        ORDER BY ci.program ASC, c.category ASC, c.name ASC
        """,
        (school_id,),
    )
    # group by program
    grouped: Dict[str, List[Any]] = {}
    for r in items:
        grouped.setdefault(r["program"], []).append(r)
    return render_template("curriculum.html", school=school, grouped=grouped)


@app.route("/companies")
def companies():
    db = get_db()
    rows = fetch_all(db, "SELECT * FROM companies ORDER BY name ASC")
    return render_template("companies.html", companies=rows)


@app.route("/roles")
def roles():
    db = get_db()
    rows = fetch_all(
        db,
        """
        SELECT r.*, c.name AS company_name, c.sector
        FROM roles r
        JOIN companies c ON c.id = r.company_id
        ORDER BY r.title ASC
        """,
    )
    return render_template("roles.html", roles=rows)


@app.route("/roles/<int:role_id>")
def role_detail(role_id: int):
    db = get_db()
    role = fetch_one(
        db,
        """
        SELECT r.*, c.name AS company_name, c.sector, c.city AS company_city
        FROM roles r
        JOIN companies c ON c.id = r.company_id
        WHERE r.id = ?
        """,
        (role_id,),
    )
    if not role:
        return render_template("not_found.html", title="Role not found"), 404

    requirements = get_role_requirements(db, role_id)
    return render_template("role_detail.html", role=role, requirements=requirements)


@app.route("/students")
def students():
    db = get_db()
    rows = fetch_all(
        db,
        """
        SELECT s.*, sc.name AS school_name
        FROM students s
        JOIN schools sc ON sc.id = s.school_id
        ORDER BY s.name ASC
        """,
    )
    return render_template("students.html", students=rows)


@app.route("/students/<int:student_id>")
def student_detail(student_id: int):
    db = get_db()
    student = fetch_one(
        db,
        """
        SELECT s.*, sc.name AS school_name, sc.city AS school_city
        FROM students s
        JOIN schools sc ON sc.id = s.school_id
        WHERE s.id = ?
        """,
        (student_id,),
    )
    if not student:
        return render_template("not_found.html", title="Student not found"), 404

    skills = fetch_all(
        db,
        """
        SELECT c.name AS competency_name, c.category, ss.level, ss.verified
        FROM student_skills ss
        JOIN competencies c ON c.id = ss.competency_id
        WHERE ss.student_id = ?
        ORDER BY c.category ASC, c.name ASC
        """,
        (student_id,),
    )
    evidence = fetch_all(db, "SELECT * FROM evidence WHERE student_id = ? ORDER BY id DESC", (student_id,))
    return render_template("student_detail.html", student=student, skills=skills, evidence=evidence)


@app.route("/match/role/<int:role_id>")
def match_role(role_id: int):
    db = get_db()
    role = fetch_one(
        db,
        """
        SELECT r.*, c.name AS company_name, c.sector
        FROM roles r
        JOIN companies c ON c.id = r.company_id
        WHERE r.id = ?
        """,
        (role_id,),
    )
    if not role:
        return render_template("not_found.html", title="Role not found"), 404

    requirements = get_role_requirements(db, role_id)
    students_rows = fetch_all(
        db,
        """
        SELECT s.*, sc.name AS school_name
        FROM students s
        JOIN schools sc ON sc.id = s.school_id
        ORDER BY s.name ASC
        """,
    )

    ranked = []
    for st in students_rows:
        skill_map = get_student_skill_map(db, int(st["id"]))
        score, gaps = compute_match_score(st["city"], role["city"], skill_map, requirements)
        ranked.append({"student": st, "score": score, "gaps": gaps})

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return render_template("match_role.html", role=role, requirements=requirements, ranked=ranked)


@app.route("/match/student/<int:student_id>")
def match_student(student_id: int):
    db = get_db()
    student = fetch_one(
        db,
        """
        SELECT s.*, sc.name AS school_name
        FROM students s
        JOIN schools sc ON sc.id = s.school_id
        WHERE s.id = ?
        """,
        (student_id,),
    )
    if not student:
        return render_template("not_found.html", title="Student not found"), 404

    roles_rows = fetch_all(
        db,
        """
        SELECT r.*, c.name AS company_name, c.sector
        FROM roles r
        JOIN companies c ON c.id = r.company_id
        ORDER BY r.title ASC
        """,
    )

    student_skills = get_student_skill_map(db, int(student_id))
    ranked = []
    for role in roles_rows:
        requirements = get_role_requirements(db, int(role["id"]))
        score, gaps = compute_match_score(student["city"], role["city"], student_skills, requirements)
        ranked.append({"role": role, "score": score, "gaps": gaps})

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return render_template("match_student.html", student=student, ranked=ranked)


@app.route("/admin/reset")
def admin_reset():
    # dev-only utility: delete DB and recreate
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    return redirect(url_for("home"))


# Initialize DB at startup
init_db()

if __name__ == "__main__":
    app.run(debug=True)
