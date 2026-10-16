"""Workshop budget: a running balance of money in and out.

* Expenses reduce the balance, income increases it.
* Client payments recorded on a job create a linked income entry automatically
  (see add_payment / delete_payment in app.py); deleting the payment removes it.
* A purchase can also add to a stock item, so buying materials updates both the
  inventory and the budget in one step.
* Every entry can carry a receipt (photo or PDF). Receipts are stored in the
  database, not on disk: Render's disk is wiped on every deploy, and files
  under static/ are publicly reachable by URL, which is wrong for financial
  documents. They are served only to the owning user.
"""
import csv
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO, StringIO

import psycopg2
from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

from neon_client import execute_query, execute_single

budget_bp = Blueprint("budget", __name__)

EXPENSE_CATEGORIES = ["Materials", "Hardware", "Tools & Equipment", "Supplies", "Rent & Utilities",
                      "Fuel & Vehicle", "Labor", "Marketing", "Other"]
INCOME_CATEGORIES = ["Client deposit", "Client payment", "Store sale", "Other income", "Opening balance"]
MAX_AMOUNT = Decimal("10000000")
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ROWS = 300


def init_budget(app):
    app.register_blueprint(budget_bp)
    try:
        execute_query("""
            CREATE TABLE IF NOT EXISTS budget_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tx_type VARCHAR(10) NOT NULL CHECK (tx_type IN ('income','expense')),
                amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
                category VARCHAR(100),
                description VARCHAR(500),
                tx_date DATE NOT NULL DEFAULT CURRENT_DATE,
                job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
                stock_id UUID REFERENCES stocks(id) ON DELETE SET NULL,
                stock_qty INTEGER,
                payment_id UUID REFERENCES payments(id) ON DELETE CASCADE,
                has_receipt BOOLEAN NOT NULL DEFAULT FALSE,
                receipt_data BYTEA,
                receipt_mime VARCHAR(50),
                receipt_name VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """, fetch=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_budget_user_date ON budget_transactions(user_id, tx_date DESC)", fetch=False)
        execute_query("CREATE INDEX IF NOT EXISTS idx_budget_payment ON budget_transactions(payment_id)", fetch=False)
    except Exception as e:
        print("Warning: could not ensure budget tables:", e)


# --------------------------------------------------------------------------
# helpers (also used by app.py and the AI assistant)
# --------------------------------------------------------------------------

def parse_amount(value):
    try:
        d = Decimal(str(value).replace(",", "").replace("$", "").strip()).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")
    if d <= 0 or d > MAX_AMOUNT:
        raise ValueError("Amount must be more than 0.")
    return d


def parse_day(value):
    if not value:
        return date.today()
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date.")


def read_receipt(file_storage):
    """Validate an uploaded receipt. Returns (bytes, mime, name) or None if no file.
    Photos are re-encoded as JPEG (max 2000px) so they stay small; PDFs pass through."""
    if not file_storage or not file_storage.filename:
        return None
    raw = file_storage.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Receipt is too large (15 MB max).")
    name = secure_filename(file_storage.filename)[:255] or "receipt"
    if raw[:5] == b"%PDF-":
        if len(raw) > MAX_PDF_BYTES:
            raise ValueError("PDF receipts must be 5 MB or less.")
        return raw, "application/pdf", name
    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, "white")
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        img.thumbnail((2000, 2000))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
    except Exception:
        raise ValueError("Receipt must be a JPG/PNG photo or a PDF.")
    return buf.getvalue(), "image/jpeg", name.rsplit(".", 1)[0] + ".jpg"


def record_transaction(user_id, tx_type, amount, category=None, description=None, tx_date=None,
                       job_id=None, stock_id=None, stock_qty=None, payment_id=None, receipt=None):
    """Insert a budget entry. If stock_id and stock_qty are given on an expense, the stock
    quantity is increased in the same call. Returns the new entry id."""
    if tx_type not in ("income", "expense"):
        raise ValueError("Type must be income or expense.")
    amount = parse_amount(amount)
    tx_date = tx_date or date.today()
    if job_id:
        if not execute_single("SELECT 1 AS ok FROM jobs WHERE id = %s AND user_id = %s", (str(job_id), user_id)):
            raise ValueError("Job not found.")
    qty = None
    if stock_id:
        stock = execute_single("SELECT id, quantity FROM stocks WHERE id = %s AND user_id = %s", (str(stock_id), user_id))
        if not stock:
            raise ValueError("Inventory item not found.")
        if tx_type != "expense":
            raise ValueError("Only expenses can add to inventory.")
        qty = int(stock_qty or 0)
        if qty < 1 or qty > 100000:
            raise ValueError("Quantity bought must be 1 or more.")
    data, mime, rname = receipt if receipt else (None, None, None)
    row = execute_single(
        "INSERT INTO budget_transactions (user_id, tx_type, amount, category, description, tx_date, job_id, "
        "stock_id, stock_qty, payment_id, has_receipt, receipt_data, receipt_mime, receipt_name) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (user_id, tx_type, amount, (category or None), ((description or "").strip()[:500] or None), tx_date,
         str(job_id) if job_id else None, str(stock_id) if stock_id else None, qty,
         str(payment_id) if payment_id else None, data is not None,
         psycopg2.Binary(data) if data is not None else None, mime, rname))
    if stock_id:
        execute_query("UPDATE stocks SET quantity = quantity + %s WHERE id = %s AND user_id = %s",
                      (qty, str(stock_id), user_id), fetch=False)
    return str(row["id"])


def budget_totals(user_id, start=None, end=None):
    sql = ("SELECT COALESCE(SUM(amount) FILTER (WHERE tx_type='income'),0) AS income, "
           "COALESCE(SUM(amount) FILTER (WHERE tx_type='expense'),0) AS expense "
           "FROM budget_transactions WHERE user_id = %s")
    params = [user_id]
    if start:
        sql += " AND tx_date >= %s"; params.append(start)
    if end:
        sql += " AND tx_date < %s"; params.append(end)
    r = execute_single(sql, tuple(params))
    return {"income": r["income"], "expense": r["expense"], "net": r["income"] - r["expense"]}


def _month_bounds(month):
    """'2026-10' -> (date(2026,10,1), date(2026,11,1)); None/'all' -> (None, None)."""
    if not month or month == "all":
        return None, None
    d = datetime.strptime(month, "%Y-%m").date()
    nxt = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return d, nxt


def _uid():
    return session.get("user_id")


def _own(tx_id, user_id, with_receipt=False):
    try:
        uuid.UUID(str(tx_id))
    except ValueError:
        return None
    cols = "*" if with_receipt else ("id, user_id, tx_type, amount, category, description, tx_date, job_id, "
                                      "stock_id, stock_qty, payment_id, has_receipt")
    return execute_single(f"SELECT {cols} FROM budget_transactions WHERE id = %s AND user_id = %s", (str(tx_id), user_id))


def _back(default="budget.budget_home"):
    nxt = request.form.get("next") or ""
    if nxt in ("stocks", "job"):
        if nxt == "stocks":
            return redirect(url_for("view_stocks"))
    return redirect(url_for(default))


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@budget_bp.route("/budget")
def budget_home():
    uid = _uid()
    if not uid:
        flash("Please log in to view your budget.", "warning")
        return redirect(url_for("login"))

    month = request.args.get("month") or date.today().strftime("%Y-%m")
    tx_type = request.args.get("type") or ""
    category = request.args.get("category") or ""
    q = (request.args.get("q") or "").strip()
    try:
        start, end = _month_bounds(month)
    except ValueError:
        month, start, end = date.today().strftime("%Y-%m"), *_month_bounds(date.today().strftime("%Y-%m"))

    sql = ("SELECT bt.id, bt.tx_type, bt.amount, bt.category, bt.description, bt.tx_date, bt.has_receipt, "
           "bt.job_id, bt.stock_id, bt.stock_qty, bt.payment_id, j.client_name, s.name AS stock_name "
           "FROM budget_transactions bt LEFT JOIN jobs j ON j.id = bt.job_id LEFT JOIN stocks s ON s.id = bt.stock_id "
           "WHERE bt.user_id = %s")
    params = [uid]
    if start:
        sql += " AND bt.tx_date >= %s AND bt.tx_date < %s"; params += [start, end]
    if tx_type in ("income", "expense"):
        sql += " AND bt.tx_type = %s"; params.append(tx_type)
    if category:
        sql += " AND bt.category = %s"; params.append(category)
    if q:
        sql += " AND (bt.description ILIKE %s OR j.client_name ILIKE %s OR s.name ILIKE %s)"; params += [f"%{q}%"] * 3
    sql += " ORDER BY bt.tx_date DESC, bt.created_at DESC LIMIT %s"
    params.append(MAX_ROWS + 1)
    rows = execute_query(sql, tuple(params), fetch=True)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    by_cat = execute_query(
        "SELECT tx_type, COALESCE(category,'Uncategorized') AS category, SUM(amount) AS total "
        "FROM budget_transactions WHERE user_id = %s" + (" AND tx_date >= %s AND tx_date < %s" if start else "") +
        " GROUP BY tx_type, 2 ORDER BY total DESC",
        (uid, start, end) if start else (uid,), fetch=True)

    return render_template(
        "budget.html", rows=rows, truncated=truncated, month=month, tx_type=tx_type, category=category, q=q,
        balance=budget_totals(uid)["net"], period=budget_totals(uid, start, end), by_cat=by_cat,
        expense_categories=EXPENSE_CATEGORIES, income_categories=INCOME_CATEGORIES,
        stocks=execute_query("SELECT id, name, unit, quantity FROM stocks WHERE user_id = %s ORDER BY name", (uid,), fetch=True),
        jobs=execute_query("SELECT id, client_name FROM jobs WHERE user_id = %s AND is_scratch IS NOT TRUE "
                           "ORDER BY created_at DESC LIMIT 200", (uid,), fetch=True),
        today=date.today().isoformat())


@budget_bp.route("/budget/add", methods=["POST"])
def budget_add():
    uid = _uid()
    if not uid:
        return redirect(url_for("login"))
    f = request.form
    try:
        tx_type = f.get("tx_type", "expense")
        stock_id = f.get("stock_id") or None
        stock_qty = f.get("stock_qty") or None
        new_stock = (f.get("new_stock_name") or "").strip()
        receipt = read_receipt(request.files.get("receipt"))
        amount = parse_amount(f.get("amount"))
        tx_date = parse_day(f.get("tx_date"))
        if tx_type == "expense" and new_stock and not stock_id:
            # Buying something new: create the inventory item, then record the purchase against it.
            if not stock_qty:
                raise ValueError("Enter how many you bought to add a new inventory item.")
            row = execute_single(
                "INSERT INTO stocks (user_id, name, category, quantity, unit) VALUES (%s,%s,%s,0,%s) RETURNING id",
                (uid, new_stock[:255], (f.get("category") or "Uncategorized")[:100], (f.get("stock_unit") or "").strip()[:50] or None))
            stock_id = str(row["id"])
        record_transaction(
            uid, tx_type, amount, category=f.get("category"), description=f.get("description"), tx_date=tx_date,
            job_id=f.get("job_id") or None, stock_id=stock_id if tx_type == "expense" else None,
            stock_qty=stock_qty, receipt=receipt)
        msg = f"{'Expense' if tx_type == 'expense' else 'Income'} of ${amount:,.2f} recorded."
        if stock_id and tx_type == "expense":
            msg += f" Inventory updated (+{int(stock_qty)})."
        flash(msg, "success")
    except ValueError as e:
        flash(str(e), "warning")
    except Exception as e:
        print("budget_add failed:", e)
        flash("Could not save that entry.", "danger")
    return _back()


@budget_bp.route("/budget/<tx_id>/edit", methods=["POST"])
def budget_edit(tx_id):
    uid = _uid()
    if not uid:
        return redirect(url_for("login"))
    tx = _own(tx_id, uid)
    if not tx:
        flash("Entry not found.", "warning")
        return redirect(url_for("budget.budget_home"))
    f = request.form
    try:
        desc = (f.get("description") or "").strip()[:500] or None
        sets, params = ["description = %s", "updated_at = NOW()"], [desc]
        if not tx["payment_id"]:  # amounts on client payments are edited from the job page
            sets += ["amount = %s", "category = %s", "tx_date = %s"]
            params += [parse_amount(f.get("amount")), f.get("category") or None, parse_day(f.get("tx_date"))]
        receipt = read_receipt(request.files.get("receipt"))
        if receipt:
            sets += ["has_receipt = TRUE", "receipt_data = %s", "receipt_mime = %s", "receipt_name = %s"]
            params += [psycopg2.Binary(receipt[0]), receipt[1], receipt[2]]
        elif f.get("remove_receipt"):
            sets += ["has_receipt = FALSE", "receipt_data = NULL", "receipt_mime = NULL", "receipt_name = NULL"]
        execute_query(f"UPDATE budget_transactions SET {', '.join(sets)} WHERE id = %s AND user_id = %s",
                      tuple(params) + (str(tx["id"]), uid), fetch=False)
        flash("Entry updated.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    return redirect(request.referrer or url_for("budget.budget_home"))


@budget_bp.route("/budget/<tx_id>/delete", methods=["POST"])
def budget_delete(tx_id):
    uid = _uid()
    if not uid:
        return redirect(url_for("login"))
    tx = _own(tx_id, uid)
    if not tx:
        flash("Entry not found.", "warning")
    elif tx["payment_id"]:
        flash("This entry comes from a client payment. Remove the payment on the job page instead.", "warning")
    else:
        execute_query("DELETE FROM budget_transactions WHERE id = %s AND user_id = %s", (str(tx["id"]), uid), fetch=False)
        note = " Inventory quantity was not changed." if tx["stock_id"] else ""
        flash("Entry deleted." + note, "success")
    return redirect(request.referrer or url_for("budget.budget_home"))


@budget_bp.route("/budget/<tx_id>/receipt")
def budget_receipt(tx_id):
    uid = _uid()
    if not uid:
        return redirect(url_for("login"))
    tx = _own(tx_id, uid, with_receipt=True)
    if not tx or not tx["has_receipt"] or tx["receipt_data"] is None:
        abort(404)
    resp = Response(bytes(tx["receipt_data"]), mimetype=tx["receipt_mime"] or "application/octet-stream")
    resp.headers["Content-Disposition"] = f'inline; filename="{tx["receipt_name"] or "receipt"}"'
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@budget_bp.route("/budget/export.csv")
def budget_export():
    uid = _uid()
    if not uid:
        return redirect(url_for("login"))
    rows = execute_query(
        "SELECT bt.tx_date, bt.tx_type, bt.amount, bt.category, bt.description, j.client_name, s.name AS stock_name, "
        "bt.stock_qty, bt.has_receipt FROM budget_transactions bt LEFT JOIN jobs j ON j.id = bt.job_id "
        "LEFT JOIN stocks s ON s.id = bt.stock_id WHERE bt.user_id = %s ORDER BY bt.tx_date, bt.created_at", (uid,), fetch=True)
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Type", "Amount", "Category", "Description", "Job", "Inventory item", "Qty added", "Has receipt"])
    for r in rows:
        # Prefix cells that start with =,+,-,@ so spreadsheets don't run them as formulas.
        safe = lambda v: ("'" + v) if isinstance(v, str) and v[:1] in "=+-@" else v
        w.writerow([r["tx_date"], r["tx_type"], r["amount"], safe(r["category"] or ""), safe(r["description"] or ""),
                    safe(r["client_name"] or ""), safe(r["stock_name"] or ""), r["stock_qty"] or "",
                    "yes" if r["has_receipt"] else "no"])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=budget.csv"})
