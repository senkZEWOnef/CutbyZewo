from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, uuid, shutil
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
from models import SessionLocal, Job, User, Estimate, Part, Base, engine
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ✅ Auto-create tables
Base.metadata.create_all(bind=engine)

# ✅ Recreate known admin user on every run (optional)
# ✅ Create admin ONCE if missing, but don't delete existing!
db = SessionLocal()
existing = db.query(User).filter(User.email == "ralph.ulysse509@gmail.com").first()
if not existing:
    admin = User(
        username="zewo",
        email="ralph.ulysse509@gmail.com",
        hashed_password=generate_password_hash("Poesie509$$$")
    )
    db.add(admin)
    db.commit()
    print("✅ Admin user created.")
else:
    print("✅ Admin user already exists.")
db.close()

print("✅ Admin user recreated.")

app = Flask(__name__)
app.secret_key = "Poesie509$$$"

# ✅ Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

# ✅ Session helper
def current_user():
    uid = session.get("user_id")
    if uid:
        db = SessionLocal()
        user = db.query(User).filter(User.id == uid).first()
        db.close()
        return user
    return None

# ✅ SIGNUP
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        db = SessionLocal()
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            flash("Email already registered.")
            db.close()
            return redirect(url_for("signup"))

        hashed = generate_password_hash(password)
        new_user = User(username=username, email=email, hashed_password=hashed)
        db.add(new_user)
        db.commit()
        db.close()

        flash("Account created! Please log in.")
        return redirect(url_for("login"))

    return render_template("signup.html")

# ✅ LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        db.close()

        if user and check_password_hash(user.hashed_password, password):
            session["user_id"] = user.id
            flash("Logged in successfully!")
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials.")

    return render_template("login.html")

# ✅ LOGOUT
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.")
    return redirect(url_for("login"))

# ✅ INDEX & CREATE JOB
@app.route("/", methods=["GET", "POST"])
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        client_name = request.form.get("client_name")
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")
        thicknesses = request.form.getlist("thicknesses")

        # 1️⃣ Group parts by thickness
        parts_by_thickness = {}
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                parts_by_thickness.setdefault(t, []).extend([(float(w), float(h))] * int(q))

        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))

        # 2️⃣ Create job & base folder
        job_uuid = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_uuid}"
        os.makedirs(output_dir, exist_ok=True)

        db = SessionLocal()
        new_job = Job(
            client_name=client_name,
            notes="Created by Cut Planner",
            image_folder=output_dir,
            user_id=user.id
        )
        db.add(new_job)
        db.commit()

        # 3️⃣ Generate sheets per thickness
        sheet_images = []
        for t, parts in parts_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            sheets = optimize_cuts(panel_width, panel_height, parts)
            draw_sheets_to_files(sheets, subfolder)

            # Track for result page
            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append( (rel, t) )

            # Save parts in DB
            for w, h in parts:
                db.add(Part(job_id=new_job.id, width=w, height=h, thickness=t))

        db.commit()

        # 4️⃣ Save uploaded files
        upload_dir = f"static/uploads/{new_job.id}"
        os.makedirs(upload_dir, exist_ok=True)
        if 'job_files' in request.files:
            files = request.files.getlist('job_files')
            for f in files:
                if f.filename:
                    filename = secure_filename(f.filename)
                    f.save(os.path.join(upload_dir, filename))

        db.refresh(new_job)
        db.close()

        return render_template(
            "result.html",
            parts=[(w, h, t) for t, ps in parts_by_thickness.items() for (w,h) in ps],
            sheet_images=sheet_images,
            user=user
        )

    return render_template("index.html", user=user)


# ✅ VIEW JOBS (only user's)
@app.route("/jobs")
def jobs():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    all_jobs = db.query(Job).filter(Job.user_id == user.id).order_by(Job.created_at.desc()).all()
    db.close()
    return render_template("jobs.html", jobs=all_jobs, user=user)

# ✅ JOB DETAILS
@app.route("/jobs/<int:job_id>")
def job_details(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    estimates = db.query(Estimate).filter(Estimate.job_id == job_id).order_by(Estimate.created_at.desc()).all()
    parts = db.query(Part).filter(Part.job_id == job_id).all()

    sheet_images = []

    if job and os.path.exists(job.image_folder):
        # Try modern structure first (subfolders by thickness)
        found_any = False
        for thickness in ["3/4", "1/2", "1/4"]:
            subfolder = os.path.join(job.image_folder, thickness)
            if os.path.exists(subfolder):
                found_any = True
                files = sorted(f for f in os.listdir(subfolder) if f.endswith(".png"))
                for f in files:
                    relative_path = f"sheets/{os.path.basename(job.image_folder)}/{thickness}/{f}"
                    sheet_images.append( (relative_path, thickness) )
        
        # If no subfolders, fallback to flat folder: assume Unknown
        if not found_any:
            files = sorted(f for f in os.listdir(job.image_folder) if f.endswith(".png"))
            for f in files:
                relative_path = f"sheets/{os.path.basename(job.image_folder)}/{f}"
                sheet_images.append( (relative_path, "Unknown") )

    upload_dir = f"static/uploads/{job.id}"
    uploaded_images = []
    if os.path.exists(upload_dir):
        uploaded_images = [f"uploads/{job.id}/{f}" for f in os.listdir(upload_dir)]

    db.close()

    if not job:
        return "Job not found", 404

    return render_template(
        "job_details.html",
        job=job,
        estimates=estimates,
        parts=parts,
        sheet_images=sheet_images,
        uploaded_images=uploaded_images,
        user=user
    )




# ✅ EDIT JOB
@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return "Job not found", 404

    if request.method == "POST":
        job.client_name = request.form.get("client_name")

        upload_dir = os.path.join("static", "uploads", str(job.id))
        os.makedirs(upload_dir, exist_ok=True)
        for file in request.files.getlist("job_files"):
            if file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(upload_dir, filename))

        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")
        thicknesses = request.form.getlist("thicknesses")

        new_parts = []
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                new_parts.extend([(float(w), float(h), t)] * int(q))

        for w, h, t in new_parts:
            db.add(Part(job_id=job.id, width=w, height=h, thickness=t))

        db.commit()

        all_parts = db.query(Part).filter(Part.job_id == job.id).all()
        parts_tuples = [(p.width, p.height) for p in all_parts]

        sheets = optimize_cuts(96, 48, parts_tuples)
        sheet_dir = job.image_folder

        # ✅ Fixed: remove entire directory safely
        if os.path.exists(sheet_dir):
            shutil.rmtree(sheet_dir)
        os.makedirs(sheet_dir, exist_ok=True)

        draw_sheets_to_files(sheets, sheet_dir)

        db.close()
        flash("Job updated.")
        return redirect(url_for("job_details", job_id=job.id))

    db.close()
    return render_template("edit_job.html", job=job, user=user)



# ✅ DELETE JOB
@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if job:
        if os.path.exists(job.image_folder):
            shutil.rmtree(job.image_folder)
        upload_dir = f"static/uploads/{job.id}"
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        db.delete(job)
        db.commit()
    db.close()
    flash("Job deleted successfully.")
    return redirect(url_for("jobs"))

# ✅ SET FINAL PRICE
@app.route("/jobs/<int:job_id>/set_price", methods=["POST"])
def set_price(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    new_price = request.form.get("final_price")
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if job:
        job.final_price = new_price
        db.commit()
    db.close()
    flash("Final price updated.")
    return redirect(url_for("job_details", job_id=job_id))

# ✅ SAVE ESTIMATE
@app.route("/jobs/<int:job_id>/save_estimate", methods=["POST"])
def save_estimate(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    amount = request.form.get("amount")
    if not amount:
        flash("No amount provided for the estimate.")
        return redirect(url_for("job_details", job_id=job_id))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()

    if job:
        try:
            new_estimate = Estimate(job_id=job_id, amount=float(amount))
            db.add(new_estimate)
            db.commit()
            flash("Estimate saved successfully.")
        except Exception as e:
            db.rollback()
            flash(f"Error saving estimate: {str(e)}")
    else:
        flash("Job not found or unauthorized access.")

    db.close()
    return redirect(url_for("job_details", job_id=job_id))


if __name__ == "__main__":
    app.run(debug=True)
