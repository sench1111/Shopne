"""
Sench Sanch Sales Tracker
--------------------
A tiny Flask backend for a shop owner to record sales through the browser
and see running totals, and profit or loss, update live without touching a terminal.

Run locally with:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000 in a browser.
"""

from functools import wraps
from flask import Flask, request, jsonify, render_template, Response, session, redirect, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
import os
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Support both layouts:
#   1) templates/*.html (standard Flask layout)
#   2) *.html beside app.py (the layout used by some Render/GitHub versions)
# This prevents TemplateNotFound when the repository is deployed with HTML
# files in the project root.
app = Flask(__name__)
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(BASE_DIR),
    FileSystemLoader(TEMPLATES_DIR),
])
app.secret_key = os.environ.get("SECRET_KEY", "sench-sanch-dev-secret")

# ---------------------------------------------------------------------------
# User accounts.
# Three roles, in a clear hierarchy:
#   - "employee": front-line access — record sales, download reports, reset
#     the day, change their own password. This is the role that actually
#     does the day-to-day selling.
#   - "manager": everything an employee can do, PLUS a "Team" dashboard that
#     oversees employee accounts and shows what employees have been doing.
#     A manager does NOT see the owner's activity, and cannot reach Backstage.
#   - "owner": full control — everything, for everyone, including Backstage
#     (manage every account at any level, edit shop settings, see every
#     login and every action across the whole shop).
# Passwords are hashed, not stored in plain text. This is still an in-memory
# store for the assignment — swap for a real database before using it for real.
# ---------------------------------------------------------------------------
ROLE_RANK = {"employee": 1, "manager": 2, "owner": 3}

users = {
    "employee": {
        "password_hash": generate_password_hash("staff123"),
        "role": "employee",
        "display_name": "Store Assistant",
    },
    "manager": {
        "password_hash": generate_password_hash("sales123"),
        "role": "manager",
        "display_name": "Shop Manager",
    },
    "sench": {
        "password_hash": generate_password_hash("backstage123"),
        "role": "owner",
        "display_name": "Sench Sanch",
    },
}

# Every login attempt (successful or not) gets logged here so the owner can
# see who has been signing in from the backstage panel.
login_log = []

# Every meaningful action a signed-in user takes (recording a sale, resetting
# the day, downloading a report, changing settings, managing accounts) gets
# logged here too, so the owner can see not just WHEN someone logged in but
# WHAT they actually did while they were signed in.
activity_log = []

# Shop-wide settings the owner can edit from backstage.
settings = {
    "shop_name": "Sench Sanch Sales Tracker",
    "currency": "GHS",
}


def current_user():
    username = session.get("username")
    if username and username in users:
        return username, users[username]
    return None, None


def log_activity(action):
    """Record what a signed-in user just did, for the owner's Backstage view
    and the manager's Team dashboard."""
    username, user = current_user()
    activity_log.append({
        "username": username or "(unknown)",
        "display_name": user["display_name"] if user else "(unknown)",
        "role": user["role"] if user else None,
        "action": action,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def login_required(view):
    """Redirect to the login page (or return 401 for API calls) if not signed in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not logged in"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def owner_required(view):
    """Only the owner role can reach backstage — everyone else gets bounced home."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        username, user = current_user()
        if not username:
            return redirect(url_for("login"))
        if user["role"] != "owner":
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def manager_required(view):
    """Manager or owner can reach the Team dashboard — employees get bounced home."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        username, user = current_user()
        if not username:
            return redirect(url_for("login"))
        if ROLE_RANK.get(user["role"], 0) < ROLE_RANK["manager"]:
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# In-memory "database" for the day's transactions.
# A list of dicts is enough here: we only need variables, lists, dicts and
# control flow (loops / conditionals) to build everything the shop owner needs.
#
# LIMITATION: this list lives in RAM only. Every transaction is lost the
# moment the Flask process restarts (a crash, a redeploy, the free tier on
# a host like Render spinning down when idle, etc). That's fine for this
# assignment, which is scoped to variables/lists/dicts/control flow rather
# than a database — but it is NOT suitable for a real shop's books. The
# straightforward upgrade path is to swap this list for a small SQLite
# database (or even just load/save transactions to a JSON file on disk),
# so data survives a restart.
# ---------------------------------------------------------------------------
transactions = []


def compute_summary():
    """Recalculate the running totals from the transactions list."""
    total_sales = 0.0
    total_units = 0
    total_profit = 0.0
    item_units = {}  # item name -> units sold, used to find the best seller

    for t in transactions:
        total_sales += t["unit_price"] * t["quantity"]
        total_units += t["quantity"]
        total_profit += t["profit"]
        item_units[t["item"]] = item_units.get(t["item"], 0) + t["quantity"]

    best_selling_item = None
    if item_units:
        best_selling_item = max(item_units, key=item_units.get)

    total_profit = round(total_profit, 2)
    if total_profit > 0:
        profit_status = "profit"
    elif total_profit < 0:
        profit_status = "loss"
    else:
        profit_status = "even"

    return {
        "total_sales": round(total_sales, 2),
        "num_transactions": len(transactions),
        "total_units": total_units,
        "best_selling_item": best_selling_item,
        "total_profit": total_profit,
        "profit_status": profit_status,
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = users.get(username)
        success = bool(user and check_password_hash(user["password_hash"], password))

        login_log.append({
            "username": username or "(blank)",
            "role": user["role"] if (success and user) else None,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "ip": request.remote_addr,
        })

        if success:
            session["username"] = username
            return redirect(url_for("index"))
        error = "Incorrect username or password."

    return render_template("login.html", error=error, settings=settings)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    username, user = current_user()
    error = None
    success = None

    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not check_password_hash(user["password_hash"], current_pw):
            error = "Your current password is incorrect."
        elif len(new_pw) < 6:
            error = "New password must be at least 6 characters."
        elif new_pw != confirm_pw:
            error = "New password and confirmation don't match."
        else:
            user["password_hash"] = generate_password_hash(new_pw)
            log_activity("Changed their own password")
            success = "Password updated. Use it next time you sign in."

    return render_template(
        "change_password.html",
        error=error,
        success=success,
        user=user,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Backstage — owner-only control panel
# ---------------------------------------------------------------------------
@app.route("/backstage", methods=["GET"])
@owner_required
def backstage():
    recent_logins = list(reversed(login_log))[:50]
    recent_activity = list(reversed(activity_log))[:50]
    return render_template(
        "backstage.html",
        users=users,
        recent_logins=recent_logins,
        recent_activity=recent_activity,
        settings=settings,
        current_username=session.get("username"),
        error=request.args.get("error"),
        success=request.args.get("success"),
    )


@app.route("/backstage/add-user", methods=["POST"])
@owner_required
def backstage_add_user():
    username = request.form.get("new_username", "").strip()
    password = request.form.get("new_password", "")
    role = request.form.get("new_role", "manager")
    display_name = request.form.get("new_display_name", "").strip() or username

    if not username or not password:
        return redirect(url_for("backstage", error="Username and password are required."))
    if username in users:
        return redirect(url_for("backstage", error=f"'{username}' already exists."))
    if len(password) < 6:
        return redirect(url_for("backstage", error="Password must be at least 6 characters."))
    if role not in ("employee", "manager", "owner"):
        role = "employee"

    users[username] = {
        "password_hash": generate_password_hash(password),
        "role": role,
        "display_name": display_name,
    }
    log_activity(f"Added staff account '{username}' as {role}")
    return redirect(url_for("backstage", success=f"Added '{username}' as {role}."))


@app.route("/backstage/update-role", methods=["POST"])
@owner_required
def backstage_update_role():
    username = request.form.get("username", "")
    new_role = request.form.get("role", "")
    current = session.get("username")

    if username not in users:
        return redirect(url_for("backstage", error="That user doesn't exist."))
    if new_role not in ("employee", "manager", "owner"):
        return redirect(url_for("backstage", error="Not a valid role."))
    if username == current and new_role != "owner":
        return redirect(url_for("backstage", error="You can't demote the account you're signed in with."))

    old_role = users[username]["role"]
    if old_role == "owner" and new_role != "owner":
        owners_left = [u for u, info in users.items() if info["role"] == "owner" and u != username]
        if not owners_left:
            return redirect(url_for("backstage", error="Can't demote the last owner account."))

    users[username]["role"] = new_role
    log_activity(f"Changed '{username}' role from {old_role} to {new_role}")
    return redirect(url_for("backstage", success=f"'{username}' is now {new_role}."))


@app.route("/backstage/remove-user", methods=["POST"])
@owner_required
def backstage_remove_user():
    username = request.form.get("username", "")
    current = session.get("username")

    if username == current:
        return redirect(url_for("backstage", error="You can't remove the account you're signed in with."))
    if username not in users:
        return redirect(url_for("backstage", error="That user doesn't exist."))

    owners_left = [u for u, info in users.items() if info["role"] == "owner" and u != username]
    if users[username]["role"] == "owner" and not owners_left:
        return redirect(url_for("backstage", error="Can't remove the last owner account."))

    del users[username]
    log_activity(f"Removed staff account '{username}'")
    return redirect(url_for("backstage", success=f"Removed '{username}'."))


@app.route("/backstage/settings", methods=["POST"])
@owner_required
def backstage_settings():
    shop_name = request.form.get("shop_name", "").strip()
    currency = request.form.get("currency", "").strip()

    if shop_name:
        settings["shop_name"] = shop_name
    if currency:
        settings["currency"] = currency

    log_activity("Updated shop settings")
    return redirect(url_for("backstage", success="Settings updated."))


# ---------------------------------------------------------------------------
# Team dashboard — manager (and owner) can see and manage employees here.
# A manager can see employee activity and logins, but never the owner's —
# those rows are filtered out below. A manager can also only add or remove
# EMPLOYEE accounts; they can't touch manager or owner accounts, even by
# tampering with the form (the role is forced server-side).
# ---------------------------------------------------------------------------
@app.route("/team", methods=["GET"])
@manager_required
def team_dashboard():
    employees = {u: info for u, info in users.items() if info["role"] == "employee"}
    team_logins = [e for e in reversed(login_log) if e.get("role") != "owner"][:50]
    team_activity = [e for e in reversed(activity_log) if e.get("role") != "owner"][:50]
    return render_template(
        "team.html",
        employees=employees,
        recent_logins=team_logins,
        recent_activity=team_activity,
        settings=settings,
        current_username=session.get("username"),
        error=request.args.get("error"),
        success=request.args.get("success"),
    )


@app.route("/team/add-employee", methods=["POST"])
@manager_required
def team_add_employee():
    username = request.form.get("new_username", "").strip()
    password = request.form.get("new_password", "")
    display_name = request.form.get("new_display_name", "").strip() or username

    if not username or not password:
        return redirect(url_for("team_dashboard", error="Username and password are required."))
    if username in users:
        return redirect(url_for("team_dashboard", error=f"'{username}' already exists."))
    if len(password) < 6:
        return redirect(url_for("team_dashboard", error="Password must be at least 6 characters."))

    # Forced to "employee" regardless of what's submitted — a manager can
    # never create a manager or owner account from here.
    users[username] = {
        "password_hash": generate_password_hash(password),
        "role": "employee",
        "display_name": display_name,
    }
    log_activity(f"Added employee account '{username}'")
    return redirect(url_for("team_dashboard", success=f"Added '{username}' to the team."))


@app.route("/team/remove-employee", methods=["POST"])
@manager_required
def team_remove_employee():
    username = request.form.get("username", "")

    if username not in users:
        return redirect(url_for("team_dashboard", error="That user doesn't exist."))
    if users[username]["role"] != "employee":
        return redirect(url_for("team_dashboard", error="You can only remove employee accounts from here."))

    del users[username]
    log_activity(f"Removed employee account '{username}'")
    return redirect(url_for("team_dashboard", success=f"Removed '{username}'."))


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    username, user = current_user()
    return render_template("index.html", user=user, settings=settings)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.route("/api/sale", methods=["POST"])
@login_required
def add_sale():
    data = request.get_json(silent=True) or {}

    item = str(data.get("item", "")).strip()
    try:
        unit_price = float(data.get("unit_price"))
        quantity = int(data.get("quantity"))
        # Cost price is optional — if the shop owner doesn't enter one, we
        # can't work out profit for that line, so it's treated as 0.
        cost_price = float(data.get("cost_price") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Prices must be numbers and quantity must be a whole number"}), 400

    if not item:
        return jsonify({"error": "Item name is required"}), 400
    if unit_price <= 0:
        return jsonify({"error": "Unit price must be greater than 0"}), 400
    if quantity <= 0:
        return jsonify({"error": "Quantity must be greater than 0"}), 400
    if cost_price < 0:
        return jsonify({"error": "Cost price can't be negative"}), 400

    transactions.append({
        "item": item,
        "unit_price": unit_price,
        "cost_price": cost_price,
        "quantity": quantity,
        "line_total": round(unit_price * quantity, 2),
        "profit": round((unit_price - cost_price) * quantity, 2),
        "time": datetime.now().strftime("%H:%M:%S"),
    })
    log_activity(f"Recorded sale: {item} x{quantity}")

    return jsonify({
        "summary": compute_summary(),
        "transactions": transactions,
    }), 201


@app.route("/api/summary", methods=["GET"])
@login_required
def get_summary():
    return jsonify({
        "summary": compute_summary(),
        "transactions": transactions,
    })


@app.route("/api/reset", methods=["POST"])
@login_required
def reset():
    count = len(transactions)
    transactions.clear()
    log_activity(f"Reset the day's transactions ({count} cleared)")
    return jsonify({
        "summary": compute_summary(),
        "transactions": transactions,
    })


@app.route("/api/report", methods=["GET"])
@login_required
def report():
    log_activity("Downloaded the sales report")
    summary = compute_summary()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_html = ""
    for t in transactions:
        profit = t.get("profit", 0.0)
        profit_color = "#34d399" if profit > 0 else ("#f87171" if profit < 0 else "#8a8478")
        rows_html += f"""
        <tr>
            <td>{t['time']}</td>
            <td>{t['item']}</td>
            <td>{t['unit_price']:.2f}</td>
            <td>{t['quantity']}</td>
            <td>{t['line_total']:.2f}</td>
            <td style="color:{profit_color}; font-weight:600;">{profit:+.2f}</td>
        </tr>"""

    if not transactions:
        rows_html = "<tr><td colspan='6' style='text-align:center;'>No transactions recorded</td></tr>"

    profit_color = "#34d399" if summary["total_profit"] > 0 else ("#f87171" if summary["total_profit"] < 0 else "#e8a855")
    profit_word = {"profit": "In profit", "loss": "Operating at a loss", "even": "Break even"}[summary["profit_status"]]
    shop_name = settings["shop_name"]
    currency = settings["currency"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{shop_name} — Sales Report</title>
<style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 2.5rem; color: #e8e4da; background: #05070a; }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; color: #f0a63e; font-weight: 700; margin: 0 0 0.4rem; }}
    h1 {{ font-family: Georgia, 'Times New Roman', serif; margin: 0 0 0.25rem; font-size: 2rem; color: #f5efe3; }}
    .meta {{ color: #8a8478; margin-bottom: 1.75rem; font-size: 0.9rem; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }}
    .summary .box {{ background: #12181a; border: 1px solid rgba(245,239,227,0.08); color: #f5efe3; border-radius: 10px; padding: 1rem 1.25rem; min-width: 150px; }}
    .summary .box .label {{ text-transform: uppercase; letter-spacing: 0.1em; font-size: 0.68rem; color: #a89f8c; margin-bottom: 0.3rem; }}
    .summary .box .value {{ font-size: 1.3rem; font-weight: 700; color: #f0a63e; }}
    table {{ border-collapse: collapse; width: 100%; background: #0d1214; border-radius: 10px; overflow: hidden; }}
    th, td {{ padding: 10px 14px; text-align: left; font-size: 0.9rem; border-bottom: 1px solid rgba(245,239,227,0.06); }}
    th {{ background: #12181a; text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.72rem; color: #a89f8c; }}
</style>
</head>
<body>
    <p class="eyebrow">Daily Snapshot</p>
    <h1>{shop_name} — Sales Report</h1>
    <p class="meta">Generated {generated_at}</p>

    <div class="summary">
        <div class="box"><div class="label">Total sales</div><div class="value">{currency} {summary['total_sales']:.2f}</div></div>
        <div class="box"><div class="label">Transactions</div><div class="value">{summary['num_transactions']}</div></div>
        <div class="box"><div class="label">Units sold</div><div class="value">{summary['total_units']}</div></div>
        <div class="box"><div class="label">Best seller</div><div class="value">{summary['best_selling_item'] or 'N/A'}</div></div>
        <div class="box"><div class="label">{profit_word}</div><div class="value" style="color:{profit_color};">{currency} {summary['total_profit']:+.2f}</div></div>
    </div>

    <table>
        <thead>
            <tr><th>Time</th><th>Item</th><th>Unit Price</th><th>Qty</th><th>Line Total</th><th>Profit</th></tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""

    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": "attachment; filename=sales_report.html"},
    )


if __name__ == "__main__":
    app.run(debug=True)
