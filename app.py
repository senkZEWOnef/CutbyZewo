from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, uuid, shutil
from cabinet import generate_parts
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
from models import SessionLocal, Job, User, Estimate
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "Poesie509$$$"

# Ensure static folder for sheets
os.makedirs("static/sheets", exist_ok=True)

def current_user():
    uid = session.get("user_id")
    if uid:
        db = SessionLocal()
        user = db.query(User).filter(User.id == uid).first()
        db.close()
        return user
    return None

# ------------------------
# ✅ MAIN INDEX / PLANNER
# ------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if not current_user():
        return redirect(url_for("login"))

    if request.method == "POST":
        client_name = request.form.get("client_name")
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")

        parts = []
        for w, h, q in zip(widths, heights, quantities):
            parts.extend([(float(w), float(h))] * int(q))

        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))

        sheets = optimize_cuts(panel_width, panel_height, parts)
        job_uuid = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_uuid}"
        os.makedirs(output_dir)
        draw_sheets_to_files(sheets, output_dir)

        db = SessionLocal()
        new_job = Job(
            client_name=client_name,
            notes="Created by Cut Planner",
            image_folder=output_dir
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        db.close()

        return redirect(url_for("job_details", job_id=new_job.id))

    return render_template("index.html", user=current_user())

# ------------------------
# ✅ AUTH
# ------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        hashed_pw = generate_password_hash(password)
        db = SessionLocal()
        new_user = User(username=username, email=email, hashed_password=hashed_pw)
        db.add(new_user)
        db.commit()
        db.close()
        flash("Signup successful! Please login.")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        db.close()
        if user and check_password_hash(user.hashed_password, password):
            session["user_id"] = user.id
            return redirect(url_for("index"))
        else:
            flash("Invalid email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully.")
    return redirect(url_for("login"))

# ------------------------
# ✅ JOBS LIST & DETAILS
# ------------------------
@app.route("/jobs")
def jobs():
    if not current_user():
        return redirect(url_for("login"))
    db = SessionLocal()
    all_jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    return render_template("jobs.html", jobs=all_jobs, user=current_user())

@app.route("/jobs/<int:job_id>")
def job_details(job_id):
    if not current_user():
        return redirect(url_for("login"))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    estimates = db.query(Estimate).filter(Estimate.job_id == job_id).order_by(Estimate.created_at.desc()).all()
    db.close()

    if not job:
        return "Job not found", 404

    sheets_subfolder = os.path.relpath(job.image_folder, "static")
    sheet_images = []
    if os.path.exists(job.image_folder):
        files = sorted(f for f in os.listdir(job.image_folder) if f.endswith(".png"))
        sheet_images = [f"{sheets_subfolder}/{file}" for file in files]

    return render_template(
        "job_details.html",
        job=job,
        sheet_images=sheet_images,
        estimates=estimates,
        user=current_user()
    )

# ------------------------
# ✅ JOB ACTIONS: EDIT, DELETE, PRICE, ESTIMATES
# ------------------------
@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    if not current_user():
        return redirect(url_for("login"))
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return "Job not found", 404

    if request.method == "POST":
        new_name = request.form.get("client_name")
        job.client_name = new_name
        db.commit()
        db.close()
        flash("Job updated.")
        return redirect(url_for("job_details", job_id=job.id))

    db.close()
    return render_template("edit_job.html", job=job, user=current_user())

@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    if not current_user():
        return redirect(url_for("login"))
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        if os.path.exists(job.image_folder):
            shutil.rmtree(job.image_folder)
        db.delete(job)
        db.commit()
    db.close()
    flash("Job deleted.")
    return redirect(url_for("jobs"))

@app.route("/jobs/<int:job_id>/set_price", methods=["POST"])
def set_price(job_id):
    if not current_user():
        return redirect(url_for("login"))
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        price = request.form.get("final_price")
        job.final_price = float(price)
        db.commit()
    db.close()
    flash("Final price updated.")
    return redirect(url_for("job_details", job_id=job_id))

@app.route("/jobs/<int:job_id>/save_estimate", methods=["POST"])
def save_estimate(job_id):
    if not current_user():
        return redirect(url_for("login"))
    amount = float(request.form.get("amount"))
    db = SessionLocal()
    new_estimate = Estimate(job_id=job_id, amount=amount)
    db.add(new_estimate)
    db.commit()
    db.close()
    flash("Estimate saved successfully.")
    return redirect(url_for("job_details", job_id=job_id))

@app.route("/jobs/<int:job_id>/export")
def export_job_pdf(job_id):
    return f"PDF export for job {job_id} is not implemented yet.", 200

# ------------------------
# ✅ MAIN ENTRYPOINT
# ------------------------
if __name__ == "__main__":
    app.run(debug=True)
