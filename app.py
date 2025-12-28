from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3
import hashlib
import os
from openai import OpenAI
from ocr_utils import extract_text

app = Flask(__name__)
app.secret_key = "resume-secret-key"

DB_NAME = "users.db"
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg"}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- DATABASE ----------
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                username TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                filename TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS enhanced_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                resume_filename TEXT NOT NULL,
                job_description TEXT NOT NULL,
                enhanced_resume TEXT NOT NULL,
                cover_letter TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

init_db()

# ---------- HELPERS ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_resumes(email):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            "SELECT filename FROM resumes WHERE email=?",
            (email,)
        )
        return cur.fetchall()

# ---------- PAGES ----------
def get_user_resumes(email):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            "SELECT filename FROM resumes WHERE email=?",
            (email,)
        )
        return cur.fetchall()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup")
def signup_page():
    return render_template("signup.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/upload")
def upload_page():
    if "email" not in session:
        return redirect("/login")
    return render_template("upload.html")

@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        email=session["email"],
        username=session["username"],
        resumes=get_user_resumes(session["email"])
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- API: SIGNUP ----------
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    username = data.get("username")

    if not email or not password or not username:
        return jsonify({"success": False, "message": "All fields required"})

    hashed = hashlib.sha256(password.encode()).hexdigest()

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute(
                "INSERT INTO users (email, password, username) VALUES (?, ?, ?)",
                (email, hashed, username)
            )
        return jsonify({"success": True, "message": "Account created successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Email already registered"})

# ---------- API: LOGIN ----------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    hashed = hashlib.sha256(password.encode()).hexdigest()

    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            "SELECT username, password FROM users WHERE email=?",
            (email,)
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"success": False, "message": "User not found"})

    username, stored_password = row

    if hashed != stored_password:
        return jsonify({"success": False, "message": "Invalid password"})

    session["email"] = email
    session["username"] = username

    return jsonify({"success": True})

# ---------- API: UPLOAD ----------
@app.route("/api/upload", methods=["POST"])
def upload():
    if "email" not in session:
        return jsonify({"success": False, "message": "Unauthorized"})

    file = request.files.get("resume")

    if not file or file.filename == "":
        return jsonify({"success": False, "message": "No file selected"})

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Only PDF or JPG allowed"})

    file.seek(0, os.SEEK_END)
    if file.tell() > MAX_FILE_SIZE:
        return jsonify({"success": False, "message": "File must be under 1MB"})
    file.seek(0)

    filename = session["email"].replace("@", "_") + "_" + file.filename
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "INSERT INTO resumes (email, filename) VALUES (?, ?)",
            (session["email"], filename)
        )

    return jsonify({"success": True})

# ---------- API: AI ENHANCE ----------
@app.route("/api/enhance", methods=["POST"])
def enhance():
    if "email" not in session:
        return jsonify({"success": False, "message": "Unauthorized"})

    data = request.get_json()
    job_desc = data.get("job")
    filename = data.get("filename")

    resume_path = os.path.join(UPLOAD_FOLDER, filename)
    resume_text = extract_text(resume_path)
    resume_text = " ".join(resume_text.split())

    prompt = f"""
You are a professional resume writer.

Rewrite the resume below by:
- Using strong action verbs
- Quantifying achievements
- Making it ATS-friendly
- Tailoring it to the job description

Resume:
{resume_text}

Job Description:
{job_desc}

Return output in this format:

IMPROVED_RESUME:
<text>

COVER_LETTER:
<text>
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    text = response.output_text

    improved = text.split("COVER_LETTER:")[0].replace(
        "IMPROVED_RESUME:", "").strip()
    cover = text.split("COVER_LETTER:")[1].strip()

    return jsonify({
        "success": True,
        "improved_resume": improved,
        "cover_letter": cover
    })

# ---------- API: DELETE RESUME ----------
@app.route("/api/delete_resume", methods=["POST"])
def delete_resume():
    if "email" not in session:
        return jsonify({"success": False})

    filename = request.get_json().get("filename")

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "DELETE FROM resumes WHERE email=? AND filename=?",
            (session["email"], filename)
        )

    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)

    return jsonify({"success": True})

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)
