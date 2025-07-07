# ✅ Imports
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response
from werkzeug.utils import secure_filename
from datetime import datetime
import os, uuid, shutil, glob
from io import BytesIO
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from supabase import create_client, Client
from planner import optimize_cuts
from visualizer import draw_sheets_to_files

# ✅ Supabase Init
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ✅ Flask Init
app = Flask(__name__)
app.secret_key = "Poesie509$$$"  # Consider moving to environment variable for production

# ✅ Ensure folders exist
os.makedirs("static/sheets", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

# ✅ Session helper (Supabase-only)
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None

    response = supabase.table("users").select("*").eq("id", uid).execute()
    users = response.data

    if not users:
        return None

    return users[0]

#Supabase authentication
def get_authenticated_supabase():
    access_token = request.cookies.get("access_token")
    if not access_token:
        flash("Session expired. Please log in again.", "warning")
        return None
    return supabase.postgrest.auth(access_token)


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
            # Step 1: Sign up with Supabase Auth
            auth_res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            if auth_res.user is None:
                flash("Signup failed. No user returned.", "danger")
                return redirect(url_for("signup"))

            user_id = auth_res.user.id
            access_token = auth_res.session.access_token if auth_res.session else None

            if not access_token:
                flash("Signup succeeded but session is missing. Please log in.", "warning")
                return redirect(url_for("login"))

            # Step 2: Insert user into users table using auth
            supa_auth = get_authenticated_supabase(access_token)
            supa_auth.table("users").insert({
                "id": user_id,
                "email": email,
                "username": username
            }).execute()

            # Step 3: Store session and cookie
            session["user_id"] = user_id
            response = make_response(redirect(url_for("home")))
            response.set_cookie("access_token", access_token)
            return response

        except Exception as e:
            print("Signup error:", e)
            flash("An error occurred during signup. Please try again.", "danger")
            return redirect(url_for("signup"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })


            session_obj = result.session
            if not session_obj:
                flash("Login failed. Please check your credentials.", "danger")
                return redirect(url_for("login"))

            access_token = session_obj.access_token
            user_id = result.user.id if result.user else None

            if not user_id:
                flash("Login succeeded but user data is missing.", "warning")
                return redirect(url_for("login"))

            # ✅ Store user_id in session and set access token cookie
            session["user_id"] = user_id
            response = make_response(redirect(url_for("home")))
            response.set_cookie("access_token", access_token)

            return response

        except Exception as e:
            print("Login error:", e)
            flash("Invalid credentials or Supabase error.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")

def logout():
    session.pop("user_id", None)
    
    # Remove token cookie
    response = make_response(redirect(url_for("login")))
    response.set_cookie("access_token", "", expires=0)
    
    flash("Logged out.")
    return response


@app.route("/", methods=["GET"])
def home():
    access_token = request.cookies.get("access_token")
    
    if "user_id" in session and access_token:
        # User is logged in, can choose to redirect or show custom content
        return render_template("landing.html")  # or redirect(url_for("jobs"))

    return render_template("landing.html")



@app.route("/create-job", methods=["GET", "POST"])
def create_job():
    if "user_id" not in session:
        flash("Please log in to create a job.", "warning")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    access_token = request.cookies.get("access_token")

    if not access_token:
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for("logout"))

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

        try:
            supabase.postgrest.auth(access_token).table("jobs").insert({
                "id": job_uuid,
                "client_name": client_name,
                "user_id": user_id
            }).execute()
        except Exception as e:
            print("Supabase job insert error:", e)
            flash("Job creation failed. Try again.", "danger")
            return redirect(url_for("create_job"))

        sheet_images = []
        for t, parts in parts_by_thickness.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)

            sheets = optimize_cuts(panel_width, panel_height, parts)
            draw_sheets_to_files(sheets, subfolder)

            for i in range(len(sheets)):
                rel = f"sheets/{job_uuid}/{t}/sheet_{i+1}.png"
                sheet_images.append((rel, t))

            try:
                supabase.table("parts").insert([
                    {
                        "job_id": job_uuid,
                        "width": w,
                        "height": h,
                        "material": t
                    }
                    for w, h in parts
                ]).execute()
            except Exception as e:
                print("Parts insert error:", e)
                flash("Failed to insert parts.", "warning")

        if soft_deadline or hard_deadline:
            try:
                supabase.table("deadlines").insert({
                    "job_id": job_uuid,
                    "soft_deadline": soft_deadline.isoformat() if soft_deadline else None,
                    "hard_deadline": hard_deadline.isoformat() if hard_deadline else None
                }).execute()
            except Exception as e:
                print("Deadline insert error:", e)
                flash("Failed to save deadlines.", "warning")

        upload_dir = f"static/uploads/{job_uuid}"
        os.makedirs(upload_dir, exist_ok=True)
        if 'job_files' in request.files:
            files = request.files.getlist('job_files')
            for f in files:
                if f.filename:
                    filename = secure_filename(f.filename)
                    f.save(os.path.join(upload_dir, filename))

        return render_template(
            "result.html",
            parts=[(w, h, t) for t, ps in parts_by_thickness.items() for (w, h) in ps],
            sheet_images=sheet_images
        )

    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in to view your dashboard.", "warning")
        return redirect(url_for("login"))

    return render_template("dashboard.html")

@app.route("/jobs")
def jobs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    access_token = request.cookies.get("access_token")  # 🔑 Needed for Supabase RLS

    try:
        jobs_resp = (
            supabase
            .postgrest.auth(access_token)
            .table("jobs")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        job_data = jobs_resp.data or []

        # ✅ Convert 'created_at' to datetime objects
        for job in job_data:
            if job.get("created_at"):
                try:
                    job["created_at"] = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
                except Exception as e:
                    print("Invalid date format:", job["created_at"], e)

        return render_template("jobs.html", jobs=job_data)

    except Exception as e:
        print("Error loading jobs:", e)
        flash("Could not load jobs. Please try again later.", "danger")
        return redirect(url_for("dashboard"))



@app.route("/jobs/<uuid:job_id>", methods=["GET", "POST"])
def job_details(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")
    authed = supabase.postgrest.auth(access_token)

    # ✅ Fetch job
    job_res = (
        authed
        .table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .single()
        .execute()
    )
    job = job_res.data
    if not job:
        return "Job not found", 404

    if isinstance(job.get("created_at"), str):
        try:
            job["created_at"] = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
        except Exception as e:
            print("⚠️ created_at parse error:", e)

    # ✅ Handle POST (save deadlines)
    if request.method == "POST":
        soft_deadline = request.form.get("soft_deadline")
        hard_deadline = request.form.get("hard_deadline")

        update_data = {}
        if soft_deadline:
            update_data["soft_deadline"] = soft_deadline
        if hard_deadline:
            update_data["hard_deadline"] = hard_deadline

        if update_data:
            authed.table("deadlines").upsert({
                "job_id": str(job_id),
                **update_data
            }).execute()

            flash("Deadlines updated.", "success")
            return redirect(url_for("job_details", job_id=job_id))

    # ✅ Fetch deadlines
    deadlines_res = (
        authed
        .table("deadlines")
        .select("*")
        .eq("job_id", str(job_id))
        .limit(1)
        .execute()
    )
    deadlines_list = deadlines_res.data or []
    deadlines = deadlines_list[0] if deadlines_list else {}

    job["soft_deadline"] = deadlines.get("soft_deadline")
    job["hard_deadline"] = deadlines.get("hard_deadline")

    for key in ["soft_deadline", "hard_deadline"]:
        if isinstance(job.get(key), str):
            try:
                job[key] = datetime.fromisoformat(job[key].replace("Z", "+00:00"))
            except:
                pass

    # ✅ Fetch parts
    parts_res = (
        authed
        .table("parts")
        .select("*")
        .eq("job_id", str(job_id))
        .execute()
    )
    parts = parts_res.data or []

    # ✅ Fetch estimates
    estimates_res = (
        authed
        .table("estimates")
        .select("*")
        .eq("job_id", str(job_id))
        .order("created_at", desc=True)
        .execute()
    )
    estimates = estimates_res.data or []

    # ✅ Sheet Images
    sheet_images = []
    sheet_dir = os.path.join("static", "sheets", str(job_id))
    if os.path.exists(sheet_dir):
        found_any = False
        for thickness in ["3/4", "1/2", "1/4"]:
            subfolder = os.path.join(sheet_dir, thickness)
            if os.path.exists(subfolder):
                found_any = True
                for f in sorted(os.listdir(subfolder)):
                    if f.endswith(".png"):
                        relative_path = f"sheets/{job_id}/{thickness}/{f}"
                        sheet_images.append((relative_path, thickness))
        if not found_any:
            for f in sorted(os.listdir(sheet_dir)):
                if f.endswith(".png"):
                    relative_path = f"sheets/{job_id}/{f}"
                    sheet_images.append((relative_path, "Unknown"))

    # ✅ Uploaded images
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




@app.route("/jobs/<uuid:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")

    # ✅ Fetch job (auth required)
    job_res = (
        supabase
        .postgrest.auth(access_token)
        .table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .single()
        .execute()
    )
    job = job_res.data
    if not job:
        return "Job not found", 404

    if request.method == "POST":
        client_name = request.form.get("client_name")
        soft_deadline = request.form.get("soft_deadline") or None
        hard_deadline = request.form.get("hard_deadline") or None

        # ✅ Update job
        update_data = {"client_name": client_name}
        supabase.postgrest.auth(access_token).table("jobs").update(update_data).eq("id", str(job_id)).execute()

        # ✅ Upsert deadlines
        if soft_deadline or hard_deadline:
            deadline_data = {"job_id": str(job_id)}
            if soft_deadline:
                deadline_data["soft_deadline"] = soft_deadline
            if hard_deadline:
                deadline_data["hard_deadline"] = hard_deadline

            supabase.postgrest.auth(access_token).table("deadlines").upsert(deadline_data).execute()

        # ✅ Handle uploads
        upload_dir = f"static/uploads/{job_id}"
        os.makedirs(upload_dir, exist_ok=True)
        if 'job_files' in request.files:
            for f in request.files.getlist('job_files'):
                if f.filename:
                    f.save(os.path.join(upload_dir, secure_filename(f.filename)))

        # ✅ New parts
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")
        thicknesses = request.form.getlist("thicknesses")

        new_parts_by_thickness = {}
        for w, h, q, t in zip(widths, heights, quantities, thicknesses):
            if w and h and q and t:
                new_parts_by_thickness.setdefault(t, []).extend([(float(w), float(h))] * int(q))

        # ✅ Fetch existing parts
        parts_res = (
            supabase
            .postgrest.auth(access_token)
            .table("parts")
            .select("width, height, material")
            .eq("job_id", str(job_id))
            .execute()
        )
        existing_parts = parts_res.data or []

        combined_parts = existing_parts[:]
        for t, new_parts in new_parts_by_thickness.items():
            for w, h in new_parts:
                combined_parts.append({"width": w, "height": h, "material": t})

        # ✅ Insert new parts
        if new_parts_by_thickness:
            supabase.postgrest.auth(access_token).table("parts").insert([
                {"job_id": str(job_id), "width": w, "height": h, "material": t}
                for t, plist in new_parts_by_thickness.items()
                for (w, h) in plist
            ]).execute()

        # ✅ Regenerate sheets
        panel_width = 96
        panel_height = 48
        output_dir = f"static/sheets/{job_id}"

        for t in ["3/4", "1/2", "1/4"]:
            subfolder = os.path.join(output_dir, t)
            if os.path.exists(subfolder):
                for f in os.listdir(subfolder):
                    os.remove(os.path.join(subfolder, f))

        sheet_map = {}
        for part in combined_parts:
            t = part["material"]
            sheet_map.setdefault(t, []).append((part["width"], part["height"]))

        for t, parts in sheet_map.items():
            subfolder = os.path.join(output_dir, t)
            os.makedirs(subfolder, exist_ok=True)
            sheets = optimize_cuts(panel_width, panel_height, parts)
            draw_sheets_to_files(sheets, subfolder)

        return redirect(url_for("job_details", job_id=job_id))

    # ✅ Parse date
    from datetime import datetime
    for key in ["soft_deadline", "hard_deadline"]:
        if isinstance(job.get(key), str):
            try:
                job[key] = datetime.fromisoformat(job[key].replace("Z", "+00:00"))
            except:
                pass

    return render_template("edit_job.html", job=job, user=user)




@app.route("/jobs/<uuid:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")

    # ✅ Step 1: Fetch job with access token
    job_res = (
        supabase
        .postgrest.auth(access_token)
        .table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .eq("user_id", user["id"])
        .single()
        .execute()
    )
    job = job_res.data

    if job:
        # ✅ Step 2: Delete local sheet images
        image_folder = f"static/sheets/{job_id}"
        if os.path.exists(image_folder):
            shutil.rmtree(image_folder)

        # ✅ Step 3: Delete uploaded files
        upload_dir = f"static/uploads/{job_id}"
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)

        # ✅ Step 4: Delete from Supabase (jobs, parts, deadlines, estimates)
        supabase.postgrest.auth(access_token).table("parts").delete().eq("job_id", str(job_id)).execute()
        supabase.postgrest.auth(access_token).table("deadlines").delete().eq("job_id", str(job_id)).execute()
        supabase.postgrest.auth(access_token).table("estimates").delete().eq("job_id", str(job_id)).execute()
        supabase.postgrest.auth(access_token).table("jobs").delete().eq("id", str(job_id)).execute()

        flash("Job deleted successfully.")
    else:
        flash("Job not found or unauthorized.", "danger")

    return redirect(url_for("jobs"))



#Set price route
@app.route("/jobs/<uuid:job_id>/set_price", methods=["POST"])
def set_price(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")
    new_price = request.form.get("final_price")

    # ✅ Step 1: Verify ownership using RLS-authenticated query
    job_res = (
        supabase
        .postgrest.auth(access_token)
        .table("jobs")
        .select("id")
        .eq("id", str(job_id))
        .eq("user_id", user["id"])
        .single()
        .execute()
    )

    if job_res.data:
        # ✅ Step 2: Update the final_price with token
        (
            supabase
            .postgrest.auth(access_token)
            .table("jobs")
            .update({"final_price": new_price})
            .eq("id", str(job_id))
            .execute()
        )
        flash("Final price updated.")
    else:
        flash("Unauthorized or job not found.", "danger")

    return redirect(url_for("job_details", job_id=job_id))




#Save Estimate route
@app.route("/jobs/<uuid:job_id>/save_estimate", methods=["POST"])
def save_estimate(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")
    amount = request.form.get("amount")
    if not amount:
        flash("No amount provided for the estimate.")
        return redirect(url_for("job_details", job_id=job_id))

    try:
        # ✅ Step 1: Check if job belongs to user (with token for RLS)
        job_res = (
            supabase
            .postgrest.auth(access_token)
            .table("jobs")
            .select("id", "user_id")
            .eq("id", str(job_id))
            .single()
            .execute()
        )
        job = job_res.data

        if not job or job["user_id"] != user["id"]:
            flash("Job not found or unauthorized access.")
            return redirect(url_for("job_details", job_id=job_id))

        # ✅ Step 2: Save estimate (with auth)
        (
            supabase
            .postgrest.auth(access_token)
            .table("estimates")
            .insert({
                "job_id": str(job_id),
                "amount": float(amount)
            })
            .execute()
        )

        flash("Estimate saved successfully.")
    except Exception as e:
        flash(f"Error saving estimate: {str(e)}")

    return redirect(url_for("job_details", job_id=job_id))




#View stocks route@app.route("/stocks")
@app.route("/stocks", endpoint="view_stocks")
def view_stocks():

    user_id = session.get("user_id")
    access_token = request.cookies.get("access_token")

    if not user_id or not access_token:
        return redirect(url_for("login"))

    try:
        # ✅ Fetch stocks with access_token for RLS
        response = (
            supabase
            .postgrest.auth(access_token)
            .table("stocks")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        stocks = response.data if response.data else []
    except Exception as e:
        print("Error loading stocks:", e)
        stocks = []
        flash("Failed to load stock inventory.", "danger")

    return render_template("stocks.html", stocks=stocks, user={"id": user_id}, )




#Add stock route
@app.route("/stocks/add", methods=["POST"])
def add_stock():
    user_id = session.get("user_id")
    access_token = request.cookies.get("access_token")

    if not user_id or not access_token:
        return redirect(url_for("login"))

    name = request.form.get("name")
    category = request.form.get("category") or "Uncategorized"
    quantity = int(request.form.get("quantity") or 0)
    unit = request.form.get("unit")
    code = request.form.get("code") or None
    color = request.form.get("color") or None

    try:
        supabase.postgrest.auth(access_token).table("stocks").insert({
            "user_id": user_id,  # ✅ Required for RLS
            "name": name,
            "category": category,
            "quantity": quantity,
            "unit": unit,
            "code": code,
            "color": color
        }).execute()
        flash("Stock item added.")
    except Exception as e:
        print("Error adding stock:", e)
        flash("Failed to add stock item.", "danger")

    return redirect(url_for("view_stocks"))




#Update Stock route
@app.route("/stocks/<stock_id>/update", methods=["POST"])
def update_stock(stock_id):
    user_id = session.get("user_id")
    access_token = request.cookies.get("access_token")

    if not user_id or not access_token:
        return redirect(url_for("login"))

    action = request.form.get("action")

    try:
        # ✅ Fetch current quantity securely with auth
        response = (
            supabase
            .postgrest
            .auth(access_token)
            .table("stocks")
            .select("quantity")
            .eq("user_id", user_id) 
            .eq("id", stock_id)
            .single()
            .execute()
        )
        data = response.data
    except Exception as e:
        print("Error fetching stock:", e)
        flash("Stock update failed.", "danger")
        return redirect(url_for("view_stocks"))

    if data:
        current_qty = data["quantity"] or 0
        new_qty = current_qty
        if action == "increase":
            new_qty += 1
        elif action == "decrease":
            new_qty = max(0, current_qty - 1)

        try:
            # ✅ Update with auth
            (
                supabase
                .postgrest
                .auth(access_token)
                .table("stocks")
                .update({"quantity": new_qty})
                .eq("id", stock_id)
                .execute()
            )
            flash("Stock updated.")
        except Exception as e:
            print("Error updating stock:", e)
            flash("Stock update failed.", "danger")

    return redirect(url_for("view_stocks"))



#Deletre stock route
@app.route("/stocks/<uuid:stock_id>/delete", methods=["POST"])
def delete_stock(stock_id):
    user = current_user()
    access_token = request.cookies.get("access_token")

    if not user or not access_token:
        return redirect(url_for("login"))

    try:
        response = (
            supabase
            .postgrest
            .auth(access_token)
            .table("stocks")
            .delete()
            .eq("id", str(stock_id))
            .execute()
        )

        if response.data:
            flash("Stock deleted successfully.", "success")
        else:
            flash("Failed to delete stock. It may not exist or be unauthorized.", "danger")

    except Exception as e:
        print("Stock delete error:", e)
        flash("Error deleting stock.", "danger")

    return redirect(url_for("view_stocks"))



#pdf routeßß
@app.route("/jobs/<uuid:job_id>/download", methods=["GET"])
def download_job_pdf(job_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    access_token = request.cookies.get("access_token")
    if not access_token:
        return redirect(url_for("login"))
    
    job_res = (
        supabase.postgrest.auth(access_token)
        .table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .single()
        .execute()
    )

    parts_res = (
        supabase.postgrest.auth(access_token)
        .table("parts")
        .select("*")
        .eq("job_id", str(job_id))
        .execute()
    )

    estimates_res = (
        supabase.postgrest.auth(access_token)
        .table("estimates")
        .select("*")
        .eq("job_id", str(job_id))
        .order("created_at", desc=True)
        .execute()
    )

    job = job_res.data
    parts = parts_res.data or []
    estimates = estimates_res.data or []

    if not job:
        return "Job not found", 404

    def fmt(dt):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).strftime("%b %d, %Y")
        except:
            return dt

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - inch
    page_number = 1

    def draw_header(title="Job Report"):
        nonlocal y
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(inch, y, f"📄 {title}")
        y -= 30

    def draw_line(text, offset=20, bold=False):
        nonlocal y
        if y < 100:
            pdf.drawString(inch, 40, f"Page {page_number}")
            pdf.showPage()
            y = height - inch
            draw_header()
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 12)
        pdf.drawString(inch, y, text)
        y -= offset

    # ✅ Header
    draw_header()
    draw_line(f"Client: {job.get('client_name', 'N/A')}", bold=True)
    draw_line(f"Job ID: {job.get('id')}")
    draw_line(f"Created At: {fmt(job.get('created_at', ''))}")
    draw_line(f"Final Price: ${job.get('final_price', 'N/A')}")
    draw_line(f"Soft Deadline: {fmt(job.get('soft_deadline', 'N/A'))}")
    draw_line(f"Hard Deadline: {fmt(job.get('hard_deadline', 'N/A'))}")
    draw_line("")

    # ✅ Parts
    draw_line("Cut Parts:", bold=True)
    if parts:
        grouped = {}
        for p in parts:
            t = p["material"]
            grouped.setdefault(t, []).append(p)
        for material, group in grouped.items():
            draw_line(f"{material} Panel — {len(group)} parts")
            for p in group:
                draw_line(f"  • {p['width']} x {p['height']} in")
    else:
        draw_line("No parts found.")
    draw_line("")

    # ✅ Estimates
    draw_line("Past Estimates:", bold=True)
    if estimates:
        for e in estimates:
            draw_line(f"• ${e['amount']} on {fmt(e['created_at'])}")
    else:
        draw_line("No estimates found.")
    draw_line("")

    # ✅ Sheet Images
    sheet_path = os.path.join("static", "sheets", str(job_id))
    if os.path.exists(sheet_path):
        for img_path in glob.glob(f"{sheet_path}/**/*.png", recursive=True):
            try:
                img = Image.open(img_path)
                img_width, img_height = img.size
                ratio = min(width / img_width, height / img_height) * 0.9
                resized_w = img_width * ratio
                resized_h = img_height * ratio

                if resized_h > height - 100:
                    resized_h = height - 100
                    resized_w = resized_h * (img_width / img_height)

                pdf.drawImage(img_path, x=30, y=height - resized_h - 40, width=resized_w, height=resized_h)
                pdf.drawString(inch, 40, f"Page {page_number}")
                page_number += 1
                pdf.showPage()
                y = height - inch
                draw_header("Sheet Images")
            except Exception as e:
                print(f"Error loading image: {img_path}, {e}")

    # ✅ Uploaded Files
    upload_path = os.path.join("static", "uploads", str(job_id))
    if os.path.exists(upload_path):
        for img_path in glob.glob(f"{upload_path}/*"):
            try:
                img = Image.open(img_path)
                img_width, img_height = img.size
                ratio = min(width / img_width, height / img_height) * 0.9
                resized_w = img_width * ratio
                resized_h = img_height * ratio

                if resized_h > height - 100:
                    resized_h = height - 100
                    resized_w = resized_h * (img_width / img_height)

                pdf.drawImage(img_path, x=30, y=height - resized_h - 40, width=resized_w, height=resized_h)
                pdf.drawString(inch, 40, f"Page {page_number}")
                page_number += 1
                pdf.showPage()
                y = height - inch
                draw_header("Uploaded Files")
            except Exception as e:
                print(f"Error loading uploaded image: {img_path}, {e}")

    pdf.drawString(inch, 40, f"Page {page_number}")
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"job_{job_id}.pdf", mimetype='application/pdf')


if __name__ == "__main__":
    app.run(debug=True)
