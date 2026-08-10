import os
import sqlite3
import secrets
from functools import wraps
from datetime import datetime, timedelta

from flask import (
    Flask, g, render_template, request, redirect, url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

import db as dbm

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "buyersforce-dev-secret-key-demo-only")
dbm.init_app(app)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = dbm.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please sign in to continue.", "error")
                return redirect(url_for("login"))
            if g.user["role"] != role:
                flash(f"That area is for {role}s.", "error")
                return redirect(home_for_role(g.user["role"]))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        if not g.user["is_admin"]:
            flash("That area is for administrators.", "error")
            return redirect(home_for_role(g.user["role"]))
        return view(*args, **kwargs)
    return wrapped


def home_for_role(role):
    if role == "admin":
        return url_for("admin_dashboard")
    return url_for("buyer_dashboard" if role == "buyer" else "seller_dashboard")


def log_activity(user_id, verb, detail=""):
    dbm.execute(
        "INSERT INTO activity_log (user_id, verb, detail) VALUES (?, ?, ?)",
        (user_id, verb, detail),
    )


def fmt_time(value):
    if not value:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(value, pattern)
            return dt.strftime("%b %-d, %Y · %-I:%M %p")
        except ValueError:
            continue
    return value


app.jinja_env.filters["fmt_time"] = fmt_time


# ---------------------------------------------------------------------------
# Public / marketing
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    if g.user:
        return redirect(home_for_role(g.user["role"]))
    return render_template("landing.html")


@app.route("/signup")
def signup():
    # Public self-signup is disabled -- BuyersForce is invite-only. An admin
    # grants access from the admin panel, which emails... well, hands them a
    # link (see /accept-invite/<token>) tied to their email address.
    if g.user:
        return redirect(home_for_role(g.user["role"]))
    return render_template("signup_disabled.html")


@app.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(home_for_role(g.user["role"]))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = dbm.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(home_for_role(user["role"]))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/accept-invite/<token>", methods=("GET", "POST"))
def accept_invite(token):
    invite = dbm.query("SELECT * FROM invites WHERE token = ?", (token,), one=True)
    if invite is None:
        return render_template("invite_invalid.html", reason="not_found")
    if invite["used_at"] is not None:
        return render_template("invite_invalid.html", reason="used")
    if datetime.strptime(invite["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.utcnow():
        return render_template("invite_invalid.html", reason="expired")

    existing_user = dbm.query("SELECT * FROM users WHERE email = ?", (invite["email"],), one=True)

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        name = request.form.get("name", "").strip() or invite["name"] or invite["email"].split("@")[0]
        error = None
        if len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords don't match."

        if error is None:
            pw_hash = generate_password_hash(password)
            if existing_user:
                dbm.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (pw_hash, existing_user["id"]),
                )
                user_id = existing_user["id"]
            else:
                user_id = dbm.execute(
                    "INSERT INTO users (role, name, email, password_hash, company) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (invite["role"], name, invite["email"], pw_hash, invite["company"]),
                )
                if invite["role"] == "seller":
                    dbm.execute(
                        "INSERT INTO vendors (seller_user_id, company_name, category, tagline, "
                        "description, website, accent, initials) VALUES (?, ?, 'Uncategorized', "
                        "'', '', '', '#2a78d6', ?)",
                        (user_id, invite["company"],
                         "".join([w[0] for w in invite["company"].split()[:2]]).upper() or "VN"),
                    )
            dbm.execute("UPDATE invites SET used_at = datetime('now') WHERE id = ?", (invite["id"],))
            session.clear()
            session["user_id"] = user_id
            flash("Your account is ready.", "success")
            return redirect(home_for_role(invite["role"]))
        flash(error, "error")

    return render_template("accept_invite.html", invite=invite, is_reset=existing_user is not None)


@app.route("/app/account", methods=("GET", "POST"))
@login_required
def account():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")
        error = None
        if not check_password_hash(g.user["password_hash"], current):
            error = "Current password is incorrect."
        elif len(new_password) < 8:
            error = "New password must be at least 8 characters."
        elif new_password != confirm:
            error = "New passwords don't match."
        if error is None:
            dbm.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), g.user["id"]),
            )
            flash("Password updated.", "success")
            return redirect(url_for("account"))
        flash(error, "error")
    return render_template("account.html")


# ---------------------------------------------------------------------------
# Admin area -- invite-only access control
# ---------------------------------------------------------------------------

@app.route("/app/admin")
@admin_required
def admin_dashboard():
    users = dbm.query(
        "SELECT * FROM users WHERE is_admin = 0 ORDER BY company, role, name"
    )
    pending_invites = dbm.query(
        "SELECT i.*, u.name invited_by_name FROM invites i JOIN users u ON u.id = i.invited_by "
        "WHERE i.used_at IS NULL ORDER BY i.created_at DESC"
    )
    new_invite_link = None
    new_invite_id = request.args.get("new_invite", type=int)
    if new_invite_id:
        inv = dbm.query("SELECT * FROM invites WHERE id = ?", (new_invite_id,), one=True)
        if inv:
            new_invite_link = url_for("accept_invite", token=inv["token"], _external=True)
    return render_template(
        "admin/dashboard.html", users=users, pending_invites=pending_invites,
        new_invite_link=new_invite_link,
    )


def _create_invite(email, role, company, name, invited_by):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    invite_id = dbm.execute(
        "INSERT INTO invites (email, role, company, name, token, invited_by, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (email, role, company, name, token, invited_by, expires_at),
    )
    return invite_id, token


@app.route("/app/admin/invite", methods=("POST",))
@admin_required
def admin_invite():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "buyer")
    company = request.form.get("company", "").strip()
    name = request.form.get("name", "").strip()
    if not email or role not in ("buyer", "seller") or not company:
        flash("Email, account type, and company are required.", "error")
        return redirect(url_for("admin_dashboard"))

    dbm.execute("DELETE FROM invites WHERE email = ? AND used_at IS NULL", (email,))
    invite_id, token = _create_invite(email, role, company, name, g.user["id"])
    flash(f"Invite link created for {email}. Copy it below and send it to them.", "success")
    return redirect(url_for("admin_dashboard", new_invite=invite_id))


@app.route("/app/admin/users/<int:user_id>/grant-access", methods=("POST",))
@admin_required
def admin_grant_access(user_id):
    user = dbm.query("SELECT * FROM users WHERE id = ? AND is_admin = 0", (user_id,), one=True)
    if not user:
        abort(404)
    dbm.execute("DELETE FROM invites WHERE email = ? AND used_at IS NULL", (user["email"],))
    invite_id, token = _create_invite(
        user["email"], user["role"], user["company"], user["name"], g.user["id"]
    )
    flash(f"New access link generated for {user['name']}.", "success")
    return redirect(url_for("admin_dashboard", new_invite=invite_id))


@app.route("/app/admin/invites/<int:invite_id>/revoke", methods=("POST",))
@admin_required
def admin_revoke_invite(invite_id):
    dbm.execute("DELETE FROM invites WHERE id = ? AND used_at IS NULL", (invite_id,))
    flash("Invite revoked.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Shared helpers for buyer/seller areas
# ---------------------------------------------------------------------------

def teammates_of(user):
    return dbm.query(
        "SELECT * FROM users WHERE company = ? AND role = 'buyer' AND id != ? ORDER BY name",
        (user["company"], user["id"]),
    )


def vendor_tags(vendor_id):
    rows = dbm.query("SELECT tag FROM vendor_tags WHERE vendor_id = ?", (vendor_id,))
    return [r["tag"] for r in rows]


def vendor_listings(vendor_id):
    listings = dbm.query(
        "SELECT * FROM listings WHERE vendor_id = ? ORDER BY id", (vendor_id,)
    )
    out = []
    for listing in listings:
        feats = dbm.query(
            "SELECT feature_text FROM listing_features WHERE listing_id = ?",
            (listing["id"],),
        )
        out.append({**dict(listing), "features": [f["feature_text"] for f in feats]})
    return out


def shortlist_status(buyer_id, vendor_id):
    row = dbm.query(
        "SELECT status FROM shortlist WHERE buyer_user_id = ? AND vendor_id = ?",
        (buyer_id, vendor_id),
        one=True,
    )
    return row["status"] if row else None


def get_or_create_vendor_thread(buyer_id, vendor_id):
    thread = dbm.query(
        "SELECT * FROM threads WHERE type='vendor' AND buyer_user_id=? AND vendor_id=?",
        (buyer_id, vendor_id),
        one=True,
    )
    if thread:
        return thread
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    thread_id = dbm.execute(
        "INSERT INTO threads (type, buyer_user_id, vendor_id, subject, created_by) "
        "VALUES ('vendor', ?, ?, ?, ?)",
        (buyer_id, vendor_id, f"Conversation with {vendor['company_name']}", buyer_id),
    )
    return dbm.query("SELECT * FROM threads WHERE id=?", (thread_id,), one=True)


# ---------------------------------------------------------------------------
# Buyer area
# ---------------------------------------------------------------------------

@app.route("/app/buyer")
@role_required("buyer")
def buyer_dashboard():
    u = g.user
    shortlisted = dbm.query(
        "SELECT s.*, v.company_name, v.category, v.accent, v.initials FROM shortlist s "
        "JOIN vendors v ON v.id = s.vendor_id WHERE s.buyer_user_id = ? "
        "ORDER BY s.created_at DESC LIMIT 6",
        (u["id"],),
    )
    counts = {
        "shortlisted": dbm.query(
            "SELECT COUNT(*) c FROM shortlist WHERE buyer_user_id=? AND status IN "
            "('shortlisted','evaluating','selected')", (u["id"],), one=True
        )["c"],
        "evaluations": dbm.query(
            "SELECT COUNT(*) c FROM evaluations WHERE company=?", (u["company"],), one=True
        )["c"],
        "unread_threads": dbm.query(
            "SELECT COUNT(DISTINCT t.id) c FROM threads t JOIN messages m ON m.thread_id=t.id "
            "WHERE (t.buyer_user_id=? OR (t.type!='vendor' AND t.created_by=?))",
            (u["id"], u["id"]), one=True
        )["c"],
        "meetings": dbm.query(
            "SELECT COUNT(*) c FROM meetings WHERE buyer_user_id=? AND status!='declined'",
            (u["id"],), one=True
        )["c"],
    }
    recent_activity = dbm.query(
        "SELECT * FROM activity_log WHERE user_id IN "
        "(SELECT id FROM users WHERE company=? AND role='buyer') "
        "ORDER BY created_at DESC LIMIT 8",
        (u["company"],),
    )
    upcoming_meetings = dbm.query(
        "SELECT me.*, v.company_name FROM meetings me JOIN vendors v ON v.id = me.vendor_id "
        "WHERE me.buyer_user_id = ? AND me.status != 'declined' "
        "ORDER BY me.proposed_time ASC LIMIT 5",
        (u["id"],),
    )
    return render_template(
        "buyer/dashboard.html",
        counts=counts,
        shortlisted=shortlisted,
        recent_activity=recent_activity,
        upcoming_meetings=upcoming_meetings,
    )


@app.route("/app/buyer/discover")
@role_required("buyer")
def buyer_discover():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sql = "SELECT * FROM vendors WHERE 1=1"
    args = []
    if q:
        sql += " AND (company_name LIKE ? OR tagline LIKE ? OR description LIKE ?)"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if category:
        sql += " AND category = ?"
        args.append(category)
    sql += " ORDER BY company_name"
    vendors = dbm.query(sql, args)
    categories = [r["category"] for r in dbm.query(
        "SELECT DISTINCT category FROM vendors ORDER BY category"
    )]
    vendor_data = []
    for v in vendors:
        vendor_data.append({
            **dict(v),
            "tags": vendor_tags(v["id"]),
            "status": shortlist_status(g.user["id"], v["id"]),
        })
    return render_template(
        "buyer/discover.html", vendors=vendor_data, categories=categories, q=q, category=category
    )


@app.route("/app/buyer/vendor/<int:vendor_id>")
@role_required("buyer")
def buyer_vendor(vendor_id):
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    listings = vendor_listings(vendor_id)
    tags = vendor_tags(vendor_id)
    status = shortlist_status(g.user["id"], vendor_id)
    templates_ = dbm.query(
        "SELECT * FROM eval_templates WHERE company=? OR is_shared=1 ORDER BY created_at DESC",
        (g.user["company"],),
    )
    existing_eval = dbm.query(
        "SELECT * FROM evaluations WHERE vendor_id=? AND company=? ORDER BY created_at DESC LIMIT 1",
        (vendor_id, g.user["company"]), one=True
    )
    return render_template(
        "buyer/vendor.html", vendor=vendor, listings=listings, tags=tags, status=status,
        templates=templates_, existing_eval=existing_eval,
    )


@app.route("/app/buyer/vendor/<int:vendor_id>/shortlist", methods=("POST",))
@role_required("buyer")
def buyer_shortlist_toggle(vendor_id):
    new_status = request.form.get("status", "shortlisted")
    existing = dbm.query(
        "SELECT * FROM shortlist WHERE buyer_user_id=? AND vendor_id=?",
        (g.user["id"], vendor_id), one=True,
    )
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if existing:
        dbm.execute(
            "UPDATE shortlist SET status=? WHERE id=?", (new_status, existing["id"])
        )
    else:
        dbm.execute(
            "INSERT INTO shortlist (buyer_user_id, vendor_id, status) VALUES (?, ?, ?)",
            (g.user["id"], vendor_id, new_status),
        )
    log_activity(g.user["id"], f"marked {vendor['company_name']} as {new_status}")
    flash(f"{vendor['company_name']} marked as {new_status}.", "success")
    return redirect(request.referrer or url_for("buyer_vendor", vendor_id=vendor_id))


@app.route("/app/buyer/compare")
@role_required("buyer")
def buyer_compare():
    ids = [int(i) for i in request.args.get("ids", "").split(",") if i.strip().isdigit()]
    ids = ids[:3]
    vendors = []
    for vid in ids:
        v = dbm.query("SELECT * FROM vendors WHERE id=?", (vid,), one=True)
        if v:
            vendors.append({
                **dict(v),
                "tags": vendor_tags(vid),
                "listings": vendor_listings(vid),
            })
    all_vendors = dbm.query("SELECT id, company_name FROM vendors ORDER BY company_name")
    return render_template("buyer/compare.html", vendors=vendors, all_vendors=all_vendors, ids=ids)


@app.route("/app/buyer/vendor/<int:vendor_id>/message", methods=("POST",))
@role_required("buyer")
def buyer_message_vendor(vendor_id):
    thread = get_or_create_vendor_thread(g.user["id"], vendor_id)
    body = request.form.get("body", "").strip()
    if body:
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], body),
        )
        vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
        log_activity(g.user["id"], f"messaged {vendor['company_name']}")
    return redirect(url_for("buyer_thread", thread_id=thread["id"]))


@app.route("/app/buyer/vendor/<int:vendor_id>/meeting", methods=("POST",))
@role_required("buyer")
def buyer_request_meeting(vendor_id):
    proposed_time = request.form.get("proposed_time", "").strip()
    note = request.form.get("note", "").strip()
    if proposed_time:
        for pattern in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                proposed_time = datetime.strptime(proposed_time, pattern).strftime("%Y-%m-%d %H:%M:%S")
                break
            except ValueError:
                continue
        dbm.execute(
            "INSERT INTO meetings (buyer_user_id, vendor_id, proposed_time, note) "
            "VALUES (?, ?, ?, ?)",
            (g.user["id"], vendor_id, proposed_time, note),
        )
        vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
        log_activity(g.user["id"], f"requested a meeting with {vendor['company_name']}")
        flash("Meeting request sent — the vendor will confirm a time.", "success")
    return redirect(url_for("buyer_vendor", vendor_id=vendor_id))


@app.route("/app/buyer/messages")
@role_required("buyer")
def buyer_messages():
    u = g.user
    vendor_threads = dbm.query(
        "SELECT t.*, v.company_name, v.initials, v.accent, "
        "(SELECT body FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_body, "
        "(SELECT created_at FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_at "
        "FROM threads t JOIN vendors v ON v.id = t.vendor_id "
        "WHERE t.type='vendor' AND t.buyer_user_id=? ORDER BY last_at DESC",
        (u["id"],),
    )
    team_threads = dbm.query(
        "SELECT t.*, "
        "(SELECT body FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_body, "
        "(SELECT created_at FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_at "
        "FROM threads t WHERE t.type='teammate' AND "
        "(t.created_by=? OR t.buyer_user_id=? OR t.id IN "
        "(SELECT thread_id FROM messages WHERE sender_user_id=?)) "
        "AND t.subject LIKE ? ORDER BY last_at DESC",
        (u["id"], u["id"], u["id"], f"%{u['company']}%"),
    )
    return render_template(
        "buyer/messages.html", vendor_threads=vendor_threads, team_threads=team_threads
    )


@app.route("/app/buyer/messages/team/new", methods=("POST",))
@role_required("buyer")
def buyer_new_team_thread():
    subject = request.form.get("subject", "").strip() or "Team discussion"
    body = request.form.get("body", "").strip()
    thread_id = dbm.execute(
        "INSERT INTO threads (type, buyer_user_id, subject, created_by) VALUES "
        "('teammate', NULL, ?, ?)",
        (f"[{g.user['company']}] {subject}", g.user["id"]),
    )
    if body:
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread_id, g.user["id"], body),
        )
    return redirect(url_for("buyer_thread", thread_id=thread_id))


def _load_thread_for_user(thread_id, user):
    thread = dbm.query("SELECT * FROM threads WHERE id=?", (thread_id,), one=True)
    if not thread:
        abort(404)
    if thread["type"] == "vendor":
        if user["role"] == "buyer" and thread["buyer_user_id"] != user["id"]:
            abort(403)
        if user["role"] == "seller":
            vendor = dbm.query(
                "SELECT * FROM vendors WHERE id=? AND seller_user_id=?",
                (thread["vendor_id"], user["id"]), one=True
            )
            if not vendor:
                abort(403)
    elif thread["type"] == "teammate":
        if user["role"] != "buyer" or user["company"] not in thread["subject"]:
            abort(403)
    return thread


@app.route("/app/buyer/messages/<int:thread_id>", methods=("GET", "POST"))
@role_required("buyer")
def buyer_thread(thread_id):
    thread = _load_thread_for_user(thread_id, g.user)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            dbm.execute(
                "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
                (thread_id, g.user["id"], body),
            )
        return redirect(url_for("buyer_thread", thread_id=thread_id))
    messages = dbm.query(
        "SELECT m.*, u.name sender_name, u.role sender_role FROM messages m "
        "JOIN users u ON u.id = m.sender_user_id WHERE thread_id=? ORDER BY m.created_at",
        (thread_id,),
    )
    vendor = None
    if thread["vendor_id"]:
        vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (thread["vendor_id"],), one=True)
    return render_template("buyer/thread.html", thread=thread, messages=messages, vendor=vendor)


@app.route("/app/buyer/evaluations")
@role_required("buyer")
def buyer_evaluations():
    u = g.user
    templates_ = dbm.query(
        "SELECT * FROM eval_templates WHERE company=? OR is_shared=1 ORDER BY created_at DESC",
        (u["company"],),
    )
    active = dbm.query(
        "SELECT e.*, v.company_name, v.accent, v.initials, t.name template_name "
        "FROM evaluations e JOIN vendors v ON v.id=e.vendor_id "
        "JOIN eval_templates t ON t.id = e.template_id "
        "WHERE e.company=? ORDER BY e.created_at DESC",
        (u["company"],),
    )
    active_data = []
    for ev in active:
        criteria = dbm.query(
            "SELECT * FROM eval_criteria WHERE template_id=? ORDER BY position", (ev["template_id"],)
        )
        total_weight = sum(c["weight"] for c in criteria) or 1
        scores = dbm.query(
            "SELECT * FROM eval_scores WHERE evaluation_id=?", (ev["id"],)
        )
        by_criterion = {}
        for s in scores:
            by_criterion.setdefault(s["criterion_id"], []).append(s["score"])
        weighted_sum = 0
        for c in criteria:
            vals = by_criterion.get(c["id"], [])
            avg = sum(vals) / len(vals) if vals else 0
            weighted_sum += avg * c["weight"]
        overall = round(weighted_sum / total_weight, 1) if scores else None
        active_data.append({**dict(ev), "overall": overall, "reviewers": len(set(s["user_id"] for s in scores))})
    return render_template("buyer/evaluations.html", templates=templates_, active=active_data)


@app.route("/app/buyer/evaluations/new", methods=("GET", "POST"))
@role_required("buyer")
def buyer_evaluation_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        labels = request.form.getlist("criterion_label")
        weights = request.form.getlist("criterion_weight")
        if not name or not any(l.strip() for l in labels):
            flash("Give your template a name and at least one criterion.", "error")
        else:
            template_id = dbm.execute(
                "INSERT INTO eval_templates (owner_user_id, company, name, description, is_shared) "
                "VALUES (?, ?, ?, ?, 1)",
                (g.user["id"], g.user["company"], name, description),
            )
            pos = 0
            for label, weight in zip(labels, weights):
                if label.strip():
                    dbm.execute(
                        "INSERT INTO eval_criteria (template_id, label, weight, position) "
                        "VALUES (?, ?, ?, ?)",
                        (template_id, label.strip(), int(weight or 1), pos),
                    )
                    pos += 1
            flash("Evaluation template created and shared with your team.", "success")
            return redirect(url_for("buyer_evaluations"))
    return render_template("buyer/evaluation_new.html")


@app.route("/app/buyer/evaluations/start/<int:vendor_id>", methods=("POST",))
@role_required("buyer")
def buyer_evaluation_start(vendor_id):
    template_id = request.form.get("template_id")
    if not template_id:
        flash("Choose an evaluation template first.", "error")
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))
    existing = dbm.query(
        "SELECT * FROM evaluations WHERE template_id=? AND vendor_id=? AND company=?",
        (template_id, vendor_id, g.user["company"]), one=True
    )
    if existing:
        return redirect(url_for("buyer_evaluation_detail", eval_id=existing["id"]))
    eval_id = dbm.execute(
        "INSERT INTO evaluations (template_id, vendor_id, company, created_by) VALUES (?, ?, ?, ?)",
        (template_id, vendor_id, g.user["company"], g.user["id"]),
    )
    existing_sl = dbm.query(
        "SELECT * FROM shortlist WHERE buyer_user_id=? AND vendor_id=?",
        (g.user["id"], vendor_id), one=True
    )
    if existing_sl:
        dbm.execute("UPDATE shortlist SET status='evaluating' WHERE id=?", (existing_sl["id"],))
    else:
        dbm.execute(
            "INSERT INTO shortlist (buyer_user_id, vendor_id, status) VALUES (?, ?, 'evaluating')",
            (g.user["id"], vendor_id),
        )
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    log_activity(g.user["id"], f"started an evaluation for {vendor['company_name']}")
    return redirect(url_for("buyer_evaluation_detail", eval_id=eval_id))


@app.route("/app/buyer/evaluations/detail/<int:eval_id>", methods=("GET", "POST"))
@role_required("buyer")
def buyer_evaluation_detail(eval_id):
    ev = dbm.query("SELECT * FROM evaluations WHERE id=?", (eval_id,), one=True)
    if not ev or ev["company"] != g.user["company"]:
        abort(404)
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (ev["vendor_id"],), one=True)
    template = dbm.query("SELECT * FROM eval_templates WHERE id=?", (ev["template_id"],), one=True)
    criteria = dbm.query(
        "SELECT * FROM eval_criteria WHERE template_id=? ORDER BY position", (ev["template_id"],)
    )

    if request.method == "POST":
        for c in criteria:
            score = request.form.get(f"score_{c['id']}")
            comment = request.form.get(f"comment_{c['id']}", "").strip()
            if score:
                dbm.execute(
                    "INSERT INTO eval_scores (evaluation_id, criterion_id, user_id, score, comment) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(evaluation_id, criterion_id, user_id) "
                    "DO UPDATE SET score=excluded.score, comment=excluded.comment",
                    (eval_id, c["id"], g.user["id"], int(score), comment),
                )
        log_activity(g.user["id"], f"submitted scores for {vendor['company_name']}")
        flash("Your scores were saved.", "success")
        return redirect(url_for("buyer_evaluation_detail", eval_id=eval_id))

    scores = dbm.query("SELECT * FROM eval_scores WHERE evaluation_id=?", (eval_id,))
    reviewers = {r["id"]: r for r in dbm.query(
        "SELECT * FROM users WHERE company=? AND role='buyer'", (g.user["company"],)
    )}
    my_scores = {s["criterion_id"]: s for s in scores if s["user_id"] == g.user["id"]}

    criterion_rows = []
    total_weight = sum(c["weight"] for c in criteria) or 1
    weighted_sum = 0
    for c in criteria:
        vals = [s["score"] for s in scores if s["criterion_id"] == c["id"]]
        avg = round(sum(vals) / len(vals), 1) if vals else None
        weighted_sum += (avg or 0) * c["weight"]
        criterion_rows.append({**dict(c), "avg": avg, "count": len(vals)})
    overall = round(weighted_sum / total_weight, 1) if scores else None

    by_reviewer = {}
    for s in scores:
        by_reviewer.setdefault(s["user_id"], []).append(s["score"])
    reviewer_rows = []
    for uid, vals in by_reviewer.items():
        reviewer_rows.append({
            "name": reviewers.get(uid, {"name": "Unknown"})["name"] if uid in reviewers else (
                g.user["name"] if uid == g.user["id"] else "Teammate"
            ),
            "avg": round(sum(vals) / len(vals), 1),
            "count": len(vals),
        })

    return render_template(
        "buyer/evaluation_detail.html",
        ev=ev, vendor=vendor, template=template, criteria=criterion_rows,
        my_scores=my_scores, overall=overall, reviewer_rows=reviewer_rows,
    )


@app.route("/app/buyer/schedule")
@role_required("buyer")
def buyer_schedule():
    meetings = dbm.query(
        "SELECT me.*, v.company_name, v.accent, v.initials FROM meetings me "
        "JOIN vendors v ON v.id=me.vendor_id WHERE me.buyer_user_id=? "
        "ORDER BY me.proposed_time",
        (g.user["id"],),
    )
    return render_template("buyer/schedule.html", meetings=meetings)


# ---------------------------------------------------------------------------
# Seller area
# ---------------------------------------------------------------------------

def seller_vendor(user):
    return dbm.query("SELECT * FROM vendors WHERE seller_user_id=?", (user["id"],), one=True)


@app.route("/app/seller")
@role_required("seller")
def seller_dashboard():
    vendor = seller_vendor(g.user)
    if not vendor:
        abort(404)
    leads = dbm.query(
        "SELECT s.*, u.name buyer_name, u.company buyer_company FROM shortlist s "
        "JOIN users u ON u.id = s.buyer_user_id WHERE s.vendor_id=? "
        "ORDER BY s.created_at DESC",
        (vendor["id"],),
    )
    thread_leads = dbm.query(
        "SELECT DISTINCT u.id, u.name, u.company FROM threads t JOIN users u ON u.id=t.buyer_user_id "
        "WHERE t.type='vendor' AND t.vendor_id=?",
        (vendor["id"],),
    )
    unread = dbm.query(
        "SELECT COUNT(*) c FROM messages m JOIN threads t ON t.id=m.thread_id "
        "WHERE t.type='vendor' AND t.vendor_id=? AND m.sender_user_id != ?",
        (vendor["id"], g.user["id"]), one=True
    )["c"]
    meetings = dbm.query(
        "SELECT me.*, u.name buyer_name, u.company buyer_company FROM meetings me "
        "JOIN users u ON u.id = me.buyer_user_id WHERE me.vendor_id=? ORDER BY me.proposed_time",
        (vendor["id"],),
    )
    counts = {
        "leads": len(set([l["buyer_user_id"] for l in leads] + [t["id"] for t in thread_leads])),
        "messages": unread,
        "meetings": len(meetings),
        "listings": dbm.query("SELECT COUNT(*) c FROM listings WHERE vendor_id=?", (vendor["id"],), one=True)["c"],
    }
    return render_template(
        "seller/dashboard.html", vendor=vendor, leads=leads[:6], counts=counts, meetings=meetings[:5]
    )


@app.route("/app/seller/profile", methods=("GET", "POST"))
@role_required("seller")
def seller_profile():
    vendor = seller_vendor(g.user)
    if request.method == "POST":
        form = request.form
        dbm.execute(
            "UPDATE vendors SET company_name=?, category=?, tagline=?, description=?, "
            "website=?, accent=?, initials=? WHERE id=?",
            (
                form["company_name"].strip(), form["category"].strip(), form["tagline"].strip(),
                form["description"].strip(), form["website"].strip(), form["accent"].strip() or "#2a78d6",
                (form["initials"].strip() or "VN")[:3].upper(), vendor["id"],
            ),
        )
        dbm.execute("DELETE FROM vendor_tags WHERE vendor_id=?", (vendor["id"],))
        for tag in form.get("tags", "").split(","):
            tag = tag.strip()
            if tag:
                dbm.execute(
                    "INSERT INTO vendor_tags (vendor_id, tag) VALUES (?, ?)", (vendor["id"], tag)
                )
        flash("Vendor profile updated — buyers will see the latest version.", "success")
        return redirect(url_for("seller_profile"))
    tags = ", ".join(vendor_tags(vendor["id"]))
    listings = vendor_listings(vendor["id"])
    return render_template("seller/profile.html", vendor=vendor, tags=tags, listings=listings)


@app.route("/app/seller/listings/new", methods=("POST",))
@role_required("seller")
def seller_listing_new():
    vendor = seller_vendor(g.user)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    pricing_model = request.form.get("pricing_model", "").strip()
    features = [f.strip() for f in request.form.get("features", "").split("\n") if f.strip()]
    if name:
        listing_id = dbm.execute(
            "INSERT INTO listings (vendor_id, name, description, pricing_model) VALUES (?, ?, ?, ?)",
            (vendor["id"], name, description, pricing_model),
        )
        for feat in features:
            dbm.execute(
                "INSERT INTO listing_features (listing_id, feature_text) VALUES (?, ?)",
                (listing_id, feat),
            )
        flash("Product listing added to your vendor profile.", "success")
    return redirect(url_for("seller_profile"))


@app.route("/app/seller/listings/<int:listing_id>/delete", methods=("POST",))
@role_required("seller")
def seller_listing_delete(listing_id):
    vendor = seller_vendor(g.user)
    listing = dbm.query(
        "SELECT * FROM listings WHERE id=? AND vendor_id=?", (listing_id, vendor["id"]), one=True
    )
    if listing:
        dbm.execute("DELETE FROM listing_features WHERE listing_id=?", (listing_id,))
        dbm.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        flash("Listing removed.", "success")
    return redirect(url_for("seller_profile"))


@app.route("/app/seller/leads")
@role_required("seller")
def seller_leads():
    vendor = seller_vendor(g.user)
    leads = dbm.query(
        "SELECT s.*, u.name buyer_name, u.company buyer_company, u.title buyer_title "
        "FROM shortlist s JOIN users u ON u.id=s.buyer_user_id "
        "WHERE s.vendor_id=? ORDER BY s.created_at DESC",
        (vendor["id"],),
    )
    return render_template("seller/leads.html", vendor=vendor, leads=leads)


@app.route("/app/seller/leads/<int:lead_user_id>/sync", methods=("POST",))
@role_required("seller")
def seller_leads_sync(lead_user_id):
    flash("Lead synced to Salesforce as a new opportunity. (demo simulation)", "success")
    return redirect(url_for("seller_leads"))


@app.route("/app/seller/messages")
@role_required("seller")
def seller_messages():
    vendor = seller_vendor(g.user)
    threads = dbm.query(
        "SELECT t.*, u.name buyer_name, u.company buyer_company, "
        "(SELECT body FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_body, "
        "(SELECT created_at FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_at "
        "FROM threads t JOIN users u ON u.id = t.buyer_user_id "
        "WHERE t.type='vendor' AND t.vendor_id=? ORDER BY last_at DESC",
        (vendor["id"],),
    )
    return render_template("seller/messages.html", threads=threads, vendor=vendor)


@app.route("/app/seller/messages/<int:thread_id>", methods=("GET", "POST"))
@role_required("seller")
def seller_thread(thread_id):
    thread = _load_thread_for_user(thread_id, g.user)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            dbm.execute(
                "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
                (thread_id, g.user["id"], body),
            )
        return redirect(url_for("seller_thread", thread_id=thread_id))
    messages = dbm.query(
        "SELECT m.*, u.name sender_name, u.role sender_role FROM messages m "
        "JOIN users u ON u.id = m.sender_user_id WHERE thread_id=? ORDER BY m.created_at",
        (thread_id,),
    )
    buyer = dbm.query("SELECT * FROM users WHERE id=?", (thread["buyer_user_id"],), one=True)
    return render_template("seller/thread.html", thread=thread, messages=messages, buyer=buyer)


@app.route("/app/seller/meetings/<int:meeting_id>/<action>", methods=("POST",))
@role_required("seller")
def seller_meeting_action(meeting_id, action):
    if action not in ("confirmed", "declined"):
        abort(400)
    vendor = seller_vendor(g.user)
    meeting = dbm.query(
        "SELECT * FROM meetings WHERE id=? AND vendor_id=?", (meeting_id, vendor["id"]), one=True
    )
    if meeting:
        dbm.execute("UPDATE meetings SET status=? WHERE id=?", (action, meeting_id))
        flash(f"Meeting {action}.", "success")
    return redirect(url_for("seller_dashboard"))


@app.route("/app/seller/partners", methods=("GET", "POST"))
@role_required("seller")
def seller_partners():
    vendor = seller_vendor(g.user)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        org = request.form.get("org", "").strip()
        role = request.form.get("role", "Alliance Partner").strip()
        email = request.form.get("email", "").strip()
        if name and org:
            dbm.execute(
                "INSERT INTO partner_contacts (seller_user_id, name, org, role, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (g.user["id"], name, org, role, email),
            )
            flash("Partner added to your collaboration portal.", "success")
        return redirect(url_for("seller_partners"))
    partners = dbm.query(
        "SELECT * FROM partner_contacts WHERE seller_user_id=? ORDER BY org, name", (g.user["id"],)
    )
    return render_template("seller/partners.html", vendor=vendor, partners=partners)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055, debug=True)
