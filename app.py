# ✅ Imports
from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, uuid, shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client, Client

from flask import send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Image
from io import BytesIO
from PIL import Image
import glob



# ✅ Optimization
from planner import optimize_cuts
from visualizer import draw_sheets_to_files

# ✅ Supabase Init
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = "Poesie509$$$"

# ✅ Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

# ✅ Session helper (Supabase-only)
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    response = supabase.table("users").select("*").eq("id", uid).single().execute()
    return response.data if response.data else None

# ✅ SIGNUP with Supabase Auth
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        # ✅ 1. Create user with Supabase Auth
        result = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        if result.get("error"):
            flash(f"Error: {result['error']['message']}")
            return redirect(url_for("signup"))

        # ✅ 2. Add to users table with same UUID
        user_id = result['user']['id']
        supabase.table("users").insert({
            "id": user_id,
            "username": username,
            "email": email
        }).execute()

        flash("Account created! Please log in.")
        return redirect(url_for("login"))

    return render_template("signup.html")



# ✅ LOGIN with Supabase Auth
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if result.get("error"):
            flash("Invalid email or password.")
            print("❌ Login error:", result["error"]["message"])
            return redirect(url_for("login"))

        user = result["user"]
        session["user_id"] = user["id"]
        print("✅ Logged in:", user["email"])

        return redirect(url_for("jobs"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    # If you want to clear Supabase session server-side later, you can store it in session and call sign_out here.
    session.pop("user_id", None)
    flash("Logged out.")
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
def index():
    if "user_id" not in session:
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
        soft_deadline = datetime.strptime(soft_deadline, "%Y-%m-%d") if soft_deadline else None
        hard_deadline = datetime.strptime(hard_deadline, "%Y-%m-%d") if hard_deadline else None

        parts_by_thickness = {}
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                parts_by_thickness.setdefault(t, []).extend([(float(w), float(h))] * int(q))

        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))

        job_uuid = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_uuid}"
        os.makedirs(output_dir, exist_ok=True)

        # ✅ Create job in Supabase
        job_resp = supabase.table("jobs").insert({
            "id": job_uuid,
            "client_name": client_name,
            "user_id": user_id
        }).execute()
        assert job_resp.status_code == 201

        sheet_images = []

        for t, parts in parts_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            sheets = optimize_cuts(panel_width, panel_height, parts)
            draw_sheets_to_files(sheets, subfolder)

            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append((rel, t))

            # ✅ Upload all parts
            supabase.table("parts").insert([
                {
                    "job_id": job_uuid,
                    "width": w,
                    "height": h,
                    "material": t
                }
                for w, h in parts
            ]).execute()

        # ✅ Optional: save deadline
        if soft_deadline or hard_deadline:
            supabase.table("deadlines").insert({
                "job_id": job_uuid,
                "soft_deadline": soft_deadline,
                "hard_deadline": hard_deadline
            }).execute()

        # ✅ Upload local job files (optional)
        upload_dir = f"static/uploads/{job_uuid}"
        os.makedirs(upload_dir, exist_ok=True)
        if 'job_files' in request.files:
            files = request.files.getlist('job_files')
            for f in files:
                if f.filename:
                    filename = secure_filename(f.filename)
                    path = os.path.join(upload_dir, filename)
                    f.save(path)

        return render_template(
            "result.html",
            parts=[(w, h, t) for t, ps in parts_by_thickness.items() for (w, h) in ps],
            sheet_images=sheet_images
        )

    return render_template("index.html")

@app.route("/jobs")
def jobs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # ✅ Fetch jobs from Supabase for this user
    response = supabase.table("jobs") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    if response.status_code != 200:
        flash("Could not fetch jobs.")
        return render_template("jobs.html", jobs=[], user={"id": user_id})

    jobs = response.data
    return render_template("jobs.html", jobs=jobs, user={"id": user_id})





# ✅ JOB DETAILS
@app.route("/jobs/<uuid:job_id>", methods=["GET", "POST"])
def job_details(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    # ✅ Fetch job from Supabase
    job_res = supabase.table("jobs").select("*").eq("id", str(job_id)).single().execute()
    job = job_res.data

    if not job:
        return "Job not found", 404

    # ✅ Handle deadline form POST
    if request.method == "POST":
        soft_deadline = request.form.get("soft_deadline")
        hard_deadline = request.form.get("hard_deadline")

        update_data = {}
        if soft_deadline:
            update_data["soft_deadline"] = soft_deadline
        if hard_deadline:
            update_data["hard_deadline"] = hard_deadline

        if update_data:
            supabase.table("deadlines").upsert({
                "job_id": str(job_id),
                **update_data
            }).execute()
            flash("Deadlines updated.", "success")
            return redirect(url_for("job_details", job_id=job_id))

    # ✅ Fetch parts and estimates
    parts_res = supabase.table("parts").select("*").eq("job_id", str(job_id)).execute()
    estimates_res = supabase.table("estimates").select("*").eq("job_id", str(job_id)).order("created_at", desc=True).execute()

    parts = parts_res.data or []
    estimates = estimates_res.data or []

    # ✅ Sheets (3/4, 1/2, 1/4 inch)
    sheet_images = []
    image_folder = job.get("image_folder")
    if image_folder and os.path.exists(image_folder):
        found_any = False
        for thickness in ["3/4", "1/2", "1/4"]:
            subfolder = os.path.join(image_folder, thickness)
            if os.path.exists(subfolder):
                found_any = True
                files = sorted(f for f in os.listdir(subfolder) if f.endswith(".png"))
                for f in files:
                    relative_path = f"sheets/{os.path.basename(image_folder)}/{thickness}/{f}"
                    sheet_images.append((relative_path, thickness))
        if not found_any:
            files = sorted(f for f in os.listdir(image_folder) if f.endswith(".png"))
            for f in files:
                relative_path = f"sheets/{os.path.basename(image_folder)}/{f}"
                sheet_images.append((relative_path, "Unknown"))

    # ✅ Uploaded job files
    upload_dir = f"static/uploads/{job_id}"
    uploaded_images = []
    if os.path.exists(upload_dir):
        uploaded_images = [
            f"uploads/{job_id}/{f}"
            for f in os.listdir(upload_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]

    return render_template(
        "job_details.html",
        job=job,
        estimates=estimates,
        parts=parts,
        sheet_images=sheet_images,
        uploaded_images=uploaded_images,
        user=user
    )


# ✅ EDIT JOB (Supabase)
@app.route("/jobs/<uuid:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    job_res = supabase.table("jobs").select("*").eq("id", str(job_id)).single().execute()
    job = job_res.data

    if not job:
        return "Job not found", 404

    if request.method == "POST":
        client_name = request.form.get("client_name")
        supabase.table("jobs").update({"client_name": client_name}).eq("id", str(job_id)).execute()

        upload_dir = os.path.join("static", "uploads", str(job_id))
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

        # Delete old parts
        supabase.table("parts").delete().eq("job_id", str(job_id)).execute()

        # Insert new parts
        supabase.table("parts").insert([
            {"job_id": str(job_id), "width": w, "height": h, "material": t}
            for w, h, t in new_parts
        ]).execute()

        # Optimize cuts
        parts_tuples = [(w, h) for w, h, t in new_parts]
        sheet_dir = f"static/sheets/{job_id}"

        if os.path.exists(sheet_dir):
            shutil.rmtree(sheet_dir)
        os.makedirs(sheet_dir, exist_ok=True)

        sheets = optimize_cuts(96, 48, parts_tuples)
        draw_sheets_to_files(sheets, sheet_dir)

        flash("Job updated.")
        return redirect(url_for("job_details", job_id=job_id))

    return render_template("edit_job.html", job=job, user=user)



# ✅ DELETE JOB (Supabase)
@app.route("/jobs/<uuid:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    # ✅ Step 1: Fetch the job to confirm it's owned by the user
    job_res = supabase.table("jobs").select("*").eq("id", str(job_id)).eq("user_id", user["id"]).single().execute()
    job = job_res.data

    if job:
        # ✅ Step 2: Delete local image folder
        if job.get("image_folder") and os.path.exists(job["image_folder"]):
            shutil.rmtree(job["image_folder"])

        # ✅ Step 3: Delete uploaded files
        upload_dir = f"static/uploads/{job_id}"
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)

        # ✅ Step 4: Delete job in Supabase (cascade removes parts, deadlines, etc.)
        supabase.table("jobs").delete().eq("id", str(job_id)).execute()

        flash("Job deleted successfully.")
    else:
        flash("Job not found or unauthorized.", "danger")

    return redirect(url_for("jobs"))


# ✅ SET FINAL PRICE (Supabase)
@app.route("/jobs/<uuid:job_id>/set_price", methods=["POST"])
def set_price(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    new_price = request.form.get("final_price")

    # ✅ Step 1: Make sure this job belongs to the current user
    job_res = supabase.table("jobs").select("id").eq("id", str(job_id)).eq("user_id", user["id"]).single().execute()
    if job_res.data:
        # ✅ Step 2: Update the price
        supabase.table("jobs").update({"final_price": new_price}).eq("id", str(job_id)).execute()
        flash("Final price updated.")
    else:
        flash("Unauthorized or job not found.", "danger")

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

@app.route("/stocks")
def view_stocks():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # ✅ Fetch all stocks (shared across users)
    response = supabase.table("stocks").select("*").order("created_at", desc=True).execute()
    stocks = response.data if response.data else []

    return render_template("stocks.html", stocks=stocks, user={"id": user_id})


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

    # ✅ Insert into Supabase
    supabase.table("stocks").insert({
        "name": name,
        "category": category,
        "quantity": quantity,
        "unit": unit,
        "code": code,
        "color": color
    }).execute()

    flash("Stock item added.")
    return redirect(url_for("view_stocks"))


@app.route("/stocks/<stock_id>/update", methods=["POST"])
def update_stock(stock_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    action = request.form.get("action")

    # ✅ Fetch current quantity
    response = supabase.table("stocks").select("quantity").eq("id", stock_id).single().execute()
    data = response.data

    if data:
        current_qty = data["quantity"] or 0
        if action == "increase":
            new_qty = current_qty + 1
        elif action == "decrease":
            new_qty = max(0, current_qty - 1)
        else:
            new_qty = current_qty  # Unknown action fallback

        # ✅ Update
        supabase.table("stocks").update({"quantity": new_qty}).eq("id", stock_id).execute()

    return redirect(url_for("view_stocks"))


@app.route("/stocks/<stock_id>/delete", methods=["POST"])
def delete_stock(stock_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # ✅ Attempt to delete the stock item
    response = supabase.table("stocks").delete().eq("id", stock_id).execute()

    if response.status_code == 200 and response.data:
        flash("Stock item deleted.")
    else:
        flash("Stock item not found or could not be deleted.", "error")

    return redirect(url_for("view_stocks"))


@app.route("/jobs/<uuid:job_id>/export_pdf")
def export_pdf(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    # ✅ Fetch job data
    job_res = supabase.table("jobs").select("*").eq("id", str(job_id)).single().execute()
    job = job_res.data
    if not job:
        return "Job not found", 404

    parts_res = supabase.table("parts").select("*").eq("job_id", str(job_id)).execute()
    parts = parts_res.data or []

    # ✅ Generate PDF
    output_path = f"static/pdfs/{job_id}.pdf"
    os.makedirs("static/pdfs", exist_ok=True)

    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    y = height - inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, "Cut Planner Summary")
    y -= inch

    c.setFont("Helvetica", 12)
    c.drawString(inch, y, f"Client: {job.get('client_name', 'N/A')}")
    y -= 20
    c.drawString(inch, y, f"Final Price: ${job.get('final_price', 'N/A')}")
    y -= 20
    c.drawString(inch, y, f"Soft Deadline: {job.get('soft_deadline', 'N/A')}")
    y -= 20
    c.drawString(inch, y, f"Hard Deadline: {job.get('hard_deadline', 'N/A')}")
    y -= 30

    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y, "Parts List")
    y -= 20

    c.setFont("Helvetica", 12)
    for i, part in enumerate(parts):
        line = f"{i+1}. {part['width']} x {part['height']} inches — {part['material']} panel"
        c.drawString(inch, y, line)
        y -= 15
        if y < 100:
            c.showPage()
            y = height - inch

    c.save()

    return send_file(output_path, as_attachment=True)


@app.route("/jobs/<uuid:job_id>/download", methods=["GET"])
def download_job_pdf(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    # ✅ Fetch job data
    job_res = supabase.table("jobs").select("*").eq("id", str(job_id)).single().execute()
    parts_res = supabase.table("parts").select("*").eq("job_id", str(job_id)).execute()
    estimates_res = supabase.table("estimates").select("*").eq("job_id", str(job_id)).order("created_at", desc=True).execute()

    job = job_res.data
    parts = parts_res.data or []
    estimates = estimates_res.data or []

    if not job:
        return "Job not found", 404

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    def draw_line(text, offset=20, bold=False):
        nonlocal y
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 12)
        pdf.drawString(50, y, text)
        y -= offset

    draw_line(f"📄 Job Report — {job['client_name']}", bold=True)
    draw_line(f"Job ID: {job['id']}")
    draw_line(f"Created At: {job.get('created_at', '')}")
    draw_line(f"Final Price: ${job.get('final_price', 'N/A')}")
    draw_line(f"Soft Deadline: {job.get('soft_deadline', 'N/A')}")
    draw_line(f"Hard Deadline: {job.get('hard_deadline', 'N/A')}")
    draw_line("")

    draw_line("Cut Parts:", bold=True)
    if parts:
        for p in parts:
            draw_line(f"- {p['width']} x {p['height']} inches ({p['material']})")
    else:
        draw_line("No parts found.")

    draw_line("")

    draw_line("Past Estimates:", bold=True)
    if estimates:
        for e in estimates:
            draw_line(f"- ${e['amount']} on {e['created_at']}")
    else:
        draw_line("No estimates found.")

    pdf.showPage()

    # ✅ Cut Sheet Images
    sheet_path = os.path.join("static", "sheets", str(job_id))
    if os.path.exists(sheet_path):
        for img_path in glob.glob(f"{sheet_path}/**/*.png", recursive=True):
            try:
                img = Image.open(img_path)
                img_width, img_height = img.size
                ratio = min(width / img_width, height / img_height)
                resized_w = img_width * ratio * 0.9
                resized_h = img_height * ratio * 0.9

                pdf.drawImage(img_path, x=30, y=height - resized_h - 40, width=resized_w, height=resized_h)
                pdf.showPage()
            except Exception as e:
                print(f"Error loading sheet image: {img_path}, {e}")

    # ✅ Uploaded Files
    upload_path = os.path.join("static", "uploads", str(job_id))
    if os.path.exists(upload_path):
        for img_path in glob.glob(f"{upload_path}/*"):
            try:
                img = Image.open(img_path)
                img_width, img_height = img.size
                ratio = min(width / img_width, height / img_height)
                resized_w = img_width * ratio * 0.9
                resized_h = img_height * ratio * 0.9

                pdf.drawImage(img_path, x=30, y=height - resized_h - 40, width=resized_w, height=resized_h)
                pdf.showPage()
            except Exception as e:
                print(f"Error loading uploaded file: {img_path}, {e}")

    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"job_{job_id}.pdf", mimetype='application/pdf')






if __name__ == "__main__":
    app.run(debug=True)
