# app.py
from flask import Flask, render_template, request, redirect, url_for, send_file
import shutil
from cabinet import generate_parts
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
import os
import uuid
from models import SessionLocal, Job
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        client_name = request.form.get("client_name")

        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")

        parts = []
        for w, h, q in zip(widths, heights, quantities):
            w = float(w)
            h = float(h)
            q = int(q)
            parts.extend([(w, h)] * q)

        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))

        sheets = optimize_cuts(panel_width, panel_height, parts)

        job_id = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_id}"
        os.makedirs(output_dir)

        draw_sheets_to_files(sheets, output_dir)
        sheet_images = [f"{job_id}/sheet_{i+1}.png" for i in range(len(sheets))]

        # Save job + files
        upload_dir = f"static/uploads/{job_id}"
        os.makedirs(upload_dir, exist_ok=True)

        # Save uploaded files
        if 'files' in request.files:
            files = request.files.getlist("files")
            for file in files:
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(upload_dir, filename))

        # DB save
        db = SessionLocal()
        new_job = Job(
            client_name=client_name,
            notes="Saved automatically by cut planner",
            image_folder=output_dir
        )
        db.add(new_job)
        db.commit()
        db.close()

        return render_template(
            "result.html",
            parts=parts,
            sheet_images=sheet_images
        )

    return render_template("index.html")

@app.route("/jobs")
def jobs():
    db = SessionLocal()
    all_jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    return render_template("jobs.html", jobs=all_jobs)

@app.route("/jobs/<int:job_id>")
def job_details(job_id):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    db.close()

    if not job:
        return "Job not found", 404

    sheets_subfolder = os.path.relpath(job.image_folder, "static")
    sheet_images = []
    if os.path.exists(job.image_folder):
        files = sorted(
            f for f in os.listdir(job.image_folder) if f.endswith(".png")
        )
        sheet_images = [f"{sheets_subfolder}/{file}" for file in files]

    upload_subfolder = f"uploads/{os.path.basename(job.image_folder)}"
    upload_dir = f"static/{upload_subfolder}"
    uploaded_files = []
    if os.path.exists(upload_dir):
        uploaded_files = [f"{upload_subfolder}/{f}" for f in os.listdir(upload_dir)]

    return render_template(
        "job_details.html",
        job=job,
        sheet_images=sheet_images,
        uploaded_files=uploaded_files
    )

@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return "Job not found", 404

    if os.path.exists(job.image_folder):
        shutil.rmtree(job.image_folder)
    upload_dir = f"static/uploads/{os.path.basename(job.image_folder)}"
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)

    db.delete(job)
    db.commit()
    db.close()
    return redirect(url_for('jobs'))

@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        return "Job not found", 404

    if request.method == "POST":
        new_name = request.form.get("client_name")
        job.client_name = new_name

        upload_dir = f"static/uploads/{os.path.basename(job.image_folder)}"
        os.makedirs(upload_dir, exist_ok=True)

        if 'files' in request.files:
            files = request.files.getlist("files")
            for file in files:
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(upload_dir, filename))

        db.commit()
        db.close()
        return redirect(url_for('jobs'))

    db.close()
    return render_template("edit_job.html", job=job)

@app.route("/jobs/<int:job_id>/export")
def export_job_pdf(job_id):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    db.close()

    if not job:
        return "Job not found", 404

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.drawString(100, height - 50, f"Client Name: {job.client_name}")
    c.drawString(100, height - 70, f"Created: {job.created_at}")

    y = height - 120
    files = sorted(f for f in os.listdir(job.image_folder) if f.endswith(".png"))
    for file in files:
        img_path = os.path.join(job.image_folder, file)
        c.drawImage(img_path, 100, y - 200, width=400, height=200)
        y -= 220
        if y < 100:
            c.showPage()
            y = height - 50

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"job_{job_id}.pdf", mimetype='application/pdf')

@app.route("/designer")
def designer():
    return render_template("designer.html")

if __name__ == "__main__":
    app.run(debug=True)
