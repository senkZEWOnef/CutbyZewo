# ✅ Complete Neon-based Flask Application
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response, current_app 
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
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
from local_storage_manager import LocalStorageManager
import hashlib
import bcrypt

load_dotenv()

# ✅ Flask Init
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

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

@app.context_processor
def expose_helpers():
    return {"has_endpoint": lambda name: name in app.view_functions}

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        username = request.form.get("username")

        try:
            existing_user = execute_single("SELECT id FROM users WHERE email = %s", (email,))
            if existing_user:
                flash("User with this email already exists.", "danger")
                return redirect(url_for("signup"))

            password_hash = hash_password(password)
            
            user_id = execute_single(
                "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (email, username, password_hash)
            )['id']

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
            user = execute_single("SELECT id, password_hash FROM users WHERE email = %s", (email,))
            
            if not user:
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

            if not verify_password(password, user['password_hash']):
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

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
        jobs_data = execute_query(
            "SELECT id, client_name FROM jobs WHERE user_id = %s",
            (user_id,),
            fetch=True
        )
        job_ids = [str(j["id"]) for j in jobs_data]
        job_name_map = {str(j["id"]): j["client_name"] or "Unnamed Job" for j in jobs_data}

        deadlines = []
        if job_ids:
            # Use IN clause instead of ANY for better compatibility
            placeholders = ','.join(['%s'] * len(job_ids))
            deadlines = execute_query(
                f"SELECT * FROM deadlines WHERE job_id::text IN ({placeholders})",
                tuple(job_ids),
                fetch=True
            )

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
            all_jobs = execute_query(
                "SELECT id, client_name, final_price, status, created_at FROM jobs WHERE user_id = %s",
                (user_id,),
                fetch=True
            )
            
            stats["total_jobs"] = len(all_jobs)
            stats["total_revenue"] = sum(float(job.get("final_price", 0) or 0) for job in all_jobs)
            stats["pending_quotes"] = len([job for job in all_jobs if not job.get("final_price")])
            stats["completed_jobs"] = len([job for job in all_jobs if job.get("status") == "completed"])
            stats["in_progress_jobs"] = len([job for job in all_jobs if job.get("status") == "in_progress"])

            deadlines = execute_query(
                "SELECT job_id, hard_deadline FROM deadlines WHERE user_id = %s AND hard_deadline IS NOT NULL ORDER BY hard_deadline",
                (user_id,),
                fetch=True
            )
            
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

        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))
        
        job_uuid = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_uuid}"
        os.makedirs(output_dir, exist_ok=True)

        try:
            execute_query(
                "INSERT INTO jobs (id, client_name, user_id) VALUES (%s, %s, %s)",
                (job_uuid, client_name, user_id)
            )
        except Exception as e:
            print("Job insert error:", e)
            flash("Job creation failed. Try again.", "danger")
            return redirect(url_for("create_job"))

        sheets_by_thickness = {}
        all_parts = []
        
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                parts_for_thickness = [(float(w), float(h))] * int(q)
                all_parts.extend([(float(w), float(h), t) for _ in range(int(q))])
                
                if t not in sheets_by_thickness:
                    sheets_by_thickness[t] = []
                
                current_parts = [p[:2] for p in all_parts if p[2] == t]
                sheets_by_thickness[t] = optimize_cuts(panel_width, panel_height, current_parts)

        sheet_images = []
        for t, sheets in sheets_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            draw_sheets_to_files(sheets, subfolder)

            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append((rel, t))

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

        if 'job_files' in request.files:
            files = request.files.getlist('job_files')
            for f in files:
                if f.filename:
                    storage_path = LocalStorageManager.upload_file(f, job_uuid)
                    if storage_path:
                        try:
                            execute_query(
                                "INSERT INTO files (job_id, filename, storage_path, user_id) VALUES (%s, %s, %s, %s)",
                                (job_uuid, secure_filename(f.filename), storage_path, user_id)
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

@app.route("/jobs")
def jobs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    try:
        job_data = execute_query(
            "SELECT id, client_name, final_price, status, created_at FROM jobs WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
            fetch=True
        )
        job_ids = [str(j["id"]) for j in job_data]

        counts = {jid: {"3/4": 0, "1/2": 0, "1/4": 0, "Other": 0, "total": 0} for jid in job_ids}
        if job_ids:
            # Use IN clause instead of ANY for better compatibility
            placeholders = ','.join(['%s'] * len(job_ids))
            parts_data = execute_query(
                f"SELECT job_id, material FROM parts WHERE job_id::text IN ({placeholders})",
                tuple(job_ids),
                fetch=True
            )
            for p in parts_data:
                jid = str(p.get("job_id"))
                mat = (p.get("material") or "").strip()
                key = mat if mat in ("3/4", "1/2", "1/4") else "Other"
                if jid in counts:
                    counts[jid][key] += 1
                    counts[jid]["total"] += 1

        for j in job_data:
            j["part_counts"] = counts.get(str(j["id"]), {"3/4": 0, "1/2": 0, "1/4": 0, "Other": 0, "total": 0})

        current_date = datetime.now().date()
        return render_template("jobs.html", jobs=job_data, current_date=current_date)

    except Exception as e:
        print("Error loading jobs:", e)
        flash("Could not load jobs. Please try again later.", "danger")
        return redirect(url_for("home"))

@app.route("/job_details/<job_id>")
def job_details(job_id):
    if "user_id" not in session:
        flash("Please log in to view job details.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        # Get job parts
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        # Get deadlines
        deadline = execute_single(
            "SELECT * FROM deadlines WHERE job_id = %s",
            (job_id,)
        )
        
        return render_template("job_details.html", job=job, parts=parts, deadline=deadline)
        
    except Exception as e:
        print("Error loading job details:", e)
        flash("Could not load job details.", "danger")
        return redirect(url_for("jobs"))

@app.route("/edit_job/<job_id>", methods=["GET", "POST"])
def edit_job(job_id):
    if "user_id" not in session:
        flash("Please log in to edit jobs.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        if request.method == "POST":
            # Update job with form data
            client_name = request.form.get("client_name")
            final_price = request.form.get("final_price")
            status = request.form.get("status")
            
            execute_query(
                "UPDATE jobs SET client_name = %s, final_price = %s, status = %s WHERE id = %s",
                (client_name, final_price, status, job_id),
                fetch=False
            )
            
            flash("Job updated successfully!", "success")
            return redirect(url_for("job_details", job_id=job_id))
        
        return render_template("edit_job.html", job=job)
        
    except Exception as e:
        print("Error editing job:", e)
        flash("Could not edit job.", "danger")
        return redirect(url_for("jobs"))

@app.route("/job_gallery/<job_id>")
def job_gallery(job_id):
    if "user_id" not in session:
        flash("Please log in to view job gallery.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        return render_template("job_gallery.html", job=job)
        
    except Exception as e:
        print("Error loading job gallery:", e)
        flash("Could not load job gallery.", "danger")
        return redirect(url_for("jobs"))

@app.route("/delete_job/<job_id>", methods=["POST"])
def delete_job(job_id):
    if "user_id" not in session:
        flash("Please log in to delete jobs.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        # Verify job ownership
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        # Delete related records first
        execute_query("DELETE FROM parts WHERE job_id = %s", (job_id,), fetch=False)
        execute_query("DELETE FROM deadlines WHERE job_id = %s", (job_id,), fetch=False)
        
        # Delete the job
        execute_query("DELETE FROM jobs WHERE id = %s", (job_id,), fetch=False)
        
        flash("Job deleted successfully.", "success")
        return redirect(url_for("jobs"))
        
    except Exception as e:
        print("Error deleting job:", e)
        flash("Could not delete job.", "danger")
        return redirect(url_for("jobs"))

@app.route("/help")
def help():
    return render_template("help.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in to view your dashboard.", "warning")
        return redirect(url_for("login"))
    return render_template("dashboard.html")

@app.route("/robots.txt")
def robots_txt():
    return app.send_static_file("robots.txt")

@app.route("/stocks", endpoint="view_stocks")
def view_stocks():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    try:
        stocks = execute_query(
            "SELECT * FROM stocks WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
            fetch=True
        )
    except Exception as e:
        print("Error loading stocks:", e)
        stocks = []
        flash("Failed to load stock inventory.", "danger")

    return render_template("stocks.html", stocks=stocks)

@app.route("/stocks/add", methods=["POST"])
def add_stock():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    name = request.form.get("name")
    category = request.form.get("category") or "Uncategorized"
    quantity = int(request.form.get("quantity") or 0)
    unit = request.form.get("unit")
    code = request.form.get("code") or None
    color = request.form.get("color") or None

    try:
        execute_query(
            "INSERT INTO stocks (user_id, name, category, quantity, unit, code, color) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, name, category, quantity, unit, code, color)
        )
        flash("Stock item added.")
    except Exception as e:
        print("Error adding stock:", e)
        flash("Failed to add stock item.", "danger")

    return redirect(url_for("view_stocks"))

@app.route("/cabinet-designer")
def cabinet_designer():
    """iPad-optimized cabinet designer"""
    if "user_id" not in session:
        flash("Please log in to use the cabinet designer.", "warning")
        return redirect(url_for("login"))
    
    return render_template("ipad_cabinet_designer.html")

@app.route("/cabinet-designer/<int:job_id>")
def cabinet_designer_job(job_id):
    """Cabinet designer with specific job data"""
    if "user_id" not in session:
        flash("Please log in to use the cabinet designer.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        # Get job parts
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        return render_template("ipad_cabinet_designer.html", job=job, parts=parts)
    
    except Exception as e:
        print("Error loading job for cabinet designer:", e)
        flash("Could not load job data.", "danger")
        return redirect(url_for("jobs"))

@app.route("/simple-designer")
def simple_designer():
    """Simple cabinet designer (fallback)"""
    if "user_id" not in session:
        flash("Please log in to use the cabinet designer.", "warning")
        return redirect(url_for("login"))
    
    return render_template("simple_cabinet_designer.html")

@app.route("/simple-designer/<int:job_id>")
def simple_designer_job(job_id):
    """Simple cabinet designer with job data"""
    if "user_id" not in session:
        flash("Please log in to use the cabinet designer.", "warning")
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        return render_template("simple_cabinet_designer.html", job=job, parts=parts)
    
    except Exception as e:
        print("Error loading job for simple designer:", e)
        flash("Could not load job data.", "danger")
        return redirect(url_for("jobs"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)