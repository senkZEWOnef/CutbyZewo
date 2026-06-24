# ✅ Complete Rebuilt Neon-based Flask Application
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response, current_app, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os, uuid, shutil, glob, json, math, secrets, base64 as _b64
from io import BytesIO
from PIL import Image

try:
    import qrcode as _qrcode
    _HAS_QRCODE = True
except ImportError:
    _HAS_QRCODE = False

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

# Ensure cut_sheets table exists (safe to run on every startup)
try:
    execute_query("""
        CREATE TABLE IF NOT EXISTS cut_sheets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            src VARCHAR(500) NOT NULL,
            label VARCHAR(100),
            sheet_number INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """, fetch=False)
except Exception as _e:
    print("Warning: could not ensure cut_sheets table:", _e)

try:
    execute_query("""
        ALTER TABLE estimates ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE
    """, fetch=False)
except Exception as _e:
    print("Warning: could not add share_token to estimates:", _e)

try:
    execute_query("""
        CREATE TABLE IF NOT EXISTS job_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            parts JSONB DEFAULT '[]',
            accessories JSONB DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """, fetch=False)
except Exception as _e:
    print("Warning: could not ensure job_templates table:", _e)

try:
    execute_query("""
        CREATE TABLE IF NOT EXISTS job_accessories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            quantity DECIMAL(10,2) DEFAULT 1,
            unit VARCHAR(50) DEFAULT 'pieces',
            unit_price DECIMAL(10,2) DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """, fetch=False)
except Exception as _e:
    print("Warning: could not ensure job_accessories table:", _e)

def _make_qr_dataurl(url):
    if not _HAS_QRCODE:
        return None
    qr = _qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    return _b64.b64encode(buf.getvalue()).decode()


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
    
    user = current_user() if user_id else None
    return render_template("landing.html", user=user, jobs=upcoming_deadlines, recent_jobs=recent_jobs, stats=stats, current_date=current_date)

# ===== JOB ROUTES =====

@app.route("/create-job", methods=["GET", "POST"])
def create_job():
    if "user_id" not in session:
        flash("Please log in to create a job.", "warning")
        return redirect(url_for("login"))

    if request.method == "GET":
        templates = execute_query(
            "SELECT * FROM job_templates WHERE user_id = %s ORDER BY name",
            (session["user_id"],), fetch=True
        ) if "user_id" in session else []
        return render_template("index.html", templates=templates)

    user_id = session["user_id"]

    try:
        client_name = request.form.get("client_name", "").strip()
        soft_deadline = request.form.get("soft_deadline")
        hard_deadline = request.form.get("hard_deadline")
        template_id = request.form.get("template_id", "").strip()

        if not client_name:
            flash("Client name is required.", "warning")
            return render_template("index.html", templates=[])

        job_uuid = str(uuid.uuid4())
        execute_query(
            "INSERT INTO jobs (id, user_id, client_name, status) VALUES (%s, %s, %s, %s)",
            (job_uuid, user_id, client_name, "draft"),
            fetch=False
        )

        if soft_deadline or hard_deadline:
            execute_query(
                "INSERT INTO deadlines (job_id, user_id, soft_deadline, hard_deadline, job_name) VALUES (%s, %s, %s, %s, %s)",
                (job_uuid, user_id,
                 datetime.strptime(soft_deadline, '%Y-%m-%d').date() if soft_deadline else None,
                 datetime.strptime(hard_deadline, '%Y-%m-%d').date() if hard_deadline else None,
                 client_name),
                fetch=False
            )

        # Import parts + accessories from template if selected
        if template_id:
            tpl = execute_single(
                "SELECT * FROM job_templates WHERE id = %s AND user_id = %s",
                (template_id, user_id)
            )
            if tpl:
                tpl_parts = tpl['parts'] if isinstance(tpl['parts'], list) else json.loads(tpl['parts'] or '[]')
                tpl_accs  = tpl['accessories'] if isinstance(tpl['accessories'], list) else json.loads(tpl['accessories'] or '[]')
                parts_xy = []
                for p in tpl_parts:
                    for _ in range(int(p.get('quantity', 1))):
                        execute_query(
                            "INSERT INTO parts (job_id, width, height, thickness, material) VALUES (%s, %s, %s, %s, %s)",
                            (job_uuid, p['width'], p['height'], p.get('thickness','3/4'), p.get('material','Plywood')),
                            fetch=False
                        )
                        parts_xy.append((float(p['width']), float(p['height'])))
                for a in tpl_accs:
                    execute_query(
                        "INSERT INTO job_accessories (job_id, name, quantity, unit, unit_price) VALUES (%s, %s, %s, %s, %s)",
                        (job_uuid, a['name'], a.get('quantity', 1), a.get('unit','pieces'), a.get('unit_price', 0)),
                        fetch=False
                    )
                if parts_xy:
                    try:
                        optimized = optimize_cuts(96, 48, parts_xy)
                        sheet_images = draw_sheets_to_files(optimized, f"static/sheets/{job_uuid}")
                        for n, (src, label) in enumerate(sheet_images, 1):
                            execute_query(
                                "INSERT INTO cut_sheets (job_id, src, label, sheet_number) VALUES (%s, %s, %s, %s)",
                                (job_uuid, src, label, n), fetch=False
                            )
                    except Exception as e:
                        print("Error generating cut sheets from template:", e)
                flash(f"Job created from template — review parts and go to estimate.", "info")
                return redirect(url_for('job_step_parts', job_id=job_uuid))

        action = request.form.get('action', 'next')
        if action == 'save_exit':
            flash(f"Job for {client_name} created.", "success")
            return redirect(url_for('job_details', job_id=job_uuid))
        return redirect(url_for('job_step_parts', job_id=job_uuid))

    except Exception as e:
        print("Error creating job:", e)
        flash("Error creating job. Please try again.", "danger")
        return redirect(url_for("create_job"))


@app.route("/job/<job_id>/step/parts", methods=["GET", "POST"])
def job_step_parts(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    job = execute_single("SELECT * FROM jobs WHERE id = %s AND user_id = %s", (job_id, user_id))
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs"))

    if request.method == "GET":
        existing_parts = execute_query(
            "SELECT * FROM parts WHERE job_id = %s ORDER BY created_at",
            (job_id,), fetch=True
        )
        return render_template("job_parts.html", job=job, parts=existing_parts)

    # POST — save files + parts, regenerate cut sheets
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

    widths = request.form.getlist('widths')
    heights = request.form.getlist('heights')
    quantities = request.form.getlist('quantities')
    thicknesses = request.form.getlist('thicknesses')
    panel_width = float(request.form.get('panel_width', 96))
    panel_height = float(request.form.get('panel_height', 48))

    new_parts = []
    for i in range(len(widths)):
        if i < len(heights) and widths[i] and heights[i]:
            try:
                w, h = float(widths[i]), float(heights[i])
                qty = int(quantities[i]) if i < len(quantities) and quantities[i] else 1
                thickness = thicknesses[i] if i < len(thicknesses) and thicknesses[i] else "3/4"
                for _ in range(qty):
                    new_parts.append((w, h, thickness))
                    execute_query(
                        "INSERT INTO parts (job_id, width, height, thickness, material) VALUES (%s, %s, %s, %s, %s)",
                        (job_id, w, h, thickness, "Plywood"),
                        fetch=False
                    )
            except ValueError:
                continue

    # Regenerate cut sheets from all parts for this job
    all_parts = execute_query("SELECT * FROM parts WHERE job_id = %s", (job_id,), fetch=True)
    if all_parts:
        try:
            parts_xy = [(float(p['width']), float(p['height'])) for p in all_parts]
            optimized = optimize_cuts(panel_width, panel_height, parts_xy)
            execute_query("DELETE FROM cut_sheets WHERE job_id = %s", (job_id,), fetch=False)
            sheet_images = draw_sheets_to_files(optimized, f"static/sheets/{job_id}")
            for sheet_number, (src, label) in enumerate(sheet_images, start=1):
                execute_query(
                    "INSERT INTO cut_sheets (job_id, src, label, sheet_number) VALUES (%s, %s, %s, %s)",
                    (job_id, src, label, sheet_number),
                    fetch=False
                )
        except Exception as e:
            print("Error generating cut sheets:", e)
            flash(f"Parts saved but cut sheet generation failed: {e}", "warning")

    action = request.form.get('action', 'next')
    if action == 'save_exit':
        flash("Parts saved.", "success")
        return redirect(url_for('job_details', job_id=job_id))
    return redirect(url_for('job_step_accessories', job_id=job_id))


@app.route("/job/<job_id>/step/accessories", methods=["GET", "POST"])
def job_step_accessories(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    job = execute_single("SELECT * FROM jobs WHERE id = %s AND user_id = %s", (job_id, user_id))
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs"))

    if request.method == "GET":
        accessories = execute_query(
            "SELECT * FROM job_accessories WHERE job_id = %s ORDER BY created_at",
            (job_id,), fetch=True
        )
        return render_template("job_accessories.html", job=job, accessories=accessories)

    names = request.form.getlist('acc_name')
    quantities = request.form.getlist('acc_quantity')
    units = request.form.getlist('acc_unit')
    prices = request.form.getlist('acc_unit_price')

    for i in range(len(names)):
        if names[i].strip():
            try:
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1
                unit = units[i] if i < len(units) and units[i] else 'pieces'
                price = float(prices[i]) if i < len(prices) and prices[i] else 0
                execute_query(
                    "INSERT INTO job_accessories (job_id, name, quantity, unit, unit_price) VALUES (%s, %s, %s, %s, %s)",
                    (job_id, names[i].strip(), qty, unit, price),
                    fetch=False
                )
            except ValueError:
                continue

    action = request.form.get('action', 'next')
    if action == 'save_exit':
        flash("Accessories saved.", "success")
        return redirect(url_for('job_details', job_id=job_id))
    return redirect(url_for('create_detailed_estimate', job_id=job_id))


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

        # Get accessories
        accessories = execute_query(
            "SELECT * FROM job_accessories WHERE job_id = %s ORDER BY created_at",
            (job_id,), fetch=True
        )

        # Group parts by dimensions for the summary card
        part_groups = defaultdict(lambda: {'count': 0, 'first_id': None})
        for p in parts:
            key = (str(p['width']), str(p['height']), p.get('thickness') or '3/4', p.get('material') or 'Plywood')
            part_groups[key]['count'] += 1
            if part_groups[key]['first_id'] is None:
                part_groups[key]['first_id'] = str(p['id'])
        grouped_parts = [
            {'width': k[0], 'height': k[1], 'thickness': k[2], 'material': k[3],
             'quantity': v['count'], 'first_id': v['first_id']}
            for k, v in sorted(part_groups.items())
        ]

        # Build uploaded_images from files
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        uploaded_images = [
            {
                'url': '/' + f['storage_path'],
                'filename': f['filename'],
                'subfolder': f.get('subfolder') or '',
                'id': str(f['id'])
            }
            for f in files
            if os.path.splitext(f['filename'])[1].lower() in image_exts
        ]

        # Get cut sheets; regenerate PNGs if missing from disk (ephemeral filesystem)
        cut_sheet_rows = execute_query(
            "SELECT * FROM cut_sheets WHERE job_id = %s ORDER BY sheet_number",
            (job_id,), fetch=True
        )
        sheet_images = []
        if cut_sheet_rows:
            files_missing = any(
                not os.path.exists(f"static/{row['src']}") for row in cut_sheet_rows
            )
            if files_missing and parts:
                try:
                    parts_xy = [(float(p['width']), float(p['height'])) for p in parts]
                    optimized = optimize_cuts(96, 48, parts_xy)
                    draw_sheets_to_files(optimized, f"static/sheets/{job_id}")
                except Exception as _regen_err:
                    print("Error regenerating cut sheets:", _regen_err)
            sheet_images = [{"src": row["src"], "label": row["label"]} for row in cut_sheet_rows]

        return render_template(
            "job_details.html",
            job=job, parts=parts, grouped_parts=grouped_parts,
            deadline=deadline, uploaded_images=uploaded_images,
            estimates=estimates, sheet_images=sheet_images,
            accessories=accessories
        )
        
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

@app.route("/delete_part/<part_id>", methods=["POST"])
def delete_part(part_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    part = execute_single(
        "SELECT p.*, j.user_id as owner FROM parts p JOIN jobs j ON p.job_id = j.id WHERE p.id = %s",
        (part_id,)
    )
    if not part or str(part['owner']) != str(user_id):
        flash("Part not found.", "danger")
        return redirect(url_for("jobs"))
    job_id = str(part['job_id'])
    execute_query("DELETE FROM parts WHERE id = %s", (part_id,), fetch=False)
    # Regenerate cut sheets from remaining parts
    remaining = execute_query("SELECT * FROM parts WHERE job_id = %s", (job_id,), fetch=True)
    execute_query("DELETE FROM cut_sheets WHERE job_id = %s", (job_id,), fetch=False)
    if remaining:
        try:
            parts_xy = [(float(p['width']), float(p['height'])) for p in remaining]
            optimized = optimize_cuts(96, 48, parts_xy)
            sheet_images = draw_sheets_to_files(optimized, f"static/sheets/{job_id}")
            for n, (src, label) in enumerate(sheet_images, 1):
                execute_query(
                    "INSERT INTO cut_sheets (job_id, src, label, sheet_number) VALUES (%s, %s, %s, %s)",
                    (job_id, src, label, n), fetch=False
                )
        except Exception as e:
            print("Error regenerating cut sheets after part delete:", e)
    flash("Part removed.", "success")
    return redirect(url_for("job_details", job_id=job_id))


@app.route("/delete_accessory/<acc_id>", methods=["POST"])
def delete_accessory(acc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    acc = execute_single(
        "SELECT a.*, j.user_id as owner FROM job_accessories a JOIN jobs j ON a.job_id = j.id WHERE a.id = %s",
        (acc_id,)
    )
    if not acc or str(acc['owner']) != str(user_id):
        flash("Accessory not found.", "danger")
        return redirect(url_for("jobs"))
    job_id = str(acc['job_id'])
    execute_query("DELETE FROM job_accessories WHERE id = %s", (acc_id,), fetch=False)
    flash("Accessory removed.", "success")
    return redirect(url_for("job_details", job_id=job_id))


# ===== TEMPLATE ROUTES =====

@app.route("/job/<job_id>/save-as-template", methods=["POST"])
def save_as_template(job_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    job = execute_single("SELECT * FROM jobs WHERE id = %s AND user_id = %s", (job_id, user_id))
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs"))

    template_name = request.form.get("template_name", "").strip() or f"Template – {job['client_name']}"
    template_desc = request.form.get("template_description", "").strip()

    parts = execute_query("SELECT * FROM parts WHERE job_id = %s", (job_id,), fetch=True)
    part_groups = defaultdict(lambda: {'count': 0})
    for p in parts:
        key = (str(p['width']), str(p['height']), p.get('thickness','3/4'), p.get('material','Plywood'))
        part_groups[key]['count'] += 1
    parts_json = [
        {'width': k[0], 'height': k[1], 'thickness': k[2], 'material': k[3], 'quantity': v['count']}
        for k, v in part_groups.items()
    ]

    accessories = execute_query("SELECT * FROM job_accessories WHERE job_id = %s", (job_id,), fetch=True)
    acc_json = [
        {'name': a['name'], 'quantity': float(a['quantity']), 'unit': a['unit'], 'unit_price': float(a['unit_price'])}
        for a in accessories
    ]

    execute_query(
        "INSERT INTO job_templates (user_id, name, description, parts, accessories) VALUES (%s, %s, %s, %s, %s)",
        (user_id, template_name, template_desc, json.dumps(parts_json), json.dumps(acc_json)),
        fetch=False
    )
    flash(f'Template "{template_name}" saved.', "success")
    return redirect(url_for("job_details", job_id=job_id))


@app.route("/templates")
def list_templates():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    templates = execute_query(
        "SELECT * FROM job_templates WHERE user_id = %s ORDER BY name",
        (user_id,), fetch=True
    )
    # Parse JSON fields
    for t in templates:
        t['parts']       = t['parts'] if isinstance(t['parts'], list) else json.loads(t['parts'] or '[]')
        t['accessories'] = t['accessories'] if isinstance(t['accessories'], list) else json.loads(t['accessories'] or '[]')
    return render_template("job_templates.html", templates=templates)


@app.route("/delete-template/<template_id>", methods=["POST"])
def delete_template(template_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    execute_query(
        "DELETE FROM job_templates WHERE id = %s AND user_id = %s",
        (template_id, user_id), fetch=False
    )
    flash("Template deleted.", "success")
    return redirect(url_for("list_templates"))


# ===== SHARE ROUTES =====

@app.route("/estimate/generate-share/<estimate_id>")
def generate_share(estimate_id):
    if "user_id" not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    user_id = session["user_id"]
    estimate = execute_single(
        "SELECT e.*, j.user_id as owner FROM estimates e JOIN jobs j ON e.job_id = j.id WHERE e.id = %s",
        (estimate_id,)
    )
    if not estimate or str(estimate['owner']) != str(user_id):
        return jsonify({'error': 'Not found'}), 404
    token = estimate.get('share_token')
    if not token:
        token = secrets.token_urlsafe(24)
        execute_query("UPDATE estimates SET share_token = %s WHERE id = %s", (token, estimate_id), fetch=False)
    share_url = request.host_url.rstrip('/') + url_for('shared_estimate', token=token)
    return jsonify({'url': share_url, 'qr': _make_qr_dataurl(share_url)})


@app.route("/e/<token>")
def shared_estimate(token):
    estimate = execute_single("SELECT * FROM estimates WHERE share_token = %s", (token,))
    if not estimate:
        return "<h2>Estimate not found or link has expired.</h2>", 404
    job = execute_single("SELECT * FROM jobs WHERE id = %s", (estimate['job_id'],))
    items = execute_query(
        "SELECT * FROM estimate_items WHERE estimate_id = %s ORDER BY item_type, created_at",
        (str(estimate['id']),), fetch=True
    )
    grouped_items = defaultdict(list)
    totals = {"material": 0.0, "hardware": 0.0, "labor": 0.0}
    for item in items:
        grouped_items[item["item_type"]].append(item)
        if item["item_type"] in totals:
            totals[item["item_type"]] += float(item.get("total_price") or 0)
    return render_template(
        "shared_estimate.html",
        estimate=estimate, job=job,
        grouped_items=dict(grouped_items), totals=totals
    )


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

SHEET_PRICES = {'3/4': 85.0, '1/2': 65.0, '1/4': 45.0}

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
            estimate_name = request.form.get("estimate_name")
            description = request.form.get("description")
            labor_fee = float(request.form.get("labor_fee") or 0)
            commission = float(request.form.get("commission") or 0)

            estimate_id = str(uuid.uuid4())
            execute_query(
                "INSERT INTO estimates (id, job_id, name, description, labor_rate, markup_percentage, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (estimate_id, job_id, estimate_name, description, labor_fee, commission, 0),
                fetch=False
            )

            # Read parallel lists — field names match the template exactly
            item_types = request.form.getlist('item_type')
            item_names = request.form.getlist('item_name')
            item_quantities = request.form.getlist('item_quantity')
            item_units = request.form.getlist('item_unit')
            item_prices = request.form.getlist('item_unit_price')
            item_descriptions = request.form.getlist('item_description')

            line_total = 0
            for i in range(len(item_names)):
                name = item_names[i].strip() if i < len(item_names) else ''
                if not name:
                    continue
                try:
                    itype = item_types[i] if i < len(item_types) else 'material'
                    qty = float(item_quantities[i]) if i < len(item_quantities) and item_quantities[i] else 1
                    unit = item_units[i] if i < len(item_units) and item_units[i] else 'pieces'
                    price = float(item_prices[i]) if i < len(item_prices) and item_prices[i] else 0
                    desc = item_descriptions[i] if i < len(item_descriptions) else ''
                    row_total = qty * price
                    line_total += row_total
                    execute_query(
                        "INSERT INTO estimate_items (estimate_id, item_type, name, description, quantity, unit, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (estimate_id, itype, name, desc, qty, unit, price, row_total),
                        fetch=False
                    )
                except ValueError:
                    continue

            final_amount = line_total + labor_fee + commission
            execute_query(
                "UPDATE estimates SET amount = %s WHERE id = %s",
                (final_amount, estimate_id),
                fetch=False
            )

            flash("Estimate created successfully!", "success")
            return redirect(url_for("view_estimate", estimate_id=estimate_id))

        # --- GET: build pre-filled line items from parts + accessories ---

        # Material line items: group parts by thickness, estimate sheets needed
        parts = execute_query(
            "SELECT thickness, width, height FROM parts WHERE job_id = %s",
            (job_id,), fetch=True
        )
        thickness_areas = {}
        for p in parts:
            t = p['thickness'] or '3/4'
            area = float(p['width']) * float(p['height'])
            thickness_areas[t] = thickness_areas.get(t, 0) + area

        sheet_area = 96.0 * 48.0
        prefill_items = []
        for thickness in sorted(thickness_areas):
            sheets = math.ceil(thickness_areas[thickness] / sheet_area * 1.15)  # 15% waste
            prefill_items.append({
                'type': 'material',
                'name': f'{thickness}" Plywood',
                'quantity': sheets,
                'unit': 'sheets',
                'unit_price': SHEET_PRICES.get(thickness, 85.0),
                'description': f'{thickness}" plywood — {sheets} sheet(s) estimated'
            })

        # Hardware line items: from accessories step
        accessories = execute_query(
            "SELECT * FROM job_accessories WHERE job_id = %s ORDER BY created_at",
            (job_id,), fetch=True
        )
        for acc in accessories:
            prefill_items.append({
                'type': 'hardware',
                'name': acc['name'],
                'quantity': float(acc['quantity']),
                'unit': acc['unit'],
                'unit_price': float(acc['unit_price']),
                'description': ''
            })

        return render_template(
            "create_detailed_estimate.html",
            job=job,
            prefill_items=prefill_items
        )

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
        
        # Group items by type and compute totals per category
        grouped_items = defaultdict(list)
        totals = {"material": 0.0, "hardware": 0.0, "labor": 0.0}
        for item in items:
            grouped_items[item["item_type"]].append(item)
            if item["item_type"] in totals:
                totals[item["item_type"]] += float(item.get("total_price") or 0)

        # Build a minimal job object the template expects
        job = {"id": str(estimate["job_id"]), "client_name": estimate["client_name"]}

        return render_template("view_estimate.html", estimate=estimate, grouped_items=dict(grouped_items), job=job, totals=totals)
        
    except Exception as e:
        print("Error viewing estimate:", e)
        flash("Could not load estimate.", "danger")
        return redirect(url_for("jobs"))

@app.route("/edit_estimate/<estimate_id>", methods=["GET", "POST"])
def edit_estimate(estimate_id):
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

        job_id = str(estimate['job_id'])
        job = execute_single("SELECT * FROM jobs WHERE id = %s", (job_id,))

        if request.method == "POST":
            labor_fee = float(request.form.get("labor_fee") or 0)
            commission = float(request.form.get("commission") or 0)
            estimate_name = request.form.get("estimate_name")
            description = request.form.get("description")

            execute_query(
                "UPDATE estimates SET name=%s, description=%s, labor_rate=%s, markup_percentage=%s WHERE id=%s",
                (estimate_name, description, labor_fee, commission, estimate_id),
                fetch=False
            )
            execute_query("DELETE FROM estimate_items WHERE estimate_id = %s", (estimate_id,), fetch=False)

            item_types = request.form.getlist('item_type')
            item_names = request.form.getlist('item_name')
            item_quantities = request.form.getlist('item_quantity')
            item_units = request.form.getlist('item_unit')
            item_prices = request.form.getlist('item_unit_price')
            item_descriptions = request.form.getlist('item_description')

            line_total = 0
            for i in range(len(item_names)):
                name = item_names[i].strip() if i < len(item_names) else ''
                if not name:
                    continue
                try:
                    itype = item_types[i] if i < len(item_types) else 'material'
                    qty = float(item_quantities[i]) if i < len(item_quantities) and item_quantities[i] else 1
                    unit = item_units[i] if i < len(item_units) and item_units[i] else 'pieces'
                    price = float(item_prices[i]) if i < len(item_prices) and item_prices[i] else 0
                    desc = item_descriptions[i] if i < len(item_descriptions) else ''
                    row_total = qty * price
                    line_total += row_total
                    execute_query(
                        "INSERT INTO estimate_items (estimate_id, item_type, name, description, quantity, unit, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (estimate_id, itype, name, desc, qty, unit, price, row_total),
                        fetch=False
                    )
                except ValueError:
                    continue

            final_amount = line_total + labor_fee + commission
            execute_query("UPDATE estimates SET amount=%s WHERE id=%s", (final_amount, estimate_id), fetch=False)
            flash("Estimate updated.", "success")
            return redirect(url_for("view_estimate", estimate_id=estimate_id))

        # GET: load existing items as prefill
        items = execute_query(
            "SELECT * FROM estimate_items WHERE estimate_id = %s ORDER BY created_at",
            (estimate_id,), fetch=True
        )
        prefill_items = [
            {
                'type': item['item_type'],
                'name': item['name'],
                'quantity': float(item['quantity']),
                'unit': item['unit'],
                'unit_price': float(item['unit_price']),
                'description': item.get('description') or ''
            }
            for item in items
        ]
        return render_template(
            "create_detailed_estimate.html",
            job=job,
            prefill_items=prefill_items,
            edit_mode=True,
            estimate=estimate
        )
    except Exception as e:
        print("Error editing estimate:", e)
        flash("Could not load estimate for editing.", "danger")
        return redirect(url_for("jobs"))


@app.route("/save_estimate/<job_id>", methods=["POST"])
def save_estimate(job_id):
    if "user_id" not in session:
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
        
        # Get form data from the estimate modal
        amount = request.form.get("amount", 0)
        lf = request.form.get("lf", 0)
        
        # Create a simple estimate record
        estimate_id = str(uuid.uuid4())
        execute_query(
            "INSERT INTO estimates (id, job_id, name, description, amount) VALUES (%s, %s, %s, %s, %s)",
            (estimate_id, job_id, f"Estimate for {job.get('client_name', 'Job')}", "Auto-generated estimate", float(amount) if amount else 0),
            fetch=False
        )
        
        # Add main line items
        if lf:
            execute_query(
                "INSERT INTO estimate_items (estimate_id, item_type, name, quantity, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s)",
                (estimate_id, "labor", "Linear Feet", float(lf), 150, float(lf) * 150),
                fetch=False
            )
        
        # Handle accessories
        acc_names = request.form.getlist("acc_name[]")
        acc_qtys = request.form.getlist("acc_qty[]")
        acc_units = request.form.getlist("acc_unit[]")
        
        for i, name in enumerate(acc_names):
            if name and i < len(acc_qtys) and i < len(acc_units):
                try:
                    qty = float(acc_qtys[i]) if acc_qtys[i] else 0
                    unit_price = float(acc_units[i]) if acc_units[i] else 0
                    if qty > 0 and unit_price > 0:
                        execute_query(
                            "INSERT INTO estimate_items (estimate_id, item_type, name, quantity, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s)",
                            (estimate_id, "hardware", name, qty, unit_price, qty * unit_price),
                            fetch=False
                        )
                except ValueError:
                    continue
        
        # Handle commissions
        com_names = request.form.getlist("com_name[]")
        com_amounts = request.form.getlist("com_amount[]")
        
        for i, name in enumerate(com_names):
            if name and i < len(com_amounts):
                try:
                    amount_val = float(com_amounts[i]) if com_amounts[i] else 0
                    if amount_val > 0:
                        execute_query(
                            "INSERT INTO estimate_items (estimate_id, item_type, name, quantity, unit_price, total_price) VALUES (%s, %s, %s, %s, %s, %s)",
                            (estimate_id, "labor", f"Commission: {name}", 1, amount_val, amount_val),
                            fetch=False
                        )
                except ValueError:
                    continue
        
        flash("Estimate saved successfully!", "success")
        return redirect(url_for("job_details", job_id=job_id))
        
    except Exception as e:
        print("Error saving estimate:", e)
        flash("Could not save estimate.", "danger")
        return redirect(url_for("job_details", job_id=job_id))

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

@app.route("/cabinet-designer/<job_id>")
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

@app.route("/simple-designer/<job_id>")  
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