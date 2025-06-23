from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, uuid, shutil
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
from models import SessionLocal, Job, User, Estimate, Part
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "Poesie509$$$"

# ✅ Make sure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

def current_user():
    uid = session.get("user_id")
    if uid:
        db = SessionLocal()
        user = db.query(User).filter(User.id == uid).first()
        db.close()
        return user
    return None

@app.route("/", methods=["GET", "POST"])
def index():
 
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

        # ✅ Save parts
        for w, h in parts:
            db.add(Part(job_id=new_job.id, width=w, height=h))
        db.commit()

        # ✅ Save uploads if any
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

        sheet_images = [f"sheets/{job_uuid}/sheet_{i+1}.png" for i in range(len(sheets))]

        return render_template(
            "result.html",
            parts=parts,
            sheet_images=sheet_images,
            user=current_user()
        )

    return render_template("index.html", user=current_user())

@app.route("/jobs")
def jobs():
    db = SessionLocal()
    all_jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    return render_template("jobs.html", jobs=all_jobs, user=current_user())

@app.route("/jobs/<int:job_id>")
def job_details(job_id):
  

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    estimates = db.query(Estimate).filter(Estimate.job_id == job_id).order_by(Estimate.created_at.desc()).all()
    parts = db.query(Part).filter(Part.job_id == job_id).all()
    db.close()

    if not job:
        return "Job not found", 404

    # ✅ Cut Sheets
    sheets_subfolder = os.path.relpath(job.image_folder, "static")
    sheet_images = []
    if os.path.exists(job.image_folder):
        files = sorted(f for f in os.listdir(job.image_folder) if f.endswith(".png"))
        sheet_images = [f"sheets/{os.path.basename(job.image_folder)}/{file}" for file in files]

    # ✅ Uploaded Files
    upload_dir = f"static/uploads/{job.id}"
    uploaded_images = []
    if os.path.exists(upload_dir):
        uploaded_images = [f"uploads/{job.id}/{f}" for f in os.listdir(upload_dir)]

    return render_template(
        "job_details.html",
        job=job,
        sheet_images=sheet_images,
        uploaded_images=uploaded_images,
        estimates=estimates,
        parts=parts,
        user=current_user()
    )
@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return "Job not found", 404

    if request.method == "POST":
        # ✅ 1) Update name
        job.client_name = request.form.get("client_name")

        # ✅ 2) Save new uploaded files
        upload_dir = os.path.join("static", "uploads", str(job.id))
        os.makedirs(upload_dir, exist_ok=True)
        for file in request.files.getlist("job_files"):
            if file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(upload_dir, filename))

        # ✅ 3) Save new parts, if any
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")

        new_parts = []
        for w, h, q in zip(widths, heights, quantities):
            if w and h and q:
                new_parts.extend([(float(w), float(h))] * int(q))

        for w, h in new_parts:
            db.add(Part(job_id=job.id, width=w, height=h))

        db.commit()

        # ✅ 4) Re-generate cut sheets
        all_parts = db.query(Part).filter(Part.job_id == job.id).all()
        parts_tuples = [(p.width, p.height) for p in all_parts]

        sheets = optimize_cuts(96, 48, parts_tuples)
        sheet_dir = job.image_folder

        # Clear old sheets first
        for f in os.listdir(sheet_dir):
            os.remove(os.path.join(sheet_dir, f))

        draw_sheets_to_files(sheets, sheet_dir)

        # ✅ 5) Get ID safely
        updated_id = job.id

        db.close()
        flash("Job updated.")
        return redirect(url_for("job_details", job_id=updated_id))

    db.close()
    return render_template("edit_job.html", job=job, user=current_user())


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):


    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
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

@app.route("/jobs/<int:job_id>/set_price", methods=["POST"])
def set_price(job_id):
   

    new_price = request.form.get("final_price")
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.final_price = new_price
        db.commit()
    db.close()
    flash("Final price updated.")
    return redirect(url_for("job_details", job_id=job_id))

@app.route("/jobs/<int:job_id>/save_estimate", methods=["POST"])
def save_estimate(job_id):
   

    amount = request.form.get("amount")
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        new_estimate = Estimate(job_id=job_id, amount=amount)
        db.add(new_estimate)
        db.commit()
    db.close()
    flash("Estimate saved.")
    return redirect(url_for("job_details", job_id=job_id))



# ✅ Keep signup, login, logout, set_price, save_estimate as they are
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
