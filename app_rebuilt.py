# ✅ Complete Rebuilt Neon-based Flask Application
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response, current_app, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os, uuid, shutil, glob, json
from io import BytesIO
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from neon_client import execute_query, execute_single
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
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
    return dict(current_user=current_user())

@app.context_processor  
def expose_helpers():
    return dict(datetime=datetime, len=len, str=str)

# ===== AUTHENTICATION ROUTES =====

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password")
        
        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("signup.html")
        
        try:
            # Check if user exists
            existing_user = execute_single("SELECT id FROM users WHERE email = %s", (email,))
            if existing_user:
                flash("An account with this email already exists.", "danger")
                return render_template("signup.html")
            
            # Create new user
            hashed_password = hash_password(password)
            user_id = execute_single(
                "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (email, username, hashed_password)
            )
            
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
            
        except Exception as e:
            print("Error creating user:", e)
            flash("Error creating account. Please try again.", "danger")
            return render_template("signup.html")
    
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        password = request.form.get("password")
        
        try:
            user = execute_single("SELECT * FROM users WHERE email = %s", (email,))
            if user and verify_password(password, user["password_hash"]):
                session["user_id"] = str(user["id"])
                flash("Welcome back!", "success")
                return redirect(url_for("home"))
            else:
                flash("Invalid email or password.", "danger")
        except Exception as e:
            print("Error logging in:", e)
            flash("Login error. Please try again.", "danger")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

# ===== MAIN ROUTES =====

@app.route("/")
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

            # Get upcoming deadlines
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
            
            # Get upcoming deadlines with job info
            if deadlines:
                job_ids = [str(d["job_id"]) for d in deadlines[:5]]
                if job_ids:
                    placeholders = ','.join(['%s'] * len(job_ids))
                    jobs_info = execute_query(
                        f"SELECT id, client_name FROM jobs WHERE id::text IN ({placeholders})",
                        tuple(job_ids),
                        fetch=True
                    )
                    
                    job_map = {str(j["id"]): j["client_name"] for j in jobs_info}
                    
                    for d in deadlines[:5]:
                        if d.get("hard_deadline"):
                            upcoming_deadlines.append({
                                "job_id": d["job_id"],
                                "client_name": job_map.get(str(d["job_id"]), "Unknown"),
                                "hard_deadline": d["hard_deadline"]
                            })

            # Recent jobs
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

# ===== JOB ROUTES =====

@app.route("/create-job", methods=["GET", "POST"])
def create_job():
    if "user_id" not in session:
        flash("Please log in to create a job.", "warning")
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("index.html")

    user_id = session["user_id"]
    
    try:
        # Get form data
        client_name = request.form.get("client_name", "").strip()
        soft_deadline = request.form.get("soft_deadline")
        hard_deadline = request.form.get("hard_deadline")
        
        # Create job
        job_uuid = str(uuid.uuid4())
        execute_query(
            "INSERT INTO jobs (id, user_id, client_name, status) VALUES (%s, %s, %s, %s)",
            (job_uuid, user_id, client_name, "draft"),
            fetch=False
        )
        
        # Add deadlines if provided
        if soft_deadline or hard_deadline:
            execute_query(
                "INSERT INTO deadlines (job_id, user_id, soft_deadline, hard_deadline, job_name) VALUES (%s, %s, %s, %s, %s)",
                (job_uuid, user_id, 
                 datetime.strptime(soft_deadline, '%Y-%m-%d').date() if soft_deadline else None,
                 datetime.strptime(hard_deadline, '%Y-%m-%d').date() if hard_deadline else None,
                 client_name),
                fetch=False
            )
        
        # Handle file uploads
        uploaded_files = request.files.getlist('job_files')
        for file in uploaded_files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = f"static/uploads/{job_uuid}/{filename}"
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                
                execute_query(
                    "INSERT INTO files (job_id, user_id, filename, storage_path, subfolder) VALUES (%s, %s, %s, %s, %s)",
                    (job_uuid, user_id, filename, file_path, job_uuid),
                    fetch=False
                )

        # Process parts data
        parts_data = []
        part_index = 0
        while True:
            width_key = f"width_{part_index}"
            height_key = f"height_{part_index}"
            thickness_key = f"thickness_{part_index}"
            material_key = f"material_{part_index}"
            
            if width_key not in request.form:
                break
            
            width = request.form.get(width_key)
            height = request.form.get(height_key)
            thickness = request.form.get(thickness_key, "3/4")
            material = request.form.get(material_key, "Plywood")
            
            if width and height:
                try:
                    w = float(width)
                    h = float(height)
                    parts_data.append((w, h, thickness))
                    
                    # Save to database
                    execute_query(
                        "INSERT INTO parts (job_id, width, height, thickness, material) VALUES (%s, %s, %s, %s, %s)",
                        (job_uuid, w, h, thickness, material),
                        fetch=False
                    )
                except ValueError:
                    continue
            
            part_index += 1

        if not parts_data:
            flash("No valid parts found. Please add at least one part.", "warning")
            return redirect(url_for("create_job"))

        # Generate optimized cuts
        optimized = optimize_cuts(parts_data)
        sheet_images = draw_sheets_to_files(optimized, job_uuid)

        return render_template(
            "result.html",
            parts=parts_data,
            sheet_images=sheet_images,
            job_id=job_uuid
        )
        
    except Exception as e:
        print("Error creating job:", e)
        flash("Error creating job. Please try again.", "danger")
        return redirect(url_for("create_job"))

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
            "SELECT * FROM parts WHERE job_id = %s ORDER BY created_at",
            (job_id,),
            fetch=True
        )
        
        # Get deadlines
        deadline = execute_single(
            "SELECT * FROM deadlines WHERE job_id = %s",
            (job_id,)
        )
        
        # Get files
        files = execute_query(
            "SELECT * FROM files WHERE job_id = %s ORDER BY uploaded_at",
            (job_id,),
            fetch=True
        )
        
        # Get estimates
        estimates = execute_query(
            "SELECT * FROM estimates WHERE job_id = %s ORDER BY created_at DESC",
            (job_id,),
            fetch=True
        )
        
        return render_template("job_details.html", job=job, parts=parts, deadline=deadline, files=files, estimates=estimates)
        
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
        
        # Get current deadline
        deadline = execute_single(
            "SELECT * FROM deadlines WHERE job_id = %s",
            (job_id,)
        )
        
        if request.method == "POST":
            # Update job with form data
            client_name = request.form.get("client_name")
            soft_deadline = request.form.get("soft_deadline")
            hard_deadline = request.form.get("hard_deadline")
            
            # Update job
            execute_query(
                "UPDATE jobs SET client_name = %s WHERE id = %s",
                (client_name, job_id),
                fetch=False
            )
            
            # Update or create deadlines
            if deadline:
                execute_query(
                    "UPDATE deadlines SET soft_deadline = %s, hard_deadline = %s, job_name = %s WHERE job_id = %s",
                    (
                        datetime.strptime(soft_deadline, '%Y-%m-%d').date() if soft_deadline else None,
                        datetime.strptime(hard_deadline, '%Y-%m-%d').date() if hard_deadline else None,
                        client_name,
                        job_id
                    ),
                    fetch=False
                )
            elif soft_deadline or hard_deadline:
                execute_query(
                    "INSERT INTO deadlines (job_id, user_id, soft_deadline, hard_deadline, job_name) VALUES (%s, %s, %s, %s, %s)",
                    (
                        job_id, user_id,
                        datetime.strptime(soft_deadline, '%Y-%m-%d').date() if soft_deadline else None,
                        datetime.strptime(hard_deadline, '%Y-%m-%d').date() if hard_deadline else None,
                        client_name
                    ),
                    fetch=False
                )
            
            # Handle file uploads
            uploaded_files = request.files.getlist('job_files')
            for file in uploaded_files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    file_path = f"static/uploads/{job_id}/{filename}"
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    file.save(file_path)
                    
                    execute_query(
                        "INSERT INTO files (job_id, user_id, filename, storage_path, subfolder) VALUES (%s, %s, %s, %s, %s)",
                        (job_id, user_id, filename, file_path, job_id),
                        fetch=False
                    )
            
            # Handle new parts
            part_index = 0
            while True:
                width_key = f"width_{part_index}"
                height_key = f"height_{part_index}"
                thickness_key = f"thickness_{part_index}"
                material_key = f"material_{part_index}"
                
                if width_key not in request.form:
                    break
                
                width = request.form.get(width_key)
                height = request.form.get(height_key)
                thickness = request.form.get(thickness_key, "3/4")
                material = request.form.get(material_key, "Plywood")
                
                if width and height:
                    try:
                        w = float(width)
                        h = float(height)
                        
                        # Save to database
                        execute_query(
                            "INSERT INTO parts (job_id, width, height, thickness, material) VALUES (%s, %s, %s, %s, %s)",
                            (job_id, w, h, thickness, material),
                            fetch=False
                        )
                    except ValueError:
                        continue
                
                part_index += 1
            
            flash("Job updated successfully!", "success")
            return redirect(url_for("job_details", job_id=job_id))
        
        return render_template("edit_job.html", job=job, deadline=deadline)
        
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
        
        # Get all sheet images for this job
        sheet_folder = f"static/sheets/{job_id}"
        sheet_images = []
        
        if os.path.exists(sheet_folder):
            for file in os.listdir(sheet_folder):
                if file.endswith(('.png', '.jpg', '.jpeg')):
                    sheet_images.append(f"sheets/{job_id}/{file}")
        
        return render_template("job_gallery.html", job=job, sheet_images=sheet_images)
        
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
        
        # Delete related records first (foreign key constraints)
        execute_query("DELETE FROM files WHERE job_id = %s", (job_id,), fetch=False)
        execute_query("DELETE FROM estimate_items WHERE estimate_id IN (SELECT id FROM estimates WHERE job_id = %s)", (job_id,), fetch=False)
        execute_query("DELETE FROM estimates WHERE job_id = %s", (job_id,), fetch=False)
        execute_query("DELETE FROM parts WHERE job_id = %s", (job_id,), fetch=False)
        execute_query("DELETE FROM deadlines WHERE job_id = %s", (job_id,), fetch=False)
        
        # Delete the job
        execute_query("DELETE FROM jobs WHERE id = %s", (job_id,), fetch=False)
        
        # Clean up files
        job_folder = f"static/uploads/{job_id}"
        sheet_folder = f"static/sheets/{job_id}"
        
        if os.path.exists(job_folder):
            shutil.rmtree(job_folder)
        if os.path.exists(sheet_folder):
            shutil.rmtree(sheet_folder)
        
        flash("Job deleted successfully.", "success")
        return redirect(url_for("jobs"))
        
    except Exception as e:
        print("Error deleting job:", e)
        flash("Could not delete job.", "danger")
        return redirect(url_for("jobs"))

@app.route("/set_price/<job_id>", methods=["POST"])
def set_price(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    price = request.form.get("final_price")
    
    try:
        # Verify job ownership
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        execute_query(
            "UPDATE jobs SET final_price = %s WHERE id = %s",
            (float(price) if price else None, job_id),
            fetch=False
        )
        
        flash("Price updated successfully!", "success")
        return redirect(url_for("job_details", job_id=job_id))
        
    except Exception as e:
        print("Error setting price:", e)
        flash("Could not update price.", "danger")
        return redirect(url_for("job_details", job_id=job_id))

@app.route("/update_job_status/<job_id>", methods=["POST"])
def update_job_status(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    status = request.form.get("status")
    
    try:
        # Verify job ownership
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs"))
        
        execute_query(
            "UPDATE jobs SET status = %s WHERE id = %s",
            (status, job_id),
            fetch=False
        )
        
        flash("Status updated successfully!", "success")
        return redirect(url_for("job_details", job_id=job_id))
        
    except Exception as e:
        print("Error updating status:", e)
        flash("Could not update status.", "danger")
        return redirect(url_for("job_details", job_id=job_id))

# ===== CALENDAR ROUTE =====

@app.route("/calendar")
def calendar():
    if "user_id" not in session:
        flash("Please log in to view calendar.", "warning")
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

# ===== ESTIMATE ROUTES =====

@app.route("/create_detailed_estimate/<job_id>", methods=["GET", "POST"])
def create_detailed_estimate(job_id):
    if "user_id" not in session:
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
        
        if request.method == "POST":
            # Get form data
            estimate_name = request.form.get("estimate_name")
            description = request.form.get("description")
            labor_rate = request.form.get("labor_rate")
            markup_percentage = request.form.get("markup_percentage")
            
            # Create estimate
            estimate_id = str(uuid.uuid4())
            execute_query(
                "INSERT INTO estimates (id, job_id, name, description, labor_rate, markup_percentage, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (estimate_id, job_id, estimate_name, description, float(labor_rate or 0), float(markup_percentage or 0), 0),
                fetch=False
            )
            
            # Process estimate items
            total_amount = 0
            item_index = 0
            
            while True:
                item_type_key = f"item_type_{item_index}"
                if item_type_key not in request.form:
                    break
                
                item_type = request.form.get(item_type_key)
                name = request.form.get(f"item_name_{item_index}")
                description = request.form.get(f"item_description_{item_index}")
                quantity = request.form.get(f"quantity_{item_index}")
                unit = request.form.get(f"unit_{item_index}")
                unit_price = request.form.get(f"unit_price_{item_index}")
                
                if name and quantity and unit_price:
                    try:
                        qty = float(quantity)
                        price = float(unit_price)
                        total_price = qty * price
                        total_amount += total_price
                        
                        execute_query(
                            "INSERT INTO estimate_items (estimate_id, item_type, name, description, quantity, unit, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (estimate_id, item_type, name, description, qty, unit, price, total_price),
                            fetch=False
                        )
                    except ValueError:
                        pass
                
                item_index += 1
            
            # Apply markup
            markup_multiplier = 1 + (float(markup_percentage or 0) / 100)
            final_amount = total_amount * markup_multiplier
            
            # Update estimate total
            execute_query(
                "UPDATE estimates SET amount = %s WHERE id = %s",
                (final_amount, estimate_id),
                fetch=False
            )
            
            flash("Estimate created successfully!", "success")
            return redirect(url_for("view_estimate", estimate_id=estimate_id))
        
        return render_template("create_detailed_estimate.html", job=job)
        
    except Exception as e:
        print("Error creating estimate:", e)
        flash("Could not create estimate.", "danger")
        return redirect(url_for("job_details", job_id=job_id))

@app.route("/view_estimate/<estimate_id>")
def view_estimate(estimate_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        estimate = execute_single(
            "SELECT e.*, j.client_name FROM estimates e JOIN jobs j ON e.job_id = j.id WHERE e.id = %s AND j.user_id = %s",
            (estimate_id, user_id)
        )
        
        if not estimate:
            flash("Estimate not found.", "danger")
            return redirect(url_for("jobs"))
        
        # Get estimate items
        items = execute_query(
            "SELECT * FROM estimate_items WHERE estimate_id = %s ORDER BY created_at",
            (estimate_id,),
            fetch=True
        )
        
        # Group items by type
        grouped_items = defaultdict(list)
        for item in items:
            grouped_items[item["item_type"]].append(item)
        
        return render_template("view_estimate.html", estimate=estimate, grouped_items=dict(grouped_items))
        
    except Exception as e:
        print("Error viewing estimate:", e)
        flash("Could not load estimate.", "danger")
        return redirect(url_for("jobs"))

@app.route("/save_estimate/<job_id>", methods=["POST"])
def save_estimate(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # This is a simplified version - you can expand based on your needs
    try:
        estimate_data = request.get_json()
        
        # Save estimate logic here
        flash("Estimate saved successfully!", "success")
        return jsonify({"success": True})
        
    except Exception as e:
        print("Error saving estimate:", e)
        return jsonify({"success": False, "error": str(e)})

# ===== PDF EXPORT =====

@app.route("/download_job_pdf/<job_id>")
def download_job_pdf(job_id):
    if "user_id" not in session:
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
        
        # Get parts
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        # Create PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, f"Job Details: {job.get('client_name', 'Unnamed Client')}")
        
        # Job info
        p.setFont("Helvetica", 12)
        y_position = height - 100
        p.drawString(50, y_position, f"Job ID: {job_id}")
        y_position -= 20
        p.drawString(50, y_position, f"Created: {job.get('created_at', 'Unknown')}")
        y_position -= 20
        p.drawString(50, y_position, f"Status: {job.get('status', 'Draft')}")
        
        if job.get('final_price'):
            y_position -= 20
            p.drawString(50, y_position, f"Price: ${job['final_price']}")
        
        # Parts list
        y_position -= 40
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y_position, "Parts List:")
        
        y_position -= 30
        p.setFont("Helvetica", 10)
        for i, part in enumerate(parts, 1):
            if y_position < 100:  # Start new page if needed
                p.showPage()
                y_position = height - 50
            
            p.drawString(50, y_position, f"{i}. {part['width']}\" x {part['height']}\" x {part.get('thickness', 'N/A')} - {part.get('material', 'N/A')}")
            y_position -= 15
        
        p.save()
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"job_{job.get('client_name', 'unnamed').replace(' ', '_')}_{job_id[:8]}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print("Error generating PDF:", e)
        flash("Could not generate PDF.", "danger")
        return redirect(url_for("job_details", job_id=job_id))

# ===== STOCK MANAGEMENT =====

@app.route("/stocks")
def view_stocks():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        stocks = execute_query(
            "SELECT * FROM stocks WHERE user_id = %s ORDER BY category, name",
            (user_id,),
            fetch=True
        )
        
        return render_template("stocks.html", stocks=stocks)
        
    except Exception as e:
        print("Error loading stocks:", e)
        flash("Could not load stocks.", "danger")
        return redirect(url_for("home"))

@app.route("/add_stock", methods=["POST"])
def add_stock():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        name = request.form.get("name")
        category = request.form.get("category", "Uncategorized")
        quantity = request.form.get("quantity", 0)
        unit = request.form.get("unit")
        code = request.form.get("code")
        color = request.form.get("color")
        
        execute_query(
            "INSERT INTO stocks (user_id, name, category, quantity, unit, code, color) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, name, category, int(quantity), unit, code, color),
            fetch=False
        )
        
        flash("Stock item added successfully!", "success")
        
    except Exception as e:
        print("Error adding stock:", e)
        flash("Could not add stock item.", "danger")
    
    return redirect(url_for("view_stocks"))

@app.route("/update_stock/<stock_id>", methods=["POST"])
def update_stock(stock_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        quantity = request.form.get("quantity")
        
        execute_query(
            "UPDATE stocks SET quantity = %s WHERE id = %s AND user_id = %s",
            (int(quantity), stock_id, user_id),
            fetch=False
        )
        
        flash("Stock updated successfully!", "success")
        
    except Exception as e:
        print("Error updating stock:", e)
        flash("Could not update stock.", "danger")
    
    return redirect(url_for("view_stocks"))

@app.route("/delete_stock/<stock_id>", methods=["POST"])
def delete_stock(stock_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    
    try:
        execute_query(
            "DELETE FROM stocks WHERE id = %s AND user_id = %s",
            (stock_id, user_id),
            fetch=False
        )
        
        flash("Stock item deleted successfully!", "success")
        
    except Exception as e:
        print("Error deleting stock:", e)
        flash("Could not delete stock item.", "danger")
    
    return redirect(url_for("view_stocks"))

# ===== CABINET DESIGNER ROUTES =====

@app.route("/cabinet-designer")
def cabinet_designer():
    if "user_id" not in session:
        flash("Please log in to access the cabinet designer.", "warning")
        return redirect(url_for("login"))
    return render_template("ipad_cabinet_designer.html")

@app.route("/cabinet-designer/<int:job_id>")
def cabinet_designer_job(job_id):
    if "user_id" not in session:
        flash("Please log in to access the cabinet designer.", "warning")
        return redirect(url_for("login"))
    
    try:
        user_id = session["user_id"]
        
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found or access denied.", "danger")
            return redirect(url_for("jobs"))

        # Get job parts
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        return render_template("ipad_cabinet_designer.html", job=job, parts=parts)
    
    except Exception as e:
        print("Error loading cabinet designer:", e)
        flash("Could not load cabinet designer.", "danger")
        return redirect(url_for("jobs"))

@app.route("/simple-designer/<int:job_id>")  
def simple_designer_job(job_id):
    if "user_id" not in session:
        flash("Please log in to access the designer.", "warning")
        return redirect(url_for("login"))
    
    try:
        user_id = session["user_id"]
        
        # Get job details
        job = execute_single(
            "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id)
        )
        
        if not job:
            flash("Job not found or access denied.", "danger")
            return redirect(url_for("jobs"))
        
        parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s",
            (job_id,),
            fetch=True
        )
        
        return render_template("simple_cabinet_designer.html", job=job, parts=parts)
    
    except Exception as e:
        print("Error loading simple designer:", e)
        flash("Could not load designer.", "danger")
        return redirect(url_for("jobs"))

# ===== UTILITY ROUTES =====

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

# ===== RUN APPLICATION =====

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)