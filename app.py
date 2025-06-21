# app.py

from flask import Flask, render_template, request, redirect, url_for
from cabinet import generate_parts
from planner import optimize_cuts
from visualizer import draw_sheets_to_files
import os
import uuid

app = Flask(__name__)

# Make sure static/sheets exists
os.makedirs("static/sheets", exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Get parts lists
        widths = request.form.getlist("widths")
        heights = request.form.getlist("heights")
        quantities = request.form.getlist("quantities")

        # Convert to floats & ints
        parts = []
        for w, h, q in zip(widths, heights, quantities):
            w = float(w)
            h = float(h)
            q = int(q)
            parts.extend([(w, h)] * q)  # add q copies

        # Get panel size
        panel_width = float(request.form.get("panel_width", 96))
        panel_height = float(request.form.get("panel_height", 48))

        # Optimize cuts
        sheets = optimize_cuts(panel_width, panel_height, parts)

        # Save images as before
        job_id = str(uuid.uuid4())
        output_dir = f"static/sheets/{job_id}"
        os.makedirs(output_dir)

        draw_sheets_to_files(sheets, output_dir)
        sheet_images = [f"{job_id}/sheet_{i+1}.png" for i in range(len(sheets))]

        return render_template(
            "result.html",
            parts=parts,
            sheet_images=sheet_images
        )

    # ✅ THIS IS WHAT YOU'RE MISSING:
    return render_template("index.html")




if __name__ == "__main__":
    app.run(debug=True)
