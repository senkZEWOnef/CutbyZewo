# ✅ Imports
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response, current_app 
from werkzeug.utils import secure_filename
from datetime import datetime
import os, uuid, shutil, glob
from io import BytesIO
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from neon_client import execute_query, execute_single
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
from flask import jsonify
from collections import defaultdict
from dotenv import load_dotenv
import hashlib
import bcrypt

load_dotenv()

# ✅ Flask Init
app = Flask(__name__)
app.secret_key = "Poesie509$$$"  # Consider moving to environment variable for production

# ✅ Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

# ✅ Session helper (Neon-based)
def current_user():
    uid = session.get("user_id")
    
    if not uid:
        return None

    try:
        user = execute_single("SELECT * FROM users WHERE id = %s", (uid,))
        return user
    except Exception as e:
        print("Error fetching user:", e)
        return None

# Password hashing utilities
def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

@app.context_processor
def inject_user():
    return {"user": current_user()}

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        username = request.form.get("username")

        try:
            # Check if user already exists
            existing_user = execute_single("SELECT id FROM users WHERE email = %s", (email,))
            if existing_user:
                flash("User with this email already exists.", "danger")
                return redirect(url_for("signup"))

            # Hash password and create user
            password_hash = hash_password(password)
            
            user_id = execute_single(
                "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (email, username, password_hash)
            )['id']

            # Store session
            session["user_id"] = str(user_id)
            flash("Account created successfully!", "success")
            return redirect(url_for("home"))

        except Exception as e:
            print("Signup error:", e)
            flash("An error occurred during signup. Please try again.", "danger")
            return redirect(url_for("signup"))

    return render_template("signup.html")

@app.route('/api/deadlines')
def get_deadlines():
    if "user_id" not in session:
        return jsonify([])

    user_id = session["user_id"]

    try:
        deadlines_data = execute_query(
            "SELECT * FROM deadlines WHERE user_id = %s",
            (user_id,),
            fetch=True
        )

        deadlines = []
        for d in deadlines_data:
            if d.get("hard_deadline"):
                deadlines.append({
                    "title": d.get("job_name", "Unnamed Job"),
                    "start": d.get("hard_deadline").isoformat() if d.get("hard_deadline") else None
                })

        return jsonify(deadlines)

    except Exception as e:
        print("Error fetching deadlines:", e)
        return jsonify([])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            # Find user by email
            user = execute_single("SELECT id, password_hash FROM users WHERE email = %s", (email,))
            
            if not user:
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

            # Verify password
            if not verify_password(password, user['password_hash']):
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

            # Store user_id in session
            session["user_id"] = str(user['id'])
            flash("Logged in successfully!", "success")
            return redirect(url_for("home"))

        except Exception as e:
            print("Login error:", e)
            flash("An error occurred during login. Please try again.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

@app.route("/calendar")
def calendar():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    try:
        # Get this user's jobs
        jobs_data = execute_query(
            "SELECT id, client_name FROM jobs WHERE user_id = %s",
            (user_id,),
            fetch=True
        )
        job_ids = [j["id"] for j in jobs_data]
        job_name_map = {str(j["id"]): j["client_name"] or "Unnamed Job" for j in jobs_data}

        # Get deadlines for those jobs
        deadlines = []
        if job_ids:
            # Convert UUIDs to strings for the IN clause
            job_ids_str = [str(jid) for jid in job_ids]
            deadlines = execute_query(
                f"SELECT * FROM deadlines WHERE job_id = ANY(%s)",
                (job_ids_str,),
                fetch=True
            )

        # Build calendar events
        events = []
        for d in deadlines:
            job_id = str(d["job_id"])
            if job_id not in job_name_map:
                continue

            job_name = job_name_map.get(job_id, "Unnamed Job")

            if d.get("soft_deadline"):
                events.append({
                    "title": f"🟡 {job_name} (Soft)",
                    "start": d["soft_deadline"].isoformat(),
                    "color": "#ffc107",
                })

            if d.get("hard_deadline"):
                events.append({
                    "title": f"🔴 {job_name} (Hard)",
                    "start": d["hard_deadline"].isoformat(),
                    "color": "#dc3545",
                })

        return render_template("calendar.html", calendar_events=events)

    except Exception as e:
        print("Error loading calendar:", e)
        flash("Could not load calendar.", "warning")
        return redirect(url_for("home"))

@app.route("/", methods=["GET"])
def home():
    user_id = session.get("user_id")
    
    upcoming_deadlines = []
    recent_jobs = []
    stats = {
        "total_jobs": 0,
        "total_revenue": 0.0,
        "pending_quotes": 0,
        "urgent_jobs": 0,
        "completed_jobs": 0,
        "in_progress_jobs": 0
    }

    if user_id:
        try:
            # Get all jobs for statistics
            all_jobs = execute_query(
                "SELECT id, client_name, final_price, status, created_at FROM jobs WHERE user_id = %s",
                (user_id,),
                fetch=True
            )
            
            # Calculate statistics
            stats["total_jobs"] = len(all_jobs)
            stats["total_revenue"] = sum(float(job.get("final_price", 0) or 0) for job in all_jobs)
            stats["pending_quotes"] = len([job for job in all_jobs if not job.get("final_price")])
            stats["completed_jobs"] = len([job for job in all_jobs if job.get("status") == "completed"])
            stats["in_progress_jobs"] = len([job for job in all_jobs if job.get("status") == "in_progress"])

            # Get hard deadlines for urgent jobs calculation
            deadlines = execute_query(
                "SELECT job_id, hard_deadline FROM deadlines WHERE user_id = %s AND hard_deadline IS NOT NULL ORDER BY hard_deadline",
                (user_id,),
                fetch=True
            )
            
            # Calculate urgent jobs (within 3 days)
            from datetime import datetime, timedelta
            today = datetime.now().date()
            urgent_threshold = today + timedelta(days=3)
            
            urgent_job_ids = []
            for deadline in deadlines:
                if deadline.get("hard_deadline"):
                    deadline_date = deadline["hard_deadline"]
                    if isinstance(deadline_date, str):
                        deadline_date = datetime.fromisoformat(deadline_date.replace('Z', '+00:00')).date()
                    if deadline_date <= urgent_threshold:
                        urgent_job_ids.append(str(deadline["job_id"]))
            
            stats["urgent_jobs"] = len(urgent_job_ids)
            
            # Get upcoming deadlines for dashboard display (top 5)
            upcoming_deadlines = []
            for deadline in deadlines[:5]:
                try:
                    job_data = next((job for job in all_jobs if str(job["id"]) == str(deadline["job_id"])), None)
                    if job_data:
                        upcoming_deadlines.append({
                            "job_id": deadline["job_id"],
                            "hard_deadline": deadline["hard_deadline"],
                            "jobs": {"client_name": job_data["client_name"]}
                        })
                except:
                    continue

            # Get recent jobs for dashboard display (top 5 most recent)
            recent_jobs = []
            sorted_jobs = sorted(all_jobs, key=lambda x: x.get("created_at", datetime.min), reverse=True)
            for job in sorted_jobs[:5]:
                recent_jobs.append({
                    "id": job["id"],
                    "client_name": job["client_name"],
                    "status": job.get("status", "draft"),
                    "created_at": job["created_at"]
                })

        except Exception as e:
            print("Error loading home page:", e)

    # Provide current date for templates
    current_date = datetime.now().date()
    
    return render_template("landing.html", jobs=upcoming_deadlines, recent_jobs=recent_jobs, stats=stats, current_date=current_date)

@app.route("/create-job", methods=["GET", "POST"])
def create_job():
    if "user_id" not in session:
        flash("Please log in to create a job.", "warning")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        client_name = request.form.get("client_name")
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")
        thicknesses = request.form.getlist("thicknesses")

        soft_deadline = request.form.get("soft_deadline") or None
        hard_deadline = request.form.get("hard_deadline") or None
        soft_deadline = datetime.strptime(soft_deadline, "%Y-%m-%d").date() if soft_deadline else None
        hard_deadline = datetime.strptime(hard_deadline, "%Y-%m-%d").date() if hard_deadline else None

        # Process parts in order while maintaining sheets by thickness
        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))
        
        job_uuid = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_uuid}"
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Create job
            execute_query(
                "INSERT INTO jobs (id, client_name, user_id) VALUES (%s, %s, %s)",
                (job_uuid, client_name, user_id)
            )
        except Exception as e:
            print("Job insert error:", e)
            flash("Job creation failed. Try again.", "danger")
            return redirect(url_for("create_job"))

        # Track active sheets for each thickness
        sheets_by_thickness = {}
        all_parts = []
        
        # Process parts in the order they were entered
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                # Add each part (respecting quantity) to the thickness-specific optimization
                parts_for_thickness = [(float(w), float(h))] * int(q)
                all_parts.extend([(float(w), float(h), t) for _ in range(int(q))])
                
                if t not in sheets_by_thickness:
                    sheets_by_thickness[t] = []
                
                # Optimize this thickness incrementally with new parts
                current_parts = [p[:2] for p in all_parts if p[2] == t]  # Get all parts for this thickness so far
                sheets_by_thickness[t] = optimize_cuts(panel_width, panel_height, current_parts)

        # Generate images and collect paths
        sheet_images = []
        for t, sheets in sheets_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            draw_sheets_to_files(sheets, subfolder)

            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append((rel, t))

        # Insert all parts into database
        try:
            for w, h, t in all_parts:
                execute_query(
                    "INSERT INTO parts (job_id, width, height, material) VALUES (%s, %s, %s, %s)",
                    (job_uuid, w, h, t)
                )
        except Exception as e:
            print("Parts insert error:", e)
            flash("Failed to insert parts.", "warning")

        if soft_deadline or hard_deadline:
            try:
                execute_query(
                    "INSERT INTO deadlines (job_id, user_id, soft_deadline, hard_deadline) VALUES (%s, %s, %s, %s)",
                    (job_uuid, user_id, soft_deadline, hard_deadline)
                )
            except Exception as e:
                print("Deadline insert error:", e)
                flash("Failed to save deadlines.", "warning")

        # Handle file uploads - save to local storage
        if 'job_files' in request.files:
            files = request.files.getlist('job_files')
            upload_dir = f"static/uploads/{job_uuid}"
            os.makedirs(upload_dir, exist_ok=True)
            
            for f in files:
                if f.filename:
                    filename = secure_filename(f.filename)
                    file_path = os.path.join(upload_dir, filename)
                    f.save(file_path)
                    
                    # Save file record to database
                    try:
                        execute_query(
                            "INSERT INTO files (job_id, filename, storage_path, user_id) VALUES (%s, %s, %s, %s)",
                            (job_uuid, filename, file_path, user_id)
                        )
                    except Exception as e:
                        print("Error saving file record:", e)

        return render_template(
            "result.html",
            parts=all_parts,
            sheet_images=sheet_images,
            job_id=job_uuid
        )

    return render_template("index.html")

# Continue with other routes...
@app.route("/jobs")
def jobs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    try:
        # Jobs for this user
        job_data = execute_query(
            "SELECT id, client_name, final_price, status, created_at FROM jobs WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
            fetch=True
        )
        job_ids = [str(j["id"]) for j in job_data]

        # Parts aggregation
        counts = {jid: {"3/4": 0, "1/2": 0, "1/4": 0, "Other": 0, "total": 0} for jid in job_ids}
        if job_ids:
            parts_data = execute_query(
                f"SELECT job_id, material FROM parts WHERE job_id = ANY(%s)",
                (job_ids,),
                fetch=True
            )
            for p in parts_data:
                jid = str(p.get("job_id"))
                mat = (p.get("material") or "").strip()
                key = mat if mat in ("3/4", "1/2", "1/4") else "Other"
                if jid in counts:
                    counts[jid][key] += 1
                    counts[jid]["total"] += 1

        # Attach counts to each job
        for j in job_data:
            j["part_counts"] = counts.get(str(j["id"]), {"3/4": 0, "1/2": 0, "1/4": 0, "Other": 0, "total": 0})

        current_date = datetime.now().date()
        return render_template("jobs.html", jobs=job_data, current_date=current_date)

    except Exception as e:
        print("Error loading jobs:", e)
        flash("Could not load jobs. Please try again later.", "danger")
        return redirect(url_for("home"))

@app.route("/help")
def help():
    return render_template("help.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)