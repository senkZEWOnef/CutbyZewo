from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, uuid, shutil
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
from models import SessionLocal, Job, User, Estimate, Part, Base, engine, Stock
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime




# ✅ Auto-create tables
Base.metadata.create_all(bind=engine)



app = Flask(__name__)
app.secret_key = "Poesie509$$$"

# ✅ Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)


@app.before_first_request
def create_default_user():
    db = SessionLocal()
    if not db.query(User).filter_by(email="ralph.ulysse509@gmail.com").first():
        from werkzeug.security import generate_password_hash
        user = User(
            username="ralph",
            email="ralph.ulysse509@gmail.com",
            hashed_password=generate_password_hash("Poesie509$$$")
        )
        db.add(user)
        db.commit()
    db.close()


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

        if not user:
            print("❌ User not found.")
        else:
            print("✅ User found:", user.email)
            print("✅ Stored hash:", user.hashed_password)
            print("✅ Password entered:", password)
            print("✅ Password check:", check_password_hash(user.hashed_password, password))

        if user and check_password_hash(user.hashed_password, password):
            session["user_id"] = user.id
            return redirect(url_for("view_jobs"))
        else:
            flash("Invalid email or password.")
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

        db = SessionLocal()
        new_job = Job(
            client_name=client_name,
            notes="Created by Cut Planner",
            image_folder=output_dir,
            user_id=user.id,
            soft_deadline=soft_deadline,
            hard_deadline=hard_deadline
        )
        db.add(new_job)
        db.commit()

        sheet_images = []
        for t, parts in parts_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            sheets = optimize_cuts(panel_width, panel_height, parts)
            draw_sheets_to_files(sheets, subfolder)

            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append((rel, t))

            for w, h in parts:
                db.add(Part(job_id=new_job.id, width=w, height=h, thickness=t))

        db.commit()

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
            parts=[(w, h, t) for t, ps in parts_by_thickness.items() for (w, h) in ps],
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
@app.route("/jobs/<int:job_id>", methods=["GET", "POST"])
def job_details(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        return "Job not found", 404

    # ✅ Handle deadline form POST
    if request.method == "POST":
        soft_deadline = request.form.get("soft_deadline")
        hard_deadline = request.form.get("hard_deadline")

        if soft_deadline:
            job.soft_deadline = soft_deadline
        if hard_deadline:
            job.hard_deadline = hard_deadline

        db.commit()
        flash("Deadlines updated.", "success")
        return redirect(url_for("job_details", job_id=job_id))

    # ✅ Estimates and parts
    estimates = db.query(Estimate).filter(Estimate.job_id == job_id).order_by(Estimate.created_at.desc()).all()
    parts = db.query(Part).filter(Part.job_id == job_id).all()

    # ✅ Sheets (3/4, 1/2, 1/4 inch)
    sheet_images = []
    if job and os.path.exists(job.image_folder):
        found_any = False
        for thickness in ["3/4", "1/2", "1/4"]:
            subfolder = os.path.join(job.image_folder, thickness)
            if os.path.exists(subfolder):
                found_any = True
                files = sorted(f for f in os.listdir(subfolder) if f.endswith(".png"))
                for f in files:
                    relative_path = f"sheets/{os.path.basename(job.image_folder)}/{thickness}/{f}"
                    sheet_images.append((relative_path, thickness))
        if not found_any:
            files = sorted(f for f in os.listdir(job.image_folder) if f.endswith(".png"))
            for f in files:
                relative_path = f"sheets/{os.path.basename(job.image_folder)}/{f}"
                sheet_images.append((relative_path, "Unknown"))

    # ✅ Uploaded images
    upload_dir = f"static/uploads/{job.id}"
    uploaded_images = []
    if os.path.exists(upload_dir):
        uploaded_images = [f"uploads/{job.id}/{f}" for f in os.listdir(upload_dir)]

    db.close()

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

@app.route("/stocks")
def view_stocks():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    db = SessionLocal()
    stocks = db.query(Stock).order_by(Stock.created_at.desc()).all()
    db.close()
    return render_template("stocks.html", stocks=stocks, user=user)

@app.route("/stocks/add", methods=["POST"])
def add_stock():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    name = request.form.get("name")
    description = request.form.get("description")
    quantity = int(request.form.get("quantity") or 0)
    unit = request.form.get("unit")

    db = SessionLocal()
    stock = Stock(name=name, description=description, quantity=quantity, unit=unit)
    db.add(stock)
    db.commit()
    db.close()
    flash("Stock item added.")
    return redirect(url_for("view_stocks"))

@app.route("/stocks/<int:stock_id>/update", methods=["POST"])
def update_stock(stock_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    action = request.form.get("action")
    db = SessionLocal()
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if stock:
        if action == "increase":
            stock.quantity += 1
        elif action == "decrease":
            stock.quantity = max(0, stock.quantity - 1)
        db.commit()
    db.close()
    return redirect(url_for("view_stocks"))

@app.route("/stocks/<int:stock_id>/delete", methods=["POST"])
def delete_stock(stock_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    db = SessionLocal()
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if stock:
        db.delete(stock)
        db.commit()
        flash("Stock item deleted.")
    db.close()
    return redirect(url_for("view_stocks"))






if __name__ == "__main__":
    app.run(debug=True)
