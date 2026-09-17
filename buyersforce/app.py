import os
import re
import sqlite3
import secrets
from functools import wraps
from datetime import datetime, timedelta
from urllib.parse import quote as urlquote

import pytz
from flask import (
    Flask, g, render_template, request, redirect, url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

import db as dbm
import emailer

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "buyersforce-dev-secret-key-demo-only")
dbm.init_app(app)


# ---------------------------------------------------------------------------
# Profile fields
# ---------------------------------------------------------------------------

US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"),
    ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
    ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
    ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]
US_STATE_CODES = {code for code, _ in US_STATES}

# (ISO 3166-1 alpha-2, name, calling code) for the phone-number country
# picker. Not exhaustive -- covers the countries a B2B tech buyer/seller
# audience is realistically based in. "XX" is a catch-all for anyone else:
# no dial code is prefixed and digits are just lightly grouped, so nobody
# is stuck if their country isn't listed.
PHONE_COUNTRIES = [
    ("US", "United States", "1"), ("CA", "Canada", "1"),
    ("GB", "United Kingdom", "44"), ("IE", "Ireland", "353"),
    ("AU", "Australia", "61"), ("NZ", "New Zealand", "64"),
    ("DE", "Germany", "49"), ("FR", "France", "33"), ("IT", "Italy", "39"),
    ("ES", "Spain", "34"), ("PT", "Portugal", "351"), ("NL", "Netherlands", "31"),
    ("BE", "Belgium", "32"), ("LU", "Luxembourg", "352"), ("CH", "Switzerland", "41"),
    ("AT", "Austria", "43"), ("SE", "Sweden", "46"), ("NO", "Norway", "47"),
    ("DK", "Denmark", "45"), ("FI", "Finland", "358"), ("IS", "Iceland", "354"),
    ("PL", "Poland", "48"), ("CZ", "Czech Republic", "420"), ("SK", "Slovakia", "421"),
    ("HU", "Hungary", "36"), ("RO", "Romania", "40"), ("BG", "Bulgaria", "359"),
    ("GR", "Greece", "30"), ("HR", "Croatia", "385"), ("SI", "Slovenia", "386"),
    ("EE", "Estonia", "372"), ("LV", "Latvia", "371"), ("LT", "Lithuania", "370"),
    ("UA", "Ukraine", "380"), ("RU", "Russia", "7"), ("TR", "Turkey", "90"),
    ("IL", "Israel", "972"), ("AE", "United Arab Emirates", "971"),
    ("SA", "Saudi Arabia", "966"), ("QA", "Qatar", "974"), ("KW", "Kuwait", "965"),
    ("BH", "Bahrain", "973"), ("OM", "Oman", "968"), ("EG", "Egypt", "20"),
    ("ZA", "South Africa", "27"), ("NG", "Nigeria", "234"), ("KE", "Kenya", "254"),
    ("GH", "Ghana", "233"), ("IN", "India", "91"), ("PK", "Pakistan", "92"),
    ("BD", "Bangladesh", "880"), ("LK", "Sri Lanka", "94"), ("CN", "China", "86"),
    ("HK", "Hong Kong", "852"), ("TW", "Taiwan", "886"), ("JP", "Japan", "81"),
    ("KR", "South Korea", "82"), ("SG", "Singapore", "65"), ("MY", "Malaysia", "60"),
    ("TH", "Thailand", "66"), ("ID", "Indonesia", "62"), ("PH", "Philippines", "63"),
    ("VN", "Vietnam", "84"), ("BR", "Brazil", "55"), ("MX", "Mexico", "52"),
    ("AR", "Argentina", "54"), ("CL", "Chile", "56"), ("CO", "Colombia", "57"),
    ("PE", "Peru", "51"), ("UY", "Uruguay", "598"),
    ("XX", "Other / not listed", ""),
]


def _build_world_timezones():
    """Groups pytz's curated ~430-zone "common_timezones" list by region
    (the part before the first "/") for a worldwide, DST-safe time zone
    picker -- using real IANA identifiers (e.g. "America/New_York") rather
    than the old US-only "Eastern"/"Central"/... labels, which don't mean
    anything outside the US and had no room to grow as BuyersForce expands.
    Returns [(region, [(iana_name, display_label), ...]), ...]."""
    # pytz.common_timezones also includes a few old-style aliases
    # ("US/Eastern", "Canada/Atlantic", ...) for the same cities that
    # already appear under "America/..." -- skip those groups so each
    # zone shows up exactly once instead of twice under different names.
    alias_regions = {"US", "Canada"}
    groups = {}
    standalone = []
    for tz in sorted(pytz.common_timezones):
        label = tz.split("/")[-1].replace("_", " ")
        if "/" in tz:
            region = tz.split("/", 1)[0]
            if region in alias_regions:
                continue
            groups.setdefault(region, []).append((tz, label))
        else:
            standalone.append((tz, label))
    grouped = [(region, groups[region]) for region in sorted(groups)]
    if standalone:
        grouped.append(("Other", standalone))
    return grouped


# [(region, [(iana_name, display_label), ...]), ...] -- see
# _build_world_timezones. The region groupings and city names are static,
# so this is computed once at import time; each option's GMT offset is
# NOT baked in here since it can flip across a DST boundary while the
# server keeps running -- see world_timezones_for_picker().
WORLD_TIMEZONES = _build_world_timezones()
WORLD_TIMEZONE_CODES = set(pytz.common_timezones)

# The four continental US zones, pinned at the top of the time zone picker
# ahead of the alphabetical region groups -- most of BuyersForce's early
# users are US-based, so Eastern/Central/Mountain/Pacific are what most
# people will be looking for first. Same IANA zones as LEGACY_TIMEZONE_MAP
# below (minus Alaska/Hawaii, which aren't pinned).
US_QUICK_TIMEZONES = [
    ("America/New_York", "Eastern"),
    ("America/Chicago", "Central"),
    ("America/Denver", "Mountain"),
    ("America/Los_Angeles", "Pacific"),
]


def _gmt_offset_label(iana_name):
    """Current UTC offset for an IANA zone, formatted like "GMT-4" or
    "GMT+5:30" -- computed fresh per call (not cached) so it's always
    correct even right after a DST transition, without needing a deploy."""
    offset = datetime.now(pytz.timezone(iana_name)).utcoffset()
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"GMT{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def world_timezones_for_picker():
    """WORLD_TIMEZONES, with a "United States" group of the four pinned
    zones prepended and every option's label annotated with its current
    GMT offset -- e.g. "Eastern (GMT-4)", "New York (GMT-4)". Called per
    request (not cached at import time) so offsets stay accurate."""
    us_group = ("United States", [
        (iana, f"{label} ({_gmt_offset_label(iana)})") for iana, label in US_QUICK_TIMEZONES
    ])
    rest = [
        (region, [(iana, f"{label} ({_gmt_offset_label(iana)})") for iana, label in zones])
        for region, zones in WORLD_TIMEZONES
    ]
    return [us_group] + rest

# Old pre-worldwide values, migrated to real IANA zones by migrate.py's
# _migrate_legacy_timezones -- kept here only so nothing else has to guess
# at the mapping if it's ever needed again.
LEGACY_TIMEZONE_MAP = {
    "Eastern": "America/New_York",
    "Central": "America/Chicago",
    "Mountain": "America/Denver",
    "Pacific": "America/Los_Angeles",
    "Alaska": "America/Anchorage",
    "Hawaii": "Pacific/Honolulu",
}

# Starting vocabulary for "Sub-Categories / Segments" -- matches the
# categories used when compiling seed_data/vendor_seed_list.json from
# GitHub's awesome-cybersecurity list, CB Insights market maps, and
# Momentum Cyber's Cybersecurity Almanac. This list is now HISTORICAL: it's
# only read by migrate.py's one-time seed of the technology_segments table
# (mirrored there, not imported, since migrate.py is a standalone script).
# The live, seller/admin-extensible source of truth is that DB table --
# see all_technology_segments() -- so a value added there after launch
# won't appear in this constant, and nothing in this file should validate
# against CYBERSECURITY_SEGMENTS anymore.
CYBERSECURITY_SEGMENTS = [
    "API Security",
    "Application Security",
    "Backup & Ransomware Recovery",
    "Cloud Security",
    "Data Security & Privacy",
    "Email Security",
    "Endpoint Security",
    "Fraud & Identity Verification",
    "GRC & Compliance",
    "Identity & Access Management",
    "Incident Response & Forensics",
    "IoT/OT Security",
    "Managed Security Services (MSSP/MDR)",
    "Mobile Security",
    "Network Security",
    "Penetration Testing/Offensive Security",
    "Security Awareness Training",
    "SIEM/SOAR/XDR",
    "Supply Chain/Third-Party Risk",
    "Threat Intelligence",
    "Vulnerability Management",
    "Zero Trust/SASE",
]

# Company-size bands used for both the seed data (see the research agent's
# bucketing) and the buyer directory's size filter -- ordered smallest to
# largest rather than alphabetically (a plain DISTINCT+ORDER BY on the text
# values would put "10000+" before "51-200").
COMPANY_SIZE_BANDS = [
    "1-10", "11-50", "51-200", "201-500", "501-1000",
    "1001-5000", "5001-10000", "10000+",
]


# Support request categories -- shown as a select on the Support page and
# used to badge/filter requests on the admin side. Values are stored on
# support_requests.category; labels are what the user sees.
SUPPORT_CATEGORIES = [
    ("tech_support", "Technical support"),
    ("bug_report", "Report a bug or issue"),
    ("feature_request", "Feature enhancement request"),
]
SUPPORT_CATEGORY_LABELS = dict(SUPPORT_CATEGORIES)


# "Technology Category" -- BuyersForce's top-level vendor classification,
# shown ahead of "Sub-Categories / Segments" everywhere a vendor is
# classified or a buyer filters. Multi-select, seller/admin-extensible;
# see the technology_categories DB table and all_technology_categories().
# (Replaces the old single-value, cybersecurity-only technology_category
# column/select -- that column is left in place but no longer read or
# written, kept only for any historical row that still has it.)

# Vendor-directory listing requests -- see the vendor_requests table.
VENDOR_REQUEST_KIND_LABELS = {
    "buyer_referral": "Buyer suggestion",
    "seller_referral": "Seller suggestion",
    "seller_signup": "Vendor self-listing",
}


# Discover-page sort options -- "alphabetically" (company name) or
# "numerically" (company size band / founded year) so buyers can jump
# straight to a vendor while scanning a long, filtered list.
DISCOVER_SORT_OPTIONS = [
    ("name_asc", "Name (A-Z)"),
    ("name_desc", "Name (Z-A)"),
    ("size_desc", "Company size (largest first)"),
    ("size_asc", "Company size (smallest first)"),
    ("founded_desc", "Founded year (newest first)"),
    ("founded_asc", "Founded year (oldest first)"),
]
DISCOVER_SORT_KEYS = {key for key, _label in DISCOVER_SORT_OPTIONS}

# Jump-to-letter strip on Discover -- "#" buckets any company name that
# doesn't start with A-Z (a digit or symbol), so every vendor always has a
# bucket even before the taxonomy grows.
DISCOVER_JUMP_LETTERS = ["#"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]

# BuyersForce-native crowdsourced vendor ratings. Two phases per buyer per
# vendor: an "evaluation" rating (submitted any time a buyer is actively
# evaluating/shortlisting/has selected a vendor) and a "production" check-in
# rating, which only opens up RATING_CHECKIN_DAYS after the buyer marks a
# vendor "selected" -- the idea being the initial read on a vendor may not
# hold up once a team has actually lived with it. Both phases score the same
# three underlying dimensions (plus an overall) so aggregates are directly
# comparable, but the QUESTION WORDING differs by phase -- pre-sales framing
# for evaluation, lived-with-it framing for production -- since Kevin wants
# the production questions to reflect what only becomes apparent after go-live.
RATING_PHASES = ("evaluation", "production")
RATING_PHASE_LABELS = {"evaluation": "Evaluation", "production": "90-Day Check-in"}
RATING_DIMENSIONS = [
    ("product_score", "Product & technical fit"),
    ("support_score", "Customer service & support"),
    ("sales_score", "Sales team & buying experience"),
]
RATING_PHASE_QUESTIONS = {
    "evaluation": {
        "product_score": "How well did the product meet your technical requirements during evaluation?",
        "support_score": "How responsive and helpful was their team during the sales process?",
        "sales_score": "How was the sales experience -- transparency, pricing, negotiation?",
        "overall_score": "Overall, how would you rate this vendor based on your evaluation?",
    },
    "production": {
        "product_score": "Now that it's deployed, how well does the product perform in production?",
        "support_score": "How has their customer support/service been since go-live?",
        "sales_score": "How has the ongoing account relationship been -- renewals, upsells, responsiveness?",
        "overall_score": "Overall, now that you've lived with it, how would you rate this vendor?",
    },
}
# How many days after "selected" the production check-in becomes available.
# No scheduled-job/reminder-email infrastructure exists yet (see emailer.py --
# it's used for invites only), so eligibility is computed on-page-load
# instead of via a proactive reminder: buyer_dashboard() surfaces a banner
# for any selected vendor that has crossed this threshold without a
# check-in yet, whenever the buyer happens to visit.
RATING_CHECKIN_DAYS = 90

# Discover lets a buyer select up to this many vendors to research
# side-by-side on Compare; Compare's own "Short List" checkboxes then let
# them down-select to a smaller set to actually move into Evaluations.
DISCOVER_COMPARE_MAX = 5
SHORTLIST_MOVE_MAX = 3

# Pipeline order for shortlist.status, used by bump_shortlist_forward() below
# so a bulk action (like Compare's "Move to Evaluation") only ever advances a
# vendor's status, never regresses one a buyer already pushed further along
# (e.g. already 'selected'). 'passed' is intentionally left out -- a buyer
# who passed on a vendor has to bring it back manually, not via a bulk action.
SHORTLIST_PIPELINE_ORDER = {"discovered": 0, "shortlisted": 1, "evaluating": 2, "selected": 3}


def vendor_favicon_url(website):
    """Best-effort logo image for a vendor card, derived from their
    website via Google's public favicon service -- no API key or account
    needed (Clearbit's old free logo API was shut down in Dec 2025, and
    every modern replacement requires a signup). Quality varies -- some
    domains only have a small/generic icon -- so callers always keep the
    initials/accent badge as a fallback (see the vendor-logo-wrap markup)
    for when this doesn't load or doesn't look right."""
    if not website:
        return None
    domain = website.strip()
    domain = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
    domain = domain.split("/")[0]
    domain = re.sub(r"^www\.", "", domain, flags=re.IGNORECASE)
    if not domain:
        return None
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


app.jinja_env.globals["vendor_favicon_url"] = vendor_favicon_url


def vendor_display_logo_url(v):
    """Precedence for a vendor's displayed logo, given a row/dict that
    includes logo_upload_data_url, logo_link_url, wiki_logo_url, and
    website: a seller-uploaded image wins, then a seller-provided direct
    link, then the admin-curated Wikipedia logo, then a favicon guess from
    the website. None means the caller falls back to the initials badge
    (every logo-wrap template already does this)."""
    return (
        v.get("logo_upload_data_url")
        or v.get("logo_link_url")
        or v.get("wiki_logo_url")
        or vendor_favicon_url(v.get("website"))
    )


def buyer_outreach_badge(row, prefix=""):
    """The single badge shown to sellers for a buyer's "Open to Outreach"
    setting -- leads dashboard, conversation header. `row` is a user row
    (or an aliased projection of one, e.g. seller_leads()'s buyer_-prefixed
    columns -- pass prefix="buyer_" for that shape). Shows the strongest
    signal only when more than one sub-option is checked, in this order:
    Open to Buy > Marketing & Events > Informational Only > Not Seeking
    Outreach. Returns None (no badge) when outreach isn't enabled at all,
    matching today's "no badge" look for anyone who hasn't opted in."""
    if not row or not row.get(prefix + "outreach_enabled"):
        return None
    if row.get(prefix + "open_to_buy"):
        return {"label": "Open to Buy", "css_class": "badge-brand"}
    if row.get(prefix + "outreach_marketing_events"):
        return {"label": "Marketing & Events", "css_class": "badge-good"}
    if row.get(prefix + "outreach_informational"):
        return {"label": "Informational Only", "css_class": "badge-neutral"}
    if row.get(prefix + "outreach_none"):
        return {"label": "Not Seeking Outreach", "css_class": "badge-warning"}
    return None


app.jinja_env.globals["buyer_outreach_badge"] = buyer_outreach_badge

# Shown wherever a buyer-facing screen links out to a vendor's own website
# (Discover's vendor profile, Compare, and an evaluation's header) --
# BuyersForce doesn't control what happens after that click, and most
# vendor sites run their own analytics, so buyers should know they may be
# tracked (clicks, time on page, etc.) once they leave. A single constant
# so the wording can't drift between the three places it appears.
EXTERNAL_LINK_PRIVACY_NOTE = (
    "Leaving BuyersForce — the vendor's site may track this visit (clicks, time on page, and more)."
)
app.jinja_env.globals["EXTERNAL_LINK_PRIVACY_NOTE"] = EXTERNAL_LINK_PRIVACY_NOTE

# Checked dynamically against the user row rather than tracked with a
# stored flag, so there's nothing that can drift out of sync. role,
# company, and email are guaranteed non-blank by the users table itself
# (set by an admin at invite time), so they aren't re-checked here.
PROFILE_REQUIRED_FIELDS = (
    "first_name", "last_name", "personal_email", "phone", "state", "title", "timezone",
)

# Endpoints reachable even with an incomplete profile: auth/public pages
# and the completion screen itself. Everything else redirects a buyer or
# seller with a missing required field to complete_profile.
PROFILE_EXEMPT_ENDPOINTS = {"static", "landing", "login", "logout", "signup", "accept_invite", "complete_profile"}


def profile_is_complete(user):
    if not all((user.get(f) or "").strip() for f in PROFILE_REQUIRED_FIELDS):
        return False
    # LinkedIn is required too, unless they've told us they don't have one --
    # see the no_linkedin checkbox in _profile_form.html / signup.html.
    if not user.get("no_linkedin") and not (user.get("linkedin_url") or "").strip():
        return False
    return True


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
    # "View as" mode: an admin can look at the platform through a buyer's or
    # seller's eyes without a separate login. While this is set, g.user is
    # the account being viewed (so every existing buyer/seller page just
    # works, unchanged) and impersonator_id remembers who to snap back to.
    g.impersonating = session.get("impersonator_id") is not None
    g.unread_count = unread_count_for(g.user) if g.user and g.user["role"] in ("buyer", "seller") else 0


@app.before_request
def enforce_profile_completion():
    # Forces buyers/sellers -- including accounts that existed before this
    # feature shipped -- through a mandatory profile screen the first time
    # they hit any real page with a required field still missing. Admins
    # and "view as" sessions are exempt: an admin looking through a buyer's
    # eyes shouldn't get stuck filling out that buyer's profile for them.
    if not g.user or g.user["role"] not in ("buyer", "seller"):
        return
    if g.impersonating:
        return
    if request.endpoint in PROFILE_EXEMPT_ENDPOINTS:
        return
    if not profile_is_complete(g.user):
        return redirect(url_for("complete_profile"))


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


def get_admin_user():
    """The BuyersForce admin account that support requests (and, in the
    future, listing-claim approvals) route to. There's exactly one today
    (Kevin) -- SELECT ... LIMIT 1 rather than hardcoding the id so this
    keeps working if a second admin is ever seeded."""
    return dbm.query("SELECT * FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1", one=True)


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


@app.route("/signup", methods=("GET", "POST"))
def signup():
    # Self-signup: anyone can request an account, but it starts 'pending'
    # and can't log in until a BuyersForce admin approves it (see
    # admin_approve_signup / admin_deny_signup) -- Kj reviews each one,
    # including the required LinkedIn link, before granting access.
    if g.user:
        return redirect(home_for_role(g.user["role"]))
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        company = request.form.get("company", "").strip()
        title = request.form.get("title", "").strip()
        work_email = request.form.get("email", "").strip().lower()
        personal_email = request.form.get("personal_email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        phone_country = (request.form.get("phone_country", "US").strip().upper() or "US")[:2]
        state = request.form.get("state", "").strip().upper()
        timezone = request.form.get("timezone", "").strip()
        linkedin_url = request.form.get("linkedin_url", "").strip()
        no_linkedin = request.form.get("no_linkedin") == "on"
        password = request.form.get("password", "")

        if no_linkedin:
            # Some people genuinely don't have a LinkedIn account. We still
            # want to know that explicitly (rather than a blank field that
            # could just be someone skipping a required field), so it's
            # stored as its own flag and linkedin_url is cleared regardless
            # of what was submitted for it.
            linkedin_url = ""

        error = None
        if role not in ("buyer", "seller"):
            error = "Choose whether you're a buyer or a seller."
        elif not all((first_name, last_name, company, title, work_email, personal_email,
                      phone, state, timezone, password)):
            error = "All fields are required."
        elif "@" not in work_email:
            error = "Work email doesn't look like a valid email address."
        elif "@" not in personal_email:
            error = "Personal email doesn't look like a valid email address."
        elif state not in US_STATE_CODES:
            error = "Choose a valid US state."
        elif timezone not in WORLD_TIMEZONE_CODES:
            error = "Choose a valid time zone."
        elif not no_linkedin and not linkedin_url:
            error = "LinkedIn is required, or check \"I don't have a LinkedIn account.\""
        elif not no_linkedin and "linkedin.com" not in linkedin_url.lower():
            error = "That doesn't look like a LinkedIn URL -- we need it to verify your request."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif dbm.query("SELECT id FROM users WHERE email = ?", (work_email,), one=True):
            error = "An account already exists (or is pending review) for that email."

        if error:
            flash(error, "error")
            form_data = request.form.to_dict()
            form_data["no_linkedin"] = no_linkedin
            return render_template(
                "signup.html", us_states=US_STATES, phone_countries=PHONE_COUNTRIES, world_timezones=world_timezones_for_picker(), form_data=form_data,
            )

        dbm.execute(
            "INSERT INTO users (role, name, first_name, last_name, email, password_hash, company, "
            "title, personal_email, phone, phone_country, state, timezone, linkedin_url, no_linkedin, "
            "account_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (role, f"{first_name} {last_name}", first_name, last_name, work_email,
             generate_password_hash(password), company, title, personal_email, phone, phone_country,
             state, timezone, linkedin_url, int(no_linkedin)),
        )
        return render_template("signup_pending.html")
    return render_template("signup.html", us_states=US_STATES, phone_countries=PHONE_COUNTRIES, world_timezones=world_timezones_for_picker(), form_data={})


@app.route("/join-as-vendor", methods=("GET", "POST"))
def vendor_signup():
    """Public, no-login-required: how a vendor who isn't a BuyersForce
    member yet -- and so can't reach the buyer-only Discover page or its
    "suggest a vendor" form -- gets their own company listed. Reachable
    from the landing page's Sellers section and from a link on Discover's
    "Don't see a company here?" box. Approving the resulting vendor_requests
    row (see admin_vendor_request_decide) is what actually creates their
    seller account and vendor listing."""
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        website = request.form.get("website", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        contact_title = request.form.get("contact_title", "").strip()
        contact_email = request.form.get("contact_email", "").strip().lower()
        contact_phone = request.form.get("contact_phone", "").strip()
        if not all((company_name, website, contact_name, contact_title, contact_email, contact_phone)):
            flash(
                "Company name, website, and your name/title/email/phone are all required "
                "so a BuyersForce admin can reach you.", "error",
            )
            form_data = request.form.to_dict()
            form_data["segments"] = request.form.getlist("segments")
            form_data["technology_categories"] = request.form.getlist("technology_categories")
            return render_template(
                "vendor_signup.html", all_segments=all_technology_segments(),
                all_technology_categories=all_technology_categories(),
                company_sizes=COMPANY_SIZE_BANDS, form_data=form_data,
            )

        new_category = _ensure_technology_category(request.form.get("new_technology_category", ""))
        technology_categories = _parse_proposed_technology_categories(
            ",".join(request.form.getlist("technology_categories"))
        )
        if new_category and new_category not in technology_categories:
            technology_categories.append(new_category)

        new_segment = _ensure_technology_segment(request.form.get("new_segment", ""))
        segments = _parse_proposed_segments(",".join(request.form.getlist("segments")))
        if new_segment and new_segment not in segments:
            segments.append(new_segment)

        company_size = request.form.get("company_size", "").strip()
        if company_size not in COMPANY_SIZE_BANDS:
            company_size = None
        founded_year = request.form.get("founded_year", "").strip()
        founded_year = int(founded_year) if founded_year.isdigit() else None
        hq_location = request.form.get("hq_location", "").strip()
        tagline = request.form.get("tagline", "").strip()
        description = request.form.get("description", "").strip()

        dbm.execute(
            "INSERT INTO vendor_requests (kind, company_name, website, tagline, description, "
            "proposed_segments, proposed_technology_categories, company_size, founded_year, "
            "hq_location, contact_name, contact_title, contact_email, contact_phone) "
            "VALUES ('seller_signup', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_name, website, tagline, description, ",".join(segments),
             ",".join(technology_categories), company_size, founded_year, hq_location,
             contact_name, contact_title, contact_email, contact_phone),
        )

        admin = get_admin_user()
        if admin:
            emailer.send_email(
                admin["email"],
                subject=f"New vendor wants to list on BuyersForce: {company_name}",
                text=(
                    f"{contact_name} ({contact_title}) submitted {company_name} to be listed on "
                    f"BuyersForce.\n\nWebsite: {website}\nContact: {contact_email} · {contact_phone}\n\n"
                    f"Review it in your admin dashboard: {url_for('admin_dashboard', _external=True)}"
                ),
                reply_to=contact_email,
            )
        return render_template("vendor_signup_pending.html", company_name=company_name)

    return render_template(
        "vendor_signup.html", all_segments=all_technology_segments(),
        all_technology_categories=all_technology_categories(),
        company_sizes=COMPANY_SIZE_BANDS, form_data={},
    )


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
        elif user["account_status"] == "pending":
            flash(
                "Your account request is still pending BuyersForce approval. "
                "We'll email you once it's been reviewed.", "error",
            )
        elif user["account_status"] == "denied":
            flash("This account request wasn't approved. Contact BuyersForce if you believe this is an error.", "error")
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
    if existing_user and existing_user["is_admin"]:
        # Safety net: an invite link should never be able to reset the master
        # admin account's password. This shouldn't normally be reachable
        # since admin_invite() blocks creating such an invite in the first
        # place, but a defensive check here costs nothing.
        return render_template("invite_invalid.html", reason="not_found")

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
                        "'', '', '', '#3b82f6', ?)",
                        (user_id, invite["company"],
                         "".join([w[0] for w in invite["company"].split()[:2]]).upper() or "VN"),
                    )
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            dbm.execute("UPDATE invites SET used_at = ? WHERE id = ?", (now_str, invite["id"]))
            session.clear()
            session["user_id"] = user_id
            flash("Your account is ready.", "success")
            return redirect(home_for_role(invite["role"]))
        flash(error, "error")

    return render_template("accept_invite.html", invite=invite, is_reset=existing_user is not None)


def _safe_redirect_target(value, fallback):
    """Only follow an internal, same-app relative path -- never an
    absolute URL or protocol-relative "//host/..." one -- so a form's
    "next" field can't be turned into an open redirect."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


MAX_PHOTO_BYTES = 2 * 1024 * 1024  # 2MB -- stored inline in the database (see _add_account_status_and_photo)


def _read_uploaded_photo(files):
    """Validates and base64-encodes an uploaded profile photo. Returns
    (data_url, error) -- data_url is None if no file was chosen (leave
    the existing photo alone) and error is None on success."""
    photo = files.get("photo")
    if not photo or not photo.filename:
        return None, None
    raw = photo.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        return None, "Profile photo must be 2MB or smaller."
    mimetype = photo.mimetype or ""
    if not mimetype.startswith("image/"):
        return None, "Profile photo must be an image file."
    import base64
    return f"data:{mimetype};base64,{base64.b64encode(raw).decode('ascii')}", None


MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2MB -- same limit as MAX_PHOTO_BYTES, stored inline


def _read_uploaded_vendor_logo(files):
    """Same validation/encoding as _read_uploaded_photo, for a vendor's
    logo upload on My Company. Returns (data_url, error) -- data_url is
    None if no file was chosen (leave the existing logo alone)."""
    logo = files.get("logo_upload")
    if not logo or not logo.filename:
        return None, None
    raw = logo.read(MAX_LOGO_BYTES + 1)
    if len(raw) > MAX_LOGO_BYTES:
        return None, "Logo image must be 2MB or smaller."
    mimetype = logo.mimetype or ""
    if not mimetype.startswith("image/"):
        return None, "Logo must be an image file."
    import base64
    return f"data:{mimetype};base64,{base64.b64encode(raw).decode('ascii')}", None


def _apply_profile_form(user, form, files=None):
    """Validates and saves the shared profile fields (used by both the
    mandatory first-completion screen and later edits from Account >
    Profile). Returns None on success, or an error message to flash.
    role is never handled here -- it's permanent, admin-only. Company
    and work email ARE user-editable (Kj: people do change companies),
    but changing company requires an explicit confirmation checkbox,
    since it's a shared teammate-grouping key -- changing it drops
    access to the old company's team threads and shared evaluation
    templates (not a data loss, just no longer visible to this account)."""
    files = files or {}
    first_name = form.get("first_name", "").strip()
    last_name = form.get("last_name", "").strip()
    work_email = form.get("email", "").strip().lower()
    personal_email = form.get("personal_email", "").strip().lower()
    phone = form.get("phone", "").strip()
    phone_country = (form.get("phone_country", "US").strip().upper() or "US")[:2]
    state = form.get("state", "").strip().upper()
    title = form.get("title", "").strip()
    company = form.get("company", "").strip()
    timezone = form.get("timezone", "").strip()

    if not all((first_name, last_name, work_email, personal_email, phone, state, title, company, timezone)):
        return ("First name, last name, company, work email, personal email, phone, job title, "
                "state, and time zone are all required.")
    if "@" not in work_email:
        return "Work email doesn't look like a valid email address."
    if "@" not in personal_email:
        return "Personal email doesn't look like a valid email address."
    if state not in US_STATE_CODES:
        return "Choose a valid US state."
    if timezone not in WORLD_TIMEZONE_CODES:
        return "Choose a valid time zone."
    if work_email != user["email"]:
        taken = dbm.query("SELECT id FROM users WHERE email = ? AND id != ?", (work_email, user["id"]), one=True)
        if taken:
            return "Another account already uses that work email."

    company_changed = company != user["company"]
    if company_changed and form.get("confirm_company_change") != "on":
        return (
            "Changing your company means you'll lose access to your current team's message "
            "threads and shared evaluation templates (your own shortlist and evaluations stay "
            "yours). Check the confirmation box below to continue."
        )

    no_linkedin = form.get("no_linkedin") == "on"
    linkedin_url = form.get("linkedin_url", "").strip()
    if no_linkedin:
        linkedin_url = ""
    elif not linkedin_url:
        return "LinkedIn is required, or check \"I don't have a LinkedIn account.\""
    elif "linkedin.com" not in linkedin_url.lower():
        return "That doesn't look like a LinkedIn URL."

    photo_data_url, photo_error = _read_uploaded_photo(files)
    if photo_error:
        return photo_error
    remove_photo = form.get("remove_photo") == "on"

    address_line1 = form.get("address_line1", "").strip()
    address_line2 = form.get("address_line2", "").strip()
    city = form.get("city", "").strip()
    zip_code = form.get("zip", "").strip()
    secondary_phone = form.get("secondary_phone", "").strip()
    secondary_phone_country = (form.get("secondary_phone_country", "US").strip().upper() or "US")[:2]
    # "Open to Outreach" -- buyer-only. The parent toggle gates three
    # independent sub-options (open_to_buy, informational, marketing &
    # events); "Not seeking outreach" says the opposite of all three, so
    # it wins over them here even if the profile form's JS (which mirrors
    # this exclusivity client-side) was bypassed.
    if user["role"] == "buyer":
        outreach_enabled = form.get("outreach_enabled") == "on"
        outreach_none = outreach_enabled and form.get("outreach_none") == "on"
        if outreach_none:
            outreach_informational = False
            outreach_marketing_events = False
            open_to_buy = False
        else:
            outreach_informational = outreach_enabled and form.get("outreach_informational") == "on"
            outreach_marketing_events = outreach_enabled and form.get("outreach_marketing_events") == "on"
            open_to_buy = outreach_enabled and form.get("open_to_buy") == "on"
    else:
        outreach_enabled = outreach_none = outreach_informational = outreach_marketing_events = False
        open_to_buy = False

    dbm.execute(
        "UPDATE users SET first_name=?, last_name=?, name=?, email=?, company=?, personal_email=?, "
        "phone=?, phone_country=?, state=?, title=?, address_line1=?, address_line2=?, city=?, zip=?, "
        "secondary_phone=?, secondary_phone_country=?, linkedin_url=?, no_linkedin=?, timezone=?, "
        "open_to_buy=?, outreach_enabled=?, outreach_informational=?, outreach_marketing_events=?, "
        "outreach_none=? WHERE id=?",
        (first_name, last_name, f"{first_name} {last_name}", work_email, company, personal_email,
         phone, phone_country, state, title, address_line1, address_line2, city, zip_code,
         secondary_phone, secondary_phone_country, linkedin_url, int(no_linkedin), timezone,
         int(open_to_buy), int(outreach_enabled), int(outreach_informational),
         int(outreach_marketing_events), int(outreach_none), user["id"]),
    )
    if photo_data_url:
        dbm.execute("UPDATE users SET photo_data_url=? WHERE id=?", (photo_data_url, user["id"]))
    elif remove_photo:
        dbm.execute("UPDATE users SET photo_data_url=NULL WHERE id=?", (user["id"],))

    if company_changed and user["role"] == "seller":
        # A seller's vendor listing is 1:1 with them, so this is safe --
        # unlike team threads, nobody else's data is affected.
        vendor = dbm.query("SELECT * FROM vendors WHERE seller_user_id = ?", (user["id"],), one=True)
        if vendor:
            dbm.execute("UPDATE vendors SET company_name=? WHERE id=?", (company, vendor["id"]))
    if company_changed:
        log_activity(user["id"], f"changed their own company from {user['company']} to {company}")
    return None


@app.route("/app/complete-profile", methods=("GET", "POST"))
@login_required
def complete_profile():
    if g.user["role"] not in ("buyer", "seller"):
        return redirect(home_for_role(g.user["role"]))
    if profile_is_complete(g.user):
        return redirect(home_for_role(g.user["role"]))
    if request.method == "POST":
        error = _apply_profile_form(g.user, request.form, request.files)
        if error:
            flash(error, "error")
        else:
            flash("Profile complete -- welcome to BuyersForce.", "success")
            return redirect(home_for_role(g.user["role"]))
        # Re-fetch so the form reflects whatever partial edits are valid,
        # and so we're not rendering a stale g.user from before the (failed) update.
        g.user = dbm.query("SELECT * FROM users WHERE id=?", (g.user["id"],), one=True)
    return render_template(
        "complete_profile.html", us_states=US_STATES, phone_countries=PHONE_COUNTRIES, world_timezones=world_timezones_for_picker(), user=g.user,
    )


@app.route("/app/account")
@login_required
def account():
    tab = request.args.get("tab", "profile")
    if tab not in ("profile", "password", "blocked") or (tab == "blocked" and g.user["role"] != "buyer"):
        tab = "profile"
    blocked = []
    if g.user["role"] == "buyer":
        blocked = dbm.query(
            "SELECT b.*, u.name blocked_name, u.company blocked_user_company FROM blocked_vendors b "
            "LEFT JOIN users u ON u.id = b.blocked_user_id WHERE b.buyer_user_id=? ORDER BY b.created_at DESC",
            (g.user["id"],),
        )
    pending_role_request = None
    if g.user["role"] in ("buyer", "seller"):
        pending_role_request = dbm.query(
            "SELECT * FROM role_change_requests WHERE user_id=? AND status='pending'",
            (g.user["id"],), one=True,
        )
    return render_template(
        "account.html", tab=tab, us_states=US_STATES, phone_countries=PHONE_COUNTRIES, world_timezones=world_timezones_for_picker(),
        blocked=blocked, user=g.user, pending_role_request=pending_role_request, show_role_change=True,
    )


@app.route("/app/account/profile", methods=("POST",))
@login_required
def account_profile():
    error = _apply_profile_form(g.user, request.form, request.files)
    if error:
        flash(error, "error")
    else:
        flash("Profile updated.", "success")
    return redirect(url_for("account", tab="profile"))


@app.route("/app/account/theme", methods=("POST",))
@login_required
def account_theme():
    theme = request.form.get("theme_preference")
    if theme not in ("light", "dark"):
        flash("Invalid appearance selection.", "error")
    else:
        dbm.execute("UPDATE users SET theme_preference = ? WHERE id = ?", (theme, g.user["id"]))
        flash(f"Switched to {theme} mode.", "success")
    return redirect(url_for("account", tab="profile"))


@app.route("/app/account/password", methods=("POST",))
@login_required
def account_password():
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
    else:
        flash(error, "error")
    return redirect(url_for("account", tab="password"))


@app.route("/app/account/role-change-request", methods=("POST",))
@login_required
def request_role_change():
    if g.user["role"] not in ("buyer", "seller"):
        flash("Only buyer and seller accounts can request a role change.", "error")
        return redirect(url_for("account", tab="profile"))
    existing = dbm.query(
        "SELECT id FROM role_change_requests WHERE user_id=? AND status='pending'",
        (g.user["id"],), one=True,
    )
    if existing:
        flash("You already have a role-change request pending review.", "error")
        return redirect(url_for("account", tab="profile"))
    other_role = "seller" if g.user["role"] == "buyer" else "buyer"
    dbm.execute(
        "INSERT INTO role_change_requests (user_id, previous_role, requested_role) VALUES (?, ?, ?)",
        (g.user["id"], g.user["role"], other_role),
    )
    log_activity(g.user["id"], f"requested a role change from {g.user['role']} to {other_role}")
    flash("Request sent -- a BuyersForce admin will review it.", "success")
    return redirect(url_for("account", tab="profile"))


@app.route("/app/account/blocked/add", methods=("POST",))
@role_required("buyer")
def block_vendor():
    blocked_user_id = request.form.get("blocked_user_id", type=int)
    blocked_email = request.form.get("blocked_email", "").strip().lower()
    blocked_company = request.form.get("blocked_company", "").strip()
    next_url = _safe_redirect_target(request.form.get("next"), url_for("account", tab="blocked"))

    if not blocked_user_id and not blocked_email and not blocked_company:
        flash("Enter an email or company name, or block someone from one of your conversations.", "error")
        return redirect(next_url)

    if blocked_user_id:
        existing = dbm.query(
            "SELECT 1 FROM blocked_vendors WHERE buyer_user_id=? AND blocked_user_id=?",
            (g.user["id"], blocked_user_id), one=True,
        )
        if existing:
            flash("Already blocked.", "error")
            return redirect(next_url)

    dbm.execute(
        "INSERT INTO blocked_vendors (buyer_user_id, blocked_user_id, blocked_email, blocked_company) "
        "VALUES (?, ?, ?, ?)",
        (g.user["id"], blocked_user_id or None, blocked_email or None, blocked_company or None),
    )
    flash("Blocked -- they won't be able to message you anymore.", "success")
    return redirect(next_url)


@app.route("/app/account/blocked/<int:block_id>/remove", methods=("POST",))
@role_required("buyer")
def unblock_vendor(block_id):
    dbm.execute(
        "DELETE FROM blocked_vendors WHERE id=? AND buyer_user_id=?",
        (block_id, g.user["id"]),
    )
    flash("Unblocked.", "success")
    return redirect(url_for("account", tab="blocked"))


# ---------------------------------------------------------------------------
# Admin area -- invite-only access control
# ---------------------------------------------------------------------------

@app.route("/app/admin")
@admin_required
def admin_dashboard():
    users = dbm.query(
        "SELECT * FROM users WHERE is_admin = 0 AND account_status = 'active' ORDER BY company, role, name"
    )
    pending_invites = dbm.query(
        "SELECT i.*, u.name invited_by_name FROM invites i JOIN users u ON u.id = i.invited_by "
        "WHERE i.used_at IS NULL ORDER BY i.created_at DESC"
    )
    pending_signups = dbm.query(
        "SELECT * FROM users WHERE account_status = 'pending' ORDER BY created_at DESC"
    )
    pending_role_changes = dbm.query(
        "SELECT rcr.*, u.name, u.email, u.title, u.company FROM role_change_requests rcr "
        "JOIN users u ON u.id = rcr.user_id WHERE rcr.status = 'pending' ORDER BY rcr.created_at DESC"
    )
    open_support_requests = dbm.query(
        "SELECT sr.*, u.name requester_name, u.company requester_company, u.role requester_role "
        "FROM support_requests sr JOIN users u ON u.id = sr.user_id "
        "WHERE sr.status != 'resolved' ORDER BY sr.created_at DESC"
    )
    pending_vendor_requests = dbm.query(
        "SELECT vr.*, u.name requester_name, u.company requester_company "
        "FROM vendor_requests vr LEFT JOIN users u ON u.id = vr.requested_by_user_id "
        "WHERE vr.status = 'pending' ORDER BY vr.created_at DESC"
    )
    known_segments = all_technology_segments()
    known_categories = all_technology_categories()
    pending_vendor_requests = [
        {
            **dict(r),
            "proposed_segments_list": _parse_proposed_segments(r["proposed_segments"], known_segments),
            "proposed_technology_categories_list": _parse_proposed_technology_categories(
                r["proposed_technology_categories"], known_categories
            ),
        }
        for r in pending_vendor_requests
    ]
    new_invite_link = None
    new_invite_id = request.args.get("new_invite", type=int)
    if new_invite_id:
        inv = dbm.query("SELECT * FROM invites WHERE id = ?", (new_invite_id,), one=True)
        if inv:
            new_invite_link = url_for("accept_invite", token=inv["token"], _external=True)
    return render_template(
        "admin/dashboard.html", users=users, pending_invites=pending_invites,
        pending_signups=pending_signups, pending_role_changes=pending_role_changes,
        open_support_requests=open_support_requests, support_category_labels=SUPPORT_CATEGORY_LABELS,
        pending_vendor_requests=pending_vendor_requests, vendor_request_kind_labels=VENDOR_REQUEST_KIND_LABELS,
        all_segments=known_segments, all_technology_categories=known_categories,
        company_sizes=COMPANY_SIZE_BANDS,
        new_invite_link=new_invite_link,
    )


@app.route("/app/admin/signups/<int:user_id>/approve", methods=("POST",))
@admin_required
def admin_approve_signup(user_id):
    user = dbm.query("SELECT * FROM users WHERE id=? AND account_status='pending'", (user_id,), one=True)
    if not user:
        abort(404)
    dbm.execute("UPDATE users SET account_status='active' WHERE id=?", (user_id,))
    if user["role"] == "seller":
        dbm.execute(
            "INSERT INTO vendors (seller_user_id, company_name, category, tagline, description, "
            "website, accent, initials) VALUES (?, ?, 'Uncategorized', '', '', '', '#3b82f6', ?)",
            (user_id, user["company"],
             "".join([w[0] for w in user["company"].split()[:2]]).upper() or "VN"),
        )
    log_activity(user_id, "account approved by admin")
    emailer.send_signup_decision(user["email"], approved=True, login_url=url_for("login", _external=True))
    flash(f"{user['name']} approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/app/admin/signups/<int:user_id>/deny", methods=("POST",))
@admin_required
def admin_deny_signup(user_id):
    user = dbm.query("SELECT * FROM users WHERE id=? AND account_status='pending'", (user_id,), one=True)
    if not user:
        abort(404)
    dbm.execute("UPDATE users SET account_status='denied' WHERE id=?", (user_id,))
    log_activity(user_id, "account denied by admin")
    emailer.send_signup_decision(user["email"], approved=False)
    flash(f"{user['name']}'s request denied.", "success")
    return redirect(url_for("admin_dashboard"))


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

    existing = dbm.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if existing and existing["is_admin"]:
        flash("That email belongs to an administrator account and can't be invited "
              "as a buyer or seller.", "error")
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


@app.route("/app/admin/users/<int:user_id>/company", methods=("POST",))
@admin_required
def admin_change_company(user_id):
    # Company is admin-only (not user-editable) because it's a shared
    # teammate-grouping key, not a personal field -- see the note on
    # _apply_profile_form. A seller's own vendor listing is 1:1 with
    # them, so updating its company_name here is safe. Team-thread
    # subjects are deliberately left alone: they embed the OLD company
    # name, so this user will naturally lose access to their old team's
    # threads (correct -- they've left) without disturbing teammates who
    # are still there and haven't been moved.
    user = dbm.query("SELECT * FROM users WHERE id = ? AND is_admin = 0", (user_id,), one=True)
    if not user:
        abort(404)
    new_company = request.form.get("company", "").strip()
    if not new_company:
        flash("Company name can't be blank.", "error")
        return redirect(url_for("admin_dashboard"))
    if new_company == user["company"]:
        return redirect(url_for("admin_dashboard"))

    dbm.execute("UPDATE users SET company = ? WHERE id = ?", (new_company, user_id))
    if user["role"] == "seller":
        vendor = dbm.query("SELECT * FROM vendors WHERE seller_user_id = ?", (user_id,), one=True)
        if vendor:
            dbm.execute("UPDATE vendors SET company_name = ? WHERE id = ?", (new_company, vendor["id"]))
    log_activity(user_id, f"company changed from {user['company']} to {new_company} by admin")
    flash(f"{user['name']}'s company changed to {new_company}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/app/admin/role-changes/<int:request_id>/approve", methods=("POST",))
@admin_required
def admin_approve_role_change(request_id):
    req = dbm.query(
        "SELECT * FROM role_change_requests WHERE id=? AND status='pending'", (request_id,), one=True
    )
    if not req:
        abort(404)
    user = dbm.query("SELECT * FROM users WHERE id=?", (req["user_id"],), one=True)
    if not user:
        abort(404)

    dbm.execute("UPDATE users SET role=? WHERE id=?", (req["requested_role"], user["id"]))
    if req["requested_role"] == "seller":
        vendor = dbm.query("SELECT id FROM vendors WHERE seller_user_id=?", (user["id"],), one=True)
        if not vendor:
            dbm.execute(
                "INSERT INTO vendors (seller_user_id, company_name, category, tagline, description, "
                "website, accent, initials) VALUES (?, ?, 'Uncategorized', '', '', '', '#3b82f6', ?)",
                (user["id"], user["company"],
                 "".join([w[0] for w in user["company"].split()[:2]]).upper() or "VN"),
            )
    # Moving FROM seller deliberately doesn't touch their existing vendor
    # listing -- deleting it would take its listings/evaluations with it.
    # It's just no longer reachable from a buyer-role account; clean it up
    # by hand if it should actually go away.

    resolved_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    dbm.execute(
        "UPDATE role_change_requests SET status='approved', resolved_at=?, resolved_by=? WHERE id=?",
        (resolved_at, g.user["id"], request_id),
    )
    log_activity(user["id"], f"role changed from {req['previous_role']} to {req['requested_role']} by admin")
    emailer.send_role_change_decision(
        user["email"], approved=True, new_role=req["requested_role"],
        login_url=url_for("login", _external=True),
    )
    flash(f"{user['name']}'s account type changed to {req['requested_role']}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/app/admin/role-changes/<int:request_id>/deny", methods=("POST",))
@admin_required
def admin_deny_role_change(request_id):
    req = dbm.query(
        "SELECT * FROM role_change_requests WHERE id=? AND status='pending'", (request_id,), one=True
    )
    if not req:
        abort(404)
    resolved_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    dbm.execute(
        "UPDATE role_change_requests SET status='denied', resolved_at=?, resolved_by=? WHERE id=?",
        (resolved_at, g.user["id"], request_id),
    )
    log_activity(req["user_id"], "role change request denied by admin")
    user = dbm.query("SELECT * FROM users WHERE id=?", (req["user_id"],), one=True)
    if user:
        emailer.send_role_change_decision(user["email"], approved=False)
    flash("Request denied.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/app/admin/view-as/<int:user_id>", methods=("POST",))
@admin_required
def admin_view_as(user_id):
    if session.get("impersonator_id"):
        flash("Return to your admin account before switching to someone else.", "error")
        return redirect(url_for("admin_dashboard"))
    target = dbm.query("SELECT * FROM users WHERE id = ? AND is_admin = 0", (user_id,), one=True)
    if not target:
        abort(404)
    log_activity(g.user["id"], f"started viewing as {target['name']} ({target['role']})")
    session["impersonator_id"] = g.user["id"]
    session["user_id"] = target["id"]
    flash(f"You're now viewing BuyersForce as {target['name']}.", "success")
    return redirect(home_for_role(target["role"]))


@app.route("/app/admin/stop-view-as", methods=("POST",))
def admin_stop_view_as():
    # Deliberately not @admin_required: while impersonating, g.user IS the
    # buyer/seller being viewed, so an admin-only check would lock the real
    # admin out of their own "return to admin" button. The session's
    # impersonator_id is the actual guard here.
    admin_id = session.get("impersonator_id")
    if not admin_id:
        abort(404)
    viewed_user = g.user
    session["user_id"] = admin_id
    session.pop("impersonator_id", None)
    if viewed_user:
        log_activity(admin_id, f"stopped viewing as {viewed_user['name']} ({viewed_user['role']})")
    flash("You're back in your admin account.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Shared helpers for buyer/seller areas
# ---------------------------------------------------------------------------

def teammates_of(user):
    return dbm.query(
        "SELECT * FROM users WHERE company = ? AND role = ? AND id != ? ORDER BY name",
        (user["company"], user["role"], user["id"]),
    )


# ---------------------------------------------------------------------------
# Direct messaging: "message anyone" (contacts, directory search, and
# messaging someone who isn't a BuyersForce member yet)
# ---------------------------------------------------------------------------

def is_message_blocked(buyer_id, seller):
    """True if the buyer identified by buyer_id has blocked this seller
    specifically, or has blocked every seller at the seller's company."""
    row = dbm.query(
        "SELECT 1 FROM blocked_vendors WHERE buyer_user_id = ? AND "
        "(blocked_user_id = ? OR LOWER(blocked_email) = LOWER(?) OR LOWER(blocked_company) = LOWER(?)) "
        "LIMIT 1",
        (buyer_id, seller["id"], seller["email"], seller["company"]),
        one=True,
    )
    return row is not None


def _can_message(user, candidate):
    """Buyers and sellers can message their own teammates and anyone on
    the other side of the marketplace. Buyers can additionally message
    any other buyer, at any company -- peer buyers often want a second
    opinion on a vendor or a referral, and that's worth more than the
    company boundary here. Sellers still can't reach competing sellers
    at another company. Admin accounts are never reachable this way
    (their role is neither 'buyer' nor 'seller', so every check below
    simply fails for them). A seller can never reach a buyer who has
    blocked them (or their whole company) via Account > Blocked Vendors."""
    if candidate["id"] == user["id"]:
        return False
    opposite = "seller" if user["role"] == "buyer" else "buyer"
    if candidate["role"] == opposite:
        if user["role"] == "seller" and is_message_blocked(candidate["id"], user):
            return False
        return True
    if user["role"] == "buyer" and candidate["role"] == "buyer":
        return True
    return candidate["role"] == user["role"] and candidate["company"] == user["company"]


def search_recipients(user, q):
    """Contacts (always shown) plus a directory search (only once the
    viewer has typed something) -- teammates and anyone on the other
    side of the marketplace, matched by name, company, or email."""
    results = []
    seen_user_ids = set()

    contact_rows = dbm.query(
        "SELECT c.*, u.name u_name, u.company u_company, u.role u_role, u.email u_email, "
        "u.photo_data_url u_photo "
        "FROM contacts c LEFT JOIN users u ON u.id = c.contact_user_id "
        "WHERE c.owner_user_id = ? ORDER BY COALESCE(u.name, c.external_name)",
        (user["id"],),
    )
    needle = q.lower().strip()
    for c in contact_rows:
        if c["contact_user_id"]:
            name, company, role, email, photo = c["u_name"], c["u_company"], c["u_role"], c["u_email"], c["u_photo"]
        else:
            name, company, role, email, photo = (
                c["external_name"] or c["external_email"], "", None, c["external_email"], None,
            )
        if needle and needle not in (name or "").lower() and needle not in (company or "").lower() \
                and needle not in (email or "").lower():
            continue
        results.append({
            "source": "contact", "user_id": c["contact_user_id"], "name": name,
            "company": company, "role": role, "email": email, "photo": photo,
        })
        if c["contact_user_id"]:
            seen_user_ids.add(c["contact_user_id"])

    if len(needle) >= 2:
        if user["role"] == "buyer":
            # Any other buyer (any company) or any seller -- mirrors the
            # widened _can_message rule above.
            directory_rows = dbm.query(
                "SELECT * FROM users WHERE is_admin = 0 AND role IN ('buyer', 'seller') "
                "AND id != ? AND (LOWER(name) LIKE ? OR LOWER(company) LIKE ? OR LOWER(email) LIKE ?) "
                "ORDER BY name LIMIT 25",
                (user["id"], f"%{needle}%", f"%{needle}%", f"%{needle}%"),
            )
        else:
            directory_rows = dbm.query(
                "SELECT * FROM users WHERE is_admin = 0 AND ((role = 'buyer') OR (role = 'seller' AND company = ?)) "
                "AND id != ? AND (LOWER(name) LIKE ? OR LOWER(company) LIKE ? OR LOWER(email) LIKE ?) "
                "ORDER BY name LIMIT 25",
                (user["company"], user["id"], f"%{needle}%", f"%{needle}%", f"%{needle}%"),
            )
        for r in directory_rows:
            if r["id"] in seen_user_ids:
                continue
            results.append({
                "source": "directory", "user_id": r["id"], "name": r["name"],
                "company": r["company"], "role": r["role"], "email": r["email"],
                "photo": r["photo_data_url"],
            })

    if user["role"] == "seller":
        # Don't surface a buyer who's blocked this seller (or their whole
        # company) -- mirrors the enforcement in _can_message, so a
        # blocked buyer just quietly doesn't show up in search rather
        # than showing up and then failing when messaged.
        results = [
            r for r in results
            if not (r["role"] == "buyer" and r["user_id"] and is_message_blocked(r["user_id"], user))
        ]
    return results


def ensure_contact(owner_id, contact_user_id=None, external_name=None, external_email=None):
    if contact_user_id:
        dbm.execute(
            "INSERT INTO contacts (owner_user_id, contact_user_id) VALUES (?, ?) "
            "ON CONFLICT (owner_user_id, contact_user_id) WHERE contact_user_id IS NOT NULL DO NOTHING",
            (owner_id, contact_user_id),
        )
    elif external_email:
        dbm.execute(
            "INSERT INTO contacts (owner_user_id, external_name, external_email) VALUES (?, ?, ?) "
            "ON CONFLICT (owner_user_id, external_email) "
            "WHERE contact_user_id IS NULL AND external_email IS NOT NULL DO NOTHING",
            (owner_id, external_name, external_email),
        )


def get_or_create_direct_thread(a_id, b_id):
    lo, hi = sorted((a_id, b_id))
    thread = dbm.query(
        "SELECT * FROM threads WHERE type='direct' AND participant_a_id=? AND participant_b_id=?",
        (lo, hi), one=True,
    )
    if thread:
        return thread
    thread_id = dbm.execute(
        "INSERT INTO threads (type, participant_a_id, participant_b_id, subject, created_by) "
        "VALUES ('direct', ?, ?, '', ?)",
        (lo, hi, a_id),
    )
    return dbm.query("SELECT * FROM threads WHERE id=?", (thread_id,), one=True)


def get_or_create_external_thread(sender_id, email, name=None):
    thread = dbm.query(
        "SELECT * FROM threads WHERE type='direct' AND participant_a_id=? "
        "AND participant_b_id IS NULL AND external_email=?",
        (sender_id, email), one=True,
    )
    if thread:
        return thread
    thread_id = dbm.execute(
        "INSERT INTO threads (type, participant_a_id, external_name, external_email, subject, created_by) "
        "VALUES ('direct', ?, ?, ?, '', ?)",
        (sender_id, name or email.split("@")[0], email, sender_id),
    )
    return dbm.query("SELECT * FROM threads WHERE id=?", (thread_id,), one=True)


def thread_with_user(user, other):
    """Route a "message this person" click to the right kind of thread:
    the existing buyer<->vendor thread when the other side is a seller,
    or a new 1:1 direct thread for a teammate."""
    opposite = "seller" if user["role"] == "buyer" else "buyer"
    if other["role"] == opposite:
        buyer, seller = (user, other) if user["role"] == "buyer" else (other, user)
        vendor = seller_vendor(seller)
        if not vendor:
            abort(400)
        return get_or_create_vendor_thread(buyer["id"], vendor["id"])
    return get_or_create_direct_thread(user["id"], other["id"])


def thread_display_info(thread, viewer):
    """Describes who/what a thread is with, regardless of its type, so
    buyer/thread.html and seller/thread.html can render one consistent
    header instead of special-casing every thread shape. For a 'vendor'
    thread the "other side" depends on which of the two is looking: a
    seller sees the buyer they're talking to, a buyer sees the vendor."""
    if thread["type"] == "vendor":
        if viewer["role"] == "seller":
            buyer = dbm.query("SELECT * FROM users WHERE id=?", (thread["buyer_user_id"],), one=True)
            return {"kind": "vendor", "buyer": buyer}
        vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (thread["vendor_id"],), one=True)
        return {"kind": "vendor", "vendor": vendor}
    if thread["type"] == "teammate":
        return {"kind": "teammate"}
    if thread["type"] == "direct":
        if thread["participant_b_id"]:
            other_id = (
                thread["participant_b_id"] if thread["participant_a_id"] == viewer["id"]
                else thread["participant_a_id"]
            )
            other = dbm.query("SELECT * FROM users WHERE id=?", (other_id,), one=True)
            return {"kind": "direct", "other_user": other}
        return {
            "kind": "pending_email",
            "external_name": thread["external_name"],
            "external_email": thread["external_email"],
            "email_sent": bool(thread["pending_email_sent_at"]),
        }
    return {"kind": "unknown"}


def visible_thread_ids(user):
    """Every thread id this user is a party to, across all thread
    shapes -- used to compute the unread-messages badge."""
    ids = []
    if user["role"] == "seller":
        vendor = seller_vendor(user)
        if vendor:
            ids += [r["id"] for r in dbm.query(
                "SELECT id FROM threads WHERE type='vendor' AND vendor_id=?", (vendor["id"],)
            )]
    else:
        ids += [r["id"] for r in dbm.query(
            "SELECT id FROM threads WHERE type='vendor' AND buyer_user_id=?", (user["id"],)
        )]
        ids += [r["id"] for r in dbm.query(
            "SELECT id FROM threads WHERE type='teammate' AND subject LIKE ?",
            (f"%{user['company']}%",),
        )]
    ids += [r["id"] for r in dbm.query(
        "SELECT id FROM threads WHERE type='direct' AND (participant_a_id=? OR participant_b_id=?)",
        (user["id"], user["id"]),
    )]
    return ids


def unread_count_for(user):
    # Compares message ids rather than timestamps: this app's timestamps
    # only have one-second resolution, so a message posted in the same
    # second as a "mark as read" could otherwise tie and be missed.
    ids = visible_thread_ids(user)
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    others_messages = dbm.query(
        f"SELECT thread_id, id FROM messages "
        f"WHERE thread_id IN ({placeholders}) AND sender_user_id != ?",
        list(ids) + [user["id"]],
    )
    if not others_messages:
        return 0
    read_rows = dbm.query(
        f"SELECT thread_id, last_read_message_id FROM thread_reads "
        f"WHERE user_id=? AND thread_id IN ({placeholders})",
        [user["id"]] + list(ids),
    )
    last_read = {r["thread_id"]: r["last_read_message_id"] for r in read_rows}
    unread = set()
    for m in others_messages:
        if m["id"] > last_read.get(m["thread_id"], 0):
            unread.add(m["thread_id"])
    return len(unread)


def mark_thread_read(user_id, thread_id):
    latest = dbm.query(
        "SELECT MAX(id) AS max_id FROM messages WHERE thread_id=?", (thread_id,), one=True
    )
    latest_id = (latest["max_id"] if latest else 0) or 0
    dbm.execute(
        "INSERT INTO thread_reads (user_id, thread_id, last_read_message_id) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, thread_id) DO UPDATE SET last_read_message_id = EXCLUDED.last_read_message_id "
        "RETURNING user_id",
        (user_id, thread_id, latest_id),
    )


def _thread_route_for(user):
    return "buyer_thread" if user["role"] == "buyer" else "seller_thread"


@app.route("/app/messages/new")
@login_required
def messages_new():
    if g.user["role"] not in ("buyer", "seller"):
        abort(404)
    q = request.args.get("q", "").strip()
    to_id = request.args.get("to", type=int)
    to_email = request.args.get("email", "").strip().lower()

    selected = None
    if to_id:
        candidate = dbm.query("SELECT * FROM users WHERE id=?", (to_id,), one=True)
        if candidate and _can_message(g.user, candidate):
            selected = {"kind": "user", "user": candidate}
        else:
            flash("You can't start a conversation with that account.", "error")
    elif to_email:
        if "@" not in to_email:
            flash(
                "Texting a phone number isn't supported yet — enter an email address instead.",
                "error",
            )
        else:
            existing = dbm.query("SELECT * FROM users WHERE email=?", (to_email,), one=True)
            if existing:
                if _can_message(g.user, existing):
                    selected = {"kind": "user", "user": existing}
                else:
                    flash("That email belongs to a BuyersForce account you can't message directly.", "error")
            else:
                selected = {"kind": "email", "email": to_email}

    results = search_recipients(g.user, q) if (q and not selected) else []
    return render_template("messages_new.html", q=q, results=results, selected=selected)


@app.route("/app/messages/start", methods=("POST",))
@login_required
def messages_start():
    if g.user["role"] not in ("buyer", "seller"):
        abort(404)
    body = request.form.get("body", "").strip()
    to_id = request.form.get("to_id", type=int)
    to_email = request.form.get("to_email", "").strip().lower()
    thread_endpoint = _thread_route_for(g.user)

    if not body:
        flash("Write a message before sending.", "error")
        return redirect(url_for("messages_new", to=to_id or None, email=to_email or None))

    candidate = None
    if to_id:
        candidate = dbm.query("SELECT * FROM users WHERE id=?", (to_id,), one=True)
    elif to_email:
        candidate = dbm.query("SELECT * FROM users WHERE email=?", (to_email,), one=True)

    if candidate:
        if not _can_message(g.user, candidate):
            abort(400)
        thread = thread_with_user(g.user, candidate)
        ensure_contact(g.user["id"], contact_user_id=candidate["id"])
        ensure_contact(candidate["id"], contact_user_id=g.user["id"])
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], body),
        )
        log_activity(g.user["id"], f"messaged {candidate['name']}")
        return redirect(url_for(thread_endpoint, thread_id=thread["id"]))

    if to_email:
        if "@" not in to_email:
            flash("Texting a phone number isn't supported yet — enter an email address instead.", "error")
            return redirect(url_for("messages_new"))
        thread = get_or_create_external_thread(g.user["id"], to_email)
        ensure_contact(g.user["id"], external_email=to_email)
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], body),
        )
        signup_url = url_for("signup", _external=True)
        sent = emailer.send_message_notification(to_email, g.user, body, signup_url)
        if sent:
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            dbm.execute(
                "UPDATE threads SET pending_email_sent_at=? WHERE id=?", (now_str, thread["id"])
            )
            flash(f"Message sent — we emailed {to_email} since they're not on BuyersForce yet.", "success")
        else:
            flash(
                f"Message saved, but we couldn't email {to_email} — BuyersForce's email "
                f"sending isn't set up yet. Ask Claude to help you finish connecting it.",
                "error",
            )
        log_activity(g.user["id"], f"messaged {to_email} (not yet a member)")
        return redirect(url_for(thread_endpoint, thread_id=thread["id"]))

    abort(400)


# ---------------------------------------------------------------------------
# Support -- available to every signed-in role. Submitting a request opens
# (or reuses) a direct message thread with the BuyersForce admin account, so
# the whole back-and-forth lives in the same Messages system everyone
# already uses -- there's no separate support inbox to check.
# ---------------------------------------------------------------------------

@app.route("/app/support", methods=("GET", "POST"))
@login_required
def support_new():
    if request.method == "POST":
        category = request.form.get("category", "")
        notes = request.form.get("notes", "").strip()
        valid_categories = {key for key, _label in SUPPORT_CATEGORIES}
        if category not in valid_categories:
            flash("Choose a category for your request.", "error")
            return redirect(url_for("support_new"))
        if not notes:
            flash("Add a few details before sending your request.", "error")
            return redirect(url_for("support_new"))

        admin = get_admin_user()
        if not admin:
            flash("Support isn't set up yet — there's no BuyersForce admin account to reach.", "error")
            return redirect(url_for("support_new"))

        label = SUPPORT_CATEGORY_LABELS[category]
        thread = get_or_create_direct_thread(g.user["id"], admin["id"])
        ensure_contact(g.user["id"], contact_user_id=admin["id"])
        ensure_contact(admin["id"], contact_user_id=g.user["id"])

        # Auto-captured, not asked for -- gives whoever's troubleshooting a
        # head start on tech-support requests without adding a form field.
        user_agent = request.headers.get("User-Agent", "").strip()
        context_line = f"\n\n— Browser: {user_agent}" if user_agent else ""
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], f"New {label.lower()} request:\n\n{notes}{context_line}"),
        )
        dbm.execute(
            "INSERT INTO support_requests (user_id, category, notes, thread_id) VALUES (?, ?, ?, ?)",
            (g.user["id"], category, notes, thread["id"]),
        )
        log_activity(g.user["id"], f"submitted a support request ({label})")
        flash("Your request has been sent — reply here any time to keep the conversation going.", "success")

        if g.user["role"] == "buyer":
            return redirect(url_for("buyer_thread", thread_id=thread["id"]))
        if g.user["role"] == "seller":
            return redirect(url_for("seller_thread", thread_id=thread["id"]))
        return redirect(url_for("admin_thread", thread_id=thread["id"]))

    return render_template("support/new.html", categories=SUPPORT_CATEGORIES)


@app.route("/app/support/history")
@login_required
def support_history():
    requests_ = dbm.query(
        "SELECT * FROM support_requests WHERE user_id = ? ORDER BY created_at DESC",
        (g.user["id"],),
    )
    return render_template(
        "support/history.html", requests=requests_, category_labels=SUPPORT_CATEGORY_LABELS
    )


@app.route("/app/admin/support/<int:request_id>/status", methods=("POST",))
@admin_required
def admin_support_status(request_id):
    req = dbm.query("SELECT * FROM support_requests WHERE id=?", (request_id,), one=True)
    if not req:
        abort(404)
    status = request.form.get("status", "")
    if status not in ("open", "in_progress", "resolved"):
        abort(400)
    dbm.execute("UPDATE support_requests SET status=? WHERE id=?", (status, request_id))
    flash("Support request updated.", "success")
    return redirect(request.form.get("next") or url_for("admin_dashboard"))


@app.route("/app/admin/vendor-requests/<int:request_id>/decide", methods=("POST",))
@admin_required
def admin_vendor_request_decide(request_id):
    req = dbm.query("SELECT * FROM vendor_requests WHERE id=? AND status='pending'", (request_id,), one=True)
    if not req:
        abort(404)
    action = request.form.get("action", "")
    if action not in ("approve", "deny"):
        abort(400)

    # Admin can edit any of the submitted fields before deciding -- these
    # are what actually get used below, not the original submission.
    company_name = request.form.get("company_name", "").strip() or req["company_name"]
    website = request.form.get("website", "").strip() or req["website"]
    tagline = request.form.get("tagline", "").strip()
    description = request.form.get("description", "").strip()
    new_segment = _ensure_technology_segment(request.form.get("new_segment", ""))
    segments = _parse_proposed_segments(",".join(request.form.getlist("segments")))
    if new_segment and new_segment not in segments:
        segments.append(new_segment)
    new_category = _ensure_technology_category(request.form.get("new_technology_category", ""))
    technology_categories = _parse_proposed_technology_categories(
        ",".join(request.form.getlist("technology_categories"))
    )
    if new_category and new_category not in technology_categories:
        technology_categories.append(new_category)
    company_size = request.form.get("company_size", "").strip()
    if company_size not in COMPANY_SIZE_BANDS:
        company_size = None
    founded_year = request.form.get("founded_year", "").strip()
    founded_year = int(founded_year) if founded_year.isdigit() else None
    hq_location = request.form.get("hq_location", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_title = request.form.get("contact_title", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()

    if action == "deny":
        denial_note = request.form.get("denial_note", "").strip()
        dbm.execute(
            "UPDATE vendor_requests SET status='denied', denial_note=?, resolved_at=?, resolved_by=? WHERE id=?",
            (denial_note, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), g.user["id"], request_id),
        )
        if req["kind"] in ("buyer_referral", "seller_referral") and req["thread_id"]:
            note = (
                f"Sorry, we received your request to add {req['company_name']} to BuyersForce, "
                f"but we don't have enough information yet. We're reaching out to the company now."
            )
            if denial_note:
                note += f"\n\n{denial_note}"
            dbm.execute(
                "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
                (req["thread_id"], g.user["id"], note),
            )
        elif req["kind"] == "seller_signup" and req["contact_email"]:
            note = (
                f"Sorry, we received your request to add {req['company_name']} to BuyersForce, "
                f"but we don't have enough information yet. Please reply to this email if you'd "
                f"like to speak to a BuyersForce admin."
            )
            if denial_note:
                note += f"\n\n{denial_note}"
            emailer.send_email(
                req["contact_email"], subject=f"Your BuyersForce listing request for {req['company_name']}",
                text=note, reply_to=g.user["email"],
            )
        flash(f"{req['company_name']}'s request denied.", "success")
        return redirect(url_for("admin_dashboard"))

    # action == "approve"
    accent, initials = _derive_vendor_accent_initials(company_name)
    category = " / ".join(technology_categories) if technology_categories else "Uncategorized"
    seller_user_id = None
    created_user_id = None

    if req["kind"] == "seller_signup":
        if dbm.query("SELECT id FROM users WHERE email=?", (contact_email,), one=True):
            flash(
                f"{contact_email} already has a BuyersForce account -- resolve that manually "
                f"before approving this listing.", "error",
            )
            return redirect(url_for("admin_dashboard"))
        created_user_id = dbm.execute(
            "INSERT INTO users (role, name, email, password_hash, company, title, account_status) "
            "VALUES ('seller', ?, ?, ?, ?, ?, 'active')",
            (contact_name, contact_email, generate_password_hash(secrets.token_urlsafe(24)),
             company_name, contact_title),
        )
        seller_user_id = created_user_id

    vendor_id = dbm.execute(
        "INSERT INTO vendors (seller_user_id, company_name, category, tagline, description, website, "
        "accent, initials, company_size, founded_year, hq_location, contact_email, contact_phone, "
        "source, technology_category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cybersecurity')",
        (seller_user_id, company_name, category, tagline, description, website, accent, initials,
         company_size, founded_year, hq_location, contact_email, contact_phone, req["kind"]),
    )
    for seg in dict.fromkeys(segments):
        dbm.execute("INSERT INTO vendor_segments (vendor_id, segment) VALUES (?, ?)", (vendor_id, seg))
    for cat in dict.fromkeys(technology_categories):
        dbm.execute(
            "INSERT INTO vendor_technology_categories (vendor_id, category) VALUES (?, ?)",
            (vendor_id, cat),
        )
    dbm.execute(
        "UPDATE vendor_requests SET status='approved', created_vendor_id=?, created_user_id=?, "
        "resolved_at=?, resolved_by=? WHERE id=?",
        (vendor_id, created_user_id, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), g.user["id"], request_id),
    )

    if req["kind"] in ("buyer_referral", "seller_referral") and req["thread_id"]:
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (req["thread_id"], g.user["id"],
             f"Congratulations! We took your advice and added {company_name} to BuyersForce."),
        )
    elif req["kind"] == "seller_signup" and contact_email:
        invite_id, token = _create_invite(contact_email, "seller", company_name, contact_name, g.user["id"])
        emailer.send_email(
            contact_email,
            subject="Congratulations — you're live on BuyersForce!",
            text=(
                f"Hi {contact_name},\n\nGood news -- {company_name} is now listed on BuyersForce, "
                f"and we've set up your own account so you can manage it.\n\n"
                f"Set your password here to get started: {url_for('accept_invite', token=token, _external=True)}\n\n"
                f"This link expires in 7 days."
            ),
            reply_to=g.user["email"],
        )

    log_activity(g.user["id"], f"approved vendor listing request for {company_name}")
    flash(f"{company_name} is now live on BuyersForce.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/app/admin/messages/<int:thread_id>", methods=("GET", "POST"))
@admin_required
def admin_thread(thread_id):
    thread = _load_thread_for_user(thread_id, g.user)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            dbm.execute(
                "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
                (thread_id, g.user["id"], body),
            )
        return redirect(url_for("admin_thread", thread_id=thread_id))
    messages = dbm.query(
        "SELECT m.*, u.name sender_name, u.role sender_role FROM messages m "
        "JOIN users u ON u.id = m.sender_user_id WHERE thread_id=? ORDER BY m.created_at",
        (thread_id,),
    )
    mark_thread_read(g.user["id"], thread_id)
    info = thread_display_info(thread, g.user)
    support_request = dbm.query(
        "SELECT * FROM support_requests WHERE thread_id = ?", (thread_id,), one=True
    )
    return render_template(
        "admin/thread.html", thread=thread, messages=messages, info=info,
        support_request=support_request, category_labels=SUPPORT_CATEGORY_LABELS,
    )


def vendor_tags(vendor_id):
    rows = dbm.query("SELECT tag FROM vendor_tags WHERE vendor_id = ?", (vendor_id,))
    return [r["tag"] for r in rows]


def vendor_segments(vendor_id):
    rows = dbm.query(
        "SELECT segment FROM vendor_segments WHERE vendor_id = ? ORDER BY segment", (vendor_id,)
    )
    return [r["segment"] for r in rows]


def all_technology_categories():
    """The full, alphabetical "Technology Category" picklist -- every
    value any seller or admin has ever added, starting from the seed set
    migrate.py loads once. Backs every Technology Category checkbox list
    in the app (seller profile, vendor signup, Discover/All Vendors
    filters, admin's request-review form)."""
    rows = dbm.query("SELECT name FROM technology_categories ORDER BY name")
    return [r["name"] for r in rows]


def vendor_technology_categories(vendor_id):
    rows = dbm.query(
        "SELECT category FROM vendor_technology_categories WHERE vendor_id = ? ORDER BY category",
        (vendor_id,),
    )
    return [r["category"] for r in rows]


def all_technology_segments():
    """The full, alphabetical "Sub-Categories / Segments" picklist --
    supersedes the CYBERSECURITY_SEGMENTS constant as the live source of
    truth (that constant is now just migrate.py's one-time seed list)."""
    rows = dbm.query("SELECT name FROM technology_segments ORDER BY name")
    return [r["name"] for r in rows]


def _ensure_technology_category(name):
    """Case-insensitively look up `name` in technology_categories, adding
    it if it's genuinely new. Returns the canonical stored name (existing
    casing wins) so e.g. adding "cybersecurity" when "Cybersecurity"
    already exists reuses it instead of creating a near-duplicate. Returns
    None for a blank name."""
    name = (name or "").strip()
    if not name:
        return None
    existing = dbm.query(
        "SELECT name FROM technology_categories WHERE lower(name) = lower(?)", (name,), one=True
    )
    if existing:
        return existing["name"]
    dbm.execute("INSERT INTO technology_categories (name) VALUES (?)", (name,))
    return name


def _ensure_technology_segment(name):
    """Same as _ensure_technology_category, for technology_segments."""
    name = (name or "").strip()
    if not name:
        return None
    existing = dbm.query(
        "SELECT name FROM technology_segments WHERE lower(name) = lower(?)", (name,), one=True
    )
    if existing:
        return existing["name"]
    dbm.execute("INSERT INTO technology_segments (name) VALUES (?)", (name,))
    return name


def _parse_proposed_technology_categories(raw, known=None):
    known = known if known is not None else all_technology_categories()
    return [c for c in (raw or "").split(",") if c in known]


def _derive_initials(company_name):
    """First letters of the first two words of a company name, upper-cased
    -- the one place this formula lives, so every path that needs a
    fallback/auto initials value (new vendor rows, and a My Company save,
    where it's no longer a seller-editable field) matches exactly instead
    of drifting."""
    return "".join(w[0] for w in company_name.split()[:2]).upper() or "VN"


def _derive_vendor_accent_initials(company_name):
    """Same formula admin_approve_signup already uses for an
    auto-created seller vendor row -- kept here as one place so the
    vendor_requests approval paths (buyer_referral, seller_referral,
    seller_signup) match it exactly instead of drifting."""
    return "#3b82f6", _derive_initials(company_name)


def _parse_proposed_segments(raw, known=None):
    known = known if known is not None else all_technology_segments()
    return [s for s in (raw or "").split(",") if s in known]


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


def vendor_announcements(vendor_id):
    """Marketing posts / industry announcements a seller has added to their
    listing -- most-recent-first. Each row is either kind='link' (a
    hyperlink out to something already live on the vendor's own site) or
    kind='text' (a short blurb written directly here)."""
    return dbm.query(
        "SELECT * FROM vendor_announcements WHERE vendor_id = ? ORDER BY id DESC", (vendor_id,)
    )


def vendor_awards(vendor_id):
    """Same shape as vendor_announcements, for industry awards/recognition."""
    return dbm.query(
        "SELECT * FROM vendor_awards WHERE vendor_id = ? ORDER BY id DESC", (vendor_id,)
    )


def gartner_peer_insights_url(company_name):
    """Best-effort link out to Gartner Peer Insights for a vendor. Gartner's
    own vendor-page URLs (gartner.com/reviews/vendor/<slug>) don't follow a
    guessable slug across 240+ vendor names -- spacing, ampersands, and
    abbreviations all vary -- so rather than hardcode or maintain a mapping,
    this links to a site-scoped web search that reliably surfaces the right
    Peer Insights vendor page as the top result."""
    query = f'site:gartner.com/reviews/vendor "{company_name}"'
    return "https://www.google.com/search?q=" + urlquote(query)


def bump_shortlist_forward(buyer_id, vendor_id, target_status):
    """Advance a shortlist row to target_status, but never move it backward.
    Used by bulk actions (like Compare's "Move to Evaluation") so they can't
    accidentally downgrade a vendor a buyer already pushed further along --
    e.g. one already marked Selected shouldn't get bumped back to Shortlisted."""
    existing = dbm.query(
        "SELECT * FROM shortlist WHERE buyer_user_id=? AND vendor_id=?",
        (buyer_id, vendor_id), one=True,
    )
    target_rank = SHORTLIST_PIPELINE_ORDER.get(target_status, 0)
    if existing:
        current_rank = SHORTLIST_PIPELINE_ORDER.get(existing["status"], 0)
        if current_rank < target_rank:
            dbm.execute("UPDATE shortlist SET status=? WHERE id=?", (target_status, existing["id"]))
    else:
        dbm.execute(
            "INSERT INTO shortlist (buyer_user_id, vendor_id, status) VALUES (?, ?, ?)",
            (buyer_id, vendor_id, target_status),
        )


def shortlist_status(buyer_id, vendor_id):
    row = dbm.query(
        "SELECT status FROM shortlist WHERE buyer_user_id = ? AND vendor_id = ?",
        (buyer_id, vendor_id),
        one=True,
    )
    return row["status"] if row else None


def vendor_rating_summary(vendor_id):
    """Aggregate BF-native crowdsourced ratings for a vendor, split by phase
    (evaluation vs. 90-day production check-in) so a vendor's initial
    reception and how it held up after go-live show as two distinct numbers
    rather than blending together."""
    out = {}
    for phase in RATING_PHASES:
        row = dbm.query(
            "SELECT COUNT(*) n, AVG(overall_score) overall, AVG(product_score) product, "
            "AVG(support_score) support, AVG(sales_score) sales "
            "FROM vendor_ratings WHERE vendor_id=? AND phase=?",
            (vendor_id, phase), one=True,
        )
        out[phase] = {
            "count": row["n"] or 0,
            "overall": round(float(row["overall"]), 1) if row["overall"] is not None else None,
            "product": round(float(row["product"]), 1) if row["product"] is not None else None,
            "support": round(float(row["support"]), 1) if row["support"] is not None else None,
            "sales": round(float(row["sales"]), 1) if row["sales"] is not None else None,
        }
    return out


def my_vendor_ratings(buyer_id, vendor_id):
    """This buyer's own submitted ratings for a vendor, keyed by phase --
    used to show what they already said and let them edit it rather than
    submit a duplicate."""
    rows = dbm.query(
        "SELECT * FROM vendor_ratings WHERE buyer_user_id=? AND vendor_id=?",
        (buyer_id, vendor_id),
    )
    return {r["phase"]: r for r in rows}


def production_checkin_eligible(buyer_id, vendor_id):
    """True once RATING_CHECKIN_DAYS have passed since the buyer marked this
    vendor 'selected'. Computed on the fly (on-page-load) rather than via a
    scheduled reminder -- see the RATING_CHECKIN_DAYS comment above."""
    sl = dbm.query(
        "SELECT selected_at FROM shortlist WHERE buyer_user_id=? AND vendor_id=? AND status='selected'",
        (buyer_id, vendor_id), one=True,
    )
    if not sl or not sl["selected_at"]:
        return False
    try:
        selected_dt = datetime.strptime(str(sl["selected_at"])[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (datetime.utcnow() - selected_dt).days >= RATING_CHECKIN_DAYS


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
        # Counts projects (scorecards), not individual vendor rows within
        # them, so a 3-vendor comparison counts as one team evaluation.
        "evaluations": dbm.query(
            "SELECT COUNT(*) c FROM eval_projects WHERE company=?", (u["company"],), one=True
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
    # 90-day production check-in nudges: no scheduled-job/email infrastructure
    # exists to proactively remind buyers (see RATING_CHECKIN_DAYS comment),
    # so instead this computes on every dashboard visit which "selected"
    # vendors have crossed the check-in window without one yet.
    checkin_cutoff = (datetime.utcnow() - timedelta(days=RATING_CHECKIN_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    checkins_due = dbm.query(
        "SELECT s.vendor_id, v.company_name, v.accent, v.initials FROM shortlist s "
        "JOIN vendors v ON v.id = s.vendor_id "
        "WHERE s.buyer_user_id = ? AND s.status = 'selected' AND s.selected_at IS NOT NULL "
        "AND s.selected_at <= ? AND NOT EXISTS ("
        "  SELECT 1 FROM vendor_ratings r WHERE r.vendor_id = s.vendor_id "
        "  AND r.buyer_user_id = s.buyer_user_id AND r.phase = 'production'"
        ") ORDER BY s.selected_at ASC",
        (u["id"], checkin_cutoff),
    )
    return render_template(
        "buyer/dashboard.html",
        counts=counts,
        shortlisted=shortlisted,
        recent_activity=recent_activity,
        upcoming_meetings=upcoming_meetings,
        checkins_due=checkins_due,
        rating_checkin_days=RATING_CHECKIN_DAYS,
    )


@app.route("/app/buyer/discover")
@role_required("buyer")
def buyer_discover():
    q = request.args.get("q", "").strip()
    known_segments = all_technology_segments()
    segments = [s for s in request.args.getlist("segment") if s in known_segments]
    company_size = request.args.get("company_size", "")
    known_categories = all_technology_categories()
    technology_categories = [
        c for c in request.args.getlist("technology_category") if c in known_categories
    ]
    sql = "SELECT * FROM vendors WHERE 1=1"
    args = []
    if technology_categories:
        placeholders = ",".join(["?"] * len(technology_categories))
        sql += (
            f" AND id IN (SELECT vendor_id FROM vendor_technology_categories WHERE category IN ({placeholders}))"
        )
        args += technology_categories
    if q:
        # ILIKE, not LIKE -- LIKE is case-sensitive in Postgres, so a lowercase
        # search like "tines" would never match a stored "Tines".
        sql += (
            " AND (company_name ILIKE ? OR tagline ILIKE ? OR description ILIKE ? "
            "OR hq_location ILIKE ?)"
        )
        args += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
    if segments:
        placeholders = ",".join(["?"] * len(segments))
        sql += (
            f" AND id IN (SELECT vendor_id FROM vendor_segments WHERE segment IN ({placeholders}))"
        )
        args += segments
    if company_size:
        sql += " AND company_size = ?"
        args.append(company_size)
    letter = request.args.get("letter", "").strip().upper()[:1]
    if letter and letter not in DISCOVER_JUMP_LETTERS:
        letter = ""
    if letter == "#":
        # No leading A-Z letter -- Postgres regex, case-insensitive.
        sql += " AND company_name !~* '^[a-z]'"
    elif letter:
        sql += " AND company_name ILIKE ?"
        args.append(letter + "%")
    sort = request.args.get("sort", "name_asc")
    if sort not in DISCOVER_SORT_KEYS:
        sort = "name_asc"
    if sort in ("size_asc", "size_desc"):
        # COMPANY_SIZE_BANDS is already ordered smallest -> largest; sort by
        # each vendor's position in that list rather than the band text
        # (alphabetically "10000+" comes before "51-200").
        case_when = " ".join(
            f"WHEN company_size = ? THEN {idx}" for idx, _band in enumerate(COMPANY_SIZE_BANDS)
        )
        size_rank = f"CASE {case_when} ELSE {len(COMPANY_SIZE_BANDS)} END"
        sql += f" ORDER BY {size_rank} {'DESC' if sort == 'size_desc' else 'ASC'}, company_name"
        args += list(COMPANY_SIZE_BANDS)
    elif sort in ("founded_asc", "founded_desc"):
        direction = "DESC" if sort == "founded_desc" else "ASC"
        sql += f" ORDER BY founded_year IS NULL, founded_year {direction}, company_name"
    else:
        sql += f" ORDER BY company_name {'DESC' if sort == 'name_desc' else 'ASC'}"
    vendors = dbm.query(sql, args)
    vendor_data = []
    for v in vendors:
        vendor_data.append({
            **dict(v),
            "tags": vendor_tags(v["id"]),
            "segments": vendor_segments(v["id"]),
            "logo_url": vendor_display_logo_url(v),
            "status": shortlist_status(g.user["id"], v["id"]),
        })
    return render_template(
        "buyer/discover.html",
        vendors=vendor_data,
        all_segments=known_segments,
        selected_segments=segments,
        company_sizes=COMPANY_SIZE_BANDS,
        all_technology_categories=known_categories,
        selected_technology_categories=technology_categories,
        q=q,
        company_size=company_size,
        sort_options=DISCOVER_SORT_OPTIONS,
        sort=sort,
        jump_letters=DISCOVER_JUMP_LETTERS,
        letter=letter,
    )


@app.route("/app/buyer/vendors/suggest", methods=("GET", "POST"))
@role_required("buyer")
def suggest_vendor():
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        website = request.form.get("website", "").strip()
        if not company_name or not website:
            flash("Company name and website are required.", "error")
            return redirect(url_for("suggest_vendor"))

        segments = _parse_proposed_segments(",".join(request.form.getlist("segments")))
        company_size = request.form.get("company_size", "").strip()
        if company_size not in COMPANY_SIZE_BANDS:
            company_size = None
        founded_year = request.form.get("founded_year", "").strip()
        founded_year = int(founded_year) if founded_year.isdigit() else None
        hq_location = request.form.get("hq_location", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        notes = request.form.get("notes", "").strip()

        admin = get_admin_user()
        if not admin:
            flash("Vendor suggestions aren't set up yet — there's no BuyersForce admin account to reach.", "error")
            return redirect(url_for("suggest_vendor"))

        thread = get_or_create_direct_thread(g.user["id"], admin["id"])
        ensure_contact(g.user["id"], contact_user_id=admin["id"])
        ensure_contact(admin["id"], contact_user_id=g.user["id"])

        summary_lines = [f"New vendor suggestion: {company_name} ({website})"]
        if segments:
            summary_lines.append(f"Segments: {', '.join(segments)}")
        if company_size:
            summary_lines.append(f"Company size: {company_size}")
        if founded_year:
            summary_lines.append(f"Founded: {founded_year}")
        if hq_location:
            summary_lines.append(f"HQ: {hq_location}")
        if contact_name or contact_email or contact_phone:
            summary_lines.append(
                f"Contact: {contact_name or '—'} · {contact_email or '—'} · {contact_phone or '—'}"
            )
        if notes:
            summary_lines.append(f"Notes: {notes}")
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], "\n".join(summary_lines)),
        )

        dbm.execute(
            "INSERT INTO vendor_requests (kind, requested_by_user_id, company_name, website, "
            "proposed_segments, company_size, founded_year, hq_location, contact_name, "
            "contact_email, contact_phone, notes, thread_id) "
            "VALUES ('buyer_referral', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], company_name, website, ",".join(segments), company_size, founded_year,
             hq_location, contact_name, contact_email, contact_phone, notes, thread["id"]),
        )
        log_activity(g.user["id"], f"suggested a vendor ({company_name})")
        flash("Thank you! You'll be contacted by a BuyersForce admin shortly.", "success")
        return redirect(url_for("buyer_thread", thread_id=thread["id"]))

    return render_template(
        "buyer/suggest_vendor.html", all_segments=all_technology_segments(), company_sizes=COMPANY_SIZE_BANDS,
    )


@app.route("/app/buyer/vendor/<int:vendor_id>")
@role_required("buyer")
def buyer_vendor(vendor_id):
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    listings = vendor_listings(vendor_id)
    tags = vendor_tags(vendor_id)
    segments = vendor_segments(vendor_id)
    announcements = vendor_announcements(vendor_id)
    awards = vendor_awards(vendor_id)
    logo_url = vendor_display_logo_url(vendor)
    is_claimed = vendor["seller_user_id"] is not None
    status = shortlist_status(g.user["id"], vendor_id)
    templates_ = dbm.query(
        "SELECT * FROM eval_templates WHERE company=? OR is_shared=1 ORDER BY created_at DESC",
        (g.user["company"],),
    )
    existing_eval = dbm.query(
        "SELECT * FROM evaluations WHERE vendor_id=? AND company=? ORDER BY created_at DESC LIMIT 1",
        (vendor_id, g.user["company"]), one=True
    )
    rating_summary = vendor_rating_summary(vendor_id)
    my_ratings = my_vendor_ratings(g.user["id"], vendor_id)
    can_rate_evaluation = status in ("evaluating", "shortlisted", "selected")
    can_rate_production = "production" in my_ratings or production_checkin_eligible(g.user["id"], vendor_id)
    return render_template(
        "buyer/vendor.html", vendor=vendor, listings=listings, tags=tags, segments=segments,
        announcements=announcements, awards=awards,
        logo_url=logo_url, is_claimed=is_claimed, status=status,
        templates=templates_, existing_eval=existing_eval,
        rating_summary=rating_summary, my_ratings=my_ratings,
        can_rate_evaluation=can_rate_evaluation, can_rate_production=can_rate_production,
    )


@app.route("/app/buyer/vendor/<int:vendor_id>/rate/<phase>", methods=("GET", "POST"))
@role_required("buyer")
def buyer_rate_vendor(vendor_id, phase):
    if phase not in RATING_PHASES:
        abort(404)
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    status = shortlist_status(g.user["id"], vendor_id)
    existing = dbm.query(
        "SELECT * FROM vendor_ratings WHERE buyer_user_id=? AND vendor_id=? AND phase=?",
        (g.user["id"], vendor_id, phase), one=True,
    )
    if phase == "evaluation" and status not in ("evaluating", "shortlisted", "selected"):
        flash("Mark this vendor as evaluating or shortlisted first, then you can rate it.", "error")
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))
    if phase == "production" and not existing and not production_checkin_eligible(g.user["id"], vendor_id):
        flash(
            f"The 90-day check-in opens once it's been {RATING_CHECKIN_DAYS} days "
            "since you marked this vendor Selected.", "error",
        )
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))

    if request.method == "POST":
        try:
            scores = {
                "overall_score": int(request.form.get("overall_score", "")),
                "product_score": int(request.form.get("product_score", "")),
                "support_score": int(request.form.get("support_score", "")),
                "sales_score": int(request.form.get("sales_score", "")),
            }
            if not all(1 <= v <= 10 for v in scores.values()):
                raise ValueError
        except ValueError:
            flash("Please give every question a rating from 1-10.", "error")
            return redirect(url_for("buyer_rate_vendor", vendor_id=vendor_id, phase=phase))
        comment = request.form.get("comment", "").strip()
        dbm.execute(
            "INSERT INTO vendor_ratings "
            "(vendor_id, buyer_user_id, company, phase, overall_score, product_score, "
            "support_score, sales_score, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (vendor_id, buyer_user_id, phase) DO UPDATE SET "
            "overall_score=EXCLUDED.overall_score, product_score=EXCLUDED.product_score, "
            "support_score=EXCLUDED.support_score, sales_score=EXCLUDED.sales_score, "
            "comment=EXCLUDED.comment",
            (
                vendor_id, g.user["id"], g.user["company"], phase,
                scores["overall_score"], scores["product_score"],
                scores["support_score"], scores["sales_score"], comment,
            ),
        )
        log_activity(g.user["id"], f"rated {vendor['company_name']} ({RATING_PHASE_LABELS[phase]})")
        flash(f"Thanks -- your {RATING_PHASE_LABELS[phase].lower()} rating for {vendor['company_name']} is in.", "success")
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))

    return render_template(
        "buyer/rate_vendor.html", vendor=vendor, phase=phase,
        phase_label=RATING_PHASE_LABELS[phase], questions=RATING_PHASE_QUESTIONS[phase],
        dimensions=RATING_DIMENSIONS, existing=existing,
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
        if new_status == "selected":
            # COALESCE so re-selecting a vendor later doesn't reset the
            # original "went live" timestamp the 90-day check-in is anchored to.
            dbm.execute(
                "UPDATE shortlist SET status=?, "
                "selected_at=COALESCE(selected_at, to_char(now(), 'YYYY-MM-DD HH24:MI:SS')) "
                "WHERE id=?",
                (new_status, existing["id"]),
            )
        else:
            dbm.execute(
                "UPDATE shortlist SET status=? WHERE id=?", (new_status, existing["id"])
            )
    else:
        if new_status == "selected":
            dbm.execute(
                "INSERT INTO shortlist (buyer_user_id, vendor_id, status, selected_at) "
                "VALUES (?, ?, ?, to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))",
                (g.user["id"], vendor_id, new_status),
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
    # Discover's checkboxes are all named "ids" and a GET form submits
    # repeated same-name checkboxes as separate query params (?ids=5&ids=12),
    # NOT a single comma-joined value -- request.args.get("ids") would silently
    # grab only the first one. getlist() picks up every checked vendor; the
    # inner split(",") also keeps this page's own "Back to discover" style
    # comma-joined reload link (?ids=5,12) working.
    raw_ids = request.args.getlist("ids")
    ids = []
    for raw in raw_ids:
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
    ids = list(dict.fromkeys(ids))[:DISCOVER_COMPARE_MAX]
    vendors = []
    for vid in ids:
        v = dbm.query("SELECT * FROM vendors WHERE id=?", (vid,), one=True)
        if v:
            # Most recent evaluation (if any) this buyer's company has for
            # this vendor that has a Gartner Peer Insights note on it, so
            # Compare can surface what the team already found there.
            gartner_eval = dbm.query(
                "SELECT gartner_peer_note FROM evaluations WHERE vendor_id=? AND company=? "
                "AND gartner_peer_note != '' ORDER BY created_at DESC LIMIT 1",
                (vid, g.user["company"]), one=True,
            )
            vendors.append({
                **dict(v),
                "tags": vendor_tags(vid),
                "segments": vendor_segments(vid),
                "listings": vendor_listings(vid),
                "logo_url": vendor_display_logo_url(v),
                "ratings": vendor_rating_summary(vid),
                "gartner_url": gartner_peer_insights_url(v["company_name"]),
                "gartner_note": gartner_eval["gartner_peer_note"] if gartner_eval else "",
            })
    all_vendors = dbm.query("SELECT id, company_name FROM vendors ORDER BY company_name")
    return render_template(
        "buyer/compare.html", vendors=vendors, all_vendors=all_vendors, ids=ids,
        shortlist_move_max=SHORTLIST_MOVE_MAX,
    )


@app.route("/app/buyer/vendors/move-to-evaluation", methods=("POST",))
@role_required("buyer")
def buyer_move_to_evaluation():
    # Bulk action from Compare's "Short List" checkboxes: bump each checked
    # vendor's shortlist status forward (never backward -- see
    # bump_shortlist_forward) and send the buyer to Evaluations, where the
    # new "Ready to evaluate" section lets them pick a scorecard per vendor.
    raw_ids = request.form.getlist("shortlist_ids")
    ids = []
    for part in raw_ids:
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    ids = list(dict.fromkeys(ids))[:SHORTLIST_MOVE_MAX]
    if not ids:
        flash('Check at least one vendor\'s "Short List" box first.', "error")
        return redirect(request.referrer or url_for("buyer_discover"))
    names = []
    for vid in ids:
        vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vid,), one=True)
        if not vendor:
            continue
        bump_shortlist_forward(g.user["id"], vid, "shortlisted")
        log_activity(g.user["id"], f"shortlisted {vendor['company_name']} for evaluation")
        names.append(vendor["company_name"])
    if names:
        flash(f"Moved {', '.join(names)} to Evaluate -- pick a scorecard to get started.", "success")
    return redirect(url_for("buyer_evaluations"))


@app.route("/app/buyer/vendor/<int:vendor_id>/message", methods=("POST",))
@role_required("buyer")
def buyer_message_vendor(vendor_id):
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    if vendor["seller_user_id"] is None:
        flash(
            f"{vendor['company_name']} hasn't claimed their BuyersForce listing yet, "
            "so messaging isn't available for them.",
            "error",
        )
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))
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
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    if vendor["seller_user_id"] is None:
        flash(
            f"{vendor['company_name']} hasn't claimed their BuyersForce listing yet, "
            "so meeting requests aren't available for them.",
            "error",
        )
        return redirect(url_for("buyer_vendor", vendor_id=vendor_id))
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
    direct_threads = _direct_threads_for(u)
    return render_template(
        "buyer/messages.html", vendor_threads=vendor_threads, team_threads=team_threads,
        direct_threads=direct_threads,
    )


def _direct_threads_for(user):
    """1:1 'direct' threads for the inbox list -- teammate DMs, and
    pending conversations with someone who isn't a member yet."""
    rows = dbm.query(
        "SELECT t.*, "
        "(SELECT body FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_body, "
        "(SELECT created_at FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_at "
        "FROM threads t WHERE t.type='direct' AND (t.participant_a_id=? OR t.participant_b_id=?) "
        "ORDER BY last_at DESC",
        (user["id"], user["id"]),
    )
    out = []
    for t in rows:
        info = thread_display_info(t, user)
        out.append({**dict(t), **info})
    return out


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
    elif thread["type"] == "direct":
        if thread["participant_a_id"] != user["id"] and thread["participant_b_id"] != user["id"]:
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
    mark_thread_read(g.user["id"], thread_id)
    info = thread_display_info(thread, g.user)
    return render_template("buyer/thread.html", thread=thread, messages=messages, info=info)


def project_display_name(name, vendor_names):
    """A project's own name if the buyer gave it one, otherwise a name built
    from its vendors ("CrowdStrike vs. SentinelOne vs. Wiz") -- used on the
    Evaluations list, the project scorecard page, and as the live
    suggestion on the "Start project" form (see app.js). Every project
    (including ones backfilled from before projects existed, which are
    always single-vendor) goes through this so a blank name never shows up
    as blank.
    """
    name = (name or "").strip()
    if name:
        return name
    if not vendor_names:
        return "Untitled project"
    return " vs. ".join(vendor_names)


@app.route("/app/buyer/evaluations")
@role_required("buyer")
def buyer_evaluations():
    u = g.user
    templates_ = dbm.query(
        "SELECT * FROM eval_templates WHERE company=? OR is_shared=1 ORDER BY created_at DESC",
        (u["company"],),
    )
    # One project can (and often does) hold several vendors being scored
    # against the same template at once -- see eval_projects in schema.sql.
    # "Active evaluations" below is one card per PROJECT, not per vendor.
    projects = dbm.query(
        "SELECT p.*, t.name template_name FROM eval_projects p "
        "JOIN eval_templates t ON t.id = p.template_id "
        "WHERE p.company=? ORDER BY p.created_at DESC",
        (u["company"],),
    )
    active_data = []
    for p in projects:
        criteria = dbm.query(
            "SELECT * FROM eval_criteria WHERE template_id=? ORDER BY position", (p["template_id"],)
        )
        total_weight = sum(c["weight"] for c in criteria) or 1
        evals = dbm.query(
            "SELECT e.*, v.company_name, v.accent, v.initials, v.wiki_logo_url, v.logo_link_url, v.logo_upload_data_url, v.website "
            "FROM evaluations e JOIN vendors v ON v.id = e.vendor_id "
            "WHERE e.project_id=? ORDER BY e.id",
            (p["id"],),
        )
        if not evals:
            continue
        vendor_summaries = []
        reviewer_ids = set()
        for ev in evals:
            scores = dbm.query("SELECT * FROM eval_scores WHERE evaluation_id=?", (ev["id"],))
            reviewer_ids.update(s["user_id"] for s in scores)
            by_criterion = {}
            for s in scores:
                by_criterion.setdefault(s["criterion_id"], []).append(s["score"])
            weighted_sum = 0
            for c in criteria:
                vals = by_criterion.get(c["id"], [])
                avg = sum(vals) / len(vals) if vals else 0
                weighted_sum += avg * c["weight"]
            overall = round(weighted_sum / total_weight, 1) if scores else None
            vendor_summaries.append({
                "company_name": ev["company_name"], "accent": ev["accent"], "initials": ev["initials"],
                "logo_url": vendor_display_logo_url(ev), "overall": overall,
            })
        active_data.append({
            "id": p["id"],
            "name": project_display_name(p["name"], [v["company_name"] for v in vendor_summaries]),
            "template_name": p["template_name"], "vendors": vendor_summaries,
            "created_at": p["created_at"], "reviewers": len(reviewer_ids),
        })
    # Vendors this buyer has shortlisted/is evaluating that don't have an
    # evaluations row yet -- the bridge from Compare's "Move to Evaluation"
    # (and from manually shortlisting a vendor) into actually starting a
    # scorecard. Once an evaluation exists for a vendor it graduates to
    # "Active evaluations" above and drops out of this list. The buyer
    # picks which of these join one project together (see
    # buyer_start_project) -- e.g. the 3 vendors just moved here from
    # Compare become one shared scorecard instead of 3 separate ones.
    ready = dbm.query(
        "SELECT s.vendor_id, v.company_name, v.accent, v.initials, v.wiki_logo_url, v.logo_link_url, v.logo_upload_data_url, v.website "
        "FROM shortlist s JOIN vendors v ON v.id = s.vendor_id "
        "WHERE s.buyer_user_id=? AND s.status IN ('shortlisted', 'evaluating') "
        "AND s.vendor_id NOT IN (SELECT vendor_id FROM evaluations WHERE company=?) "
        "ORDER BY s.created_at DESC",
        (u["id"], u["company"]),
    )
    ready_data = [
        {**dict(r), "logo_url": vendor_display_logo_url(r)}
        for r in ready
    ]
    return render_template(
        "buyer/evaluations.html", templates=templates_, active=active_data, ready_to_evaluate=ready_data,
    )


# Default is 5 rows client-side, but a buyer can keep clicking
# "+ Add criterion" past that -- this just keeps it from being truly
# unbounded. Weight is a percent of the overall score (must sum to 100).
MAX_EVAL_CRITERIA = 50


@app.route("/app/buyer/evaluations/new", methods=("GET", "POST"))
@role_required("buyer")
def buyer_evaluation_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        labels = request.form.getlist("criterion_label")
        weights = request.form.getlist("criterion_weight")
        filled = [(l.strip(), w) for l, w in zip(labels, weights) if l.strip()]

        error = None
        parsed = []
        if not name or not filled:
            error = "Give your template a name and at least one criterion."
        elif len(filled) > MAX_EVAL_CRITERIA:
            error = f"A template can have at most {MAX_EVAL_CRITERIA} criteria."
        else:
            total = 0
            for label, w in filled:
                try:
                    weight = max(0, int(w))
                except (TypeError, ValueError):
                    weight = 0
                parsed.append((label, weight))
                total += weight
            # Weight is now the % of the overall score each criterion carries
            # (previously a 1-5 multiplier), so the set has to add up to a
            # whole 100 -- otherwise "weighted overall score" on the
            # evaluations list and project_detail.html stops meaning what
            # it says. Enforced here as well as with the live total shown on
            # the form (see app.js) in case a buyer submits before JS runs.
            if total != 100:
                error = f"Criteria weights must add up to 100% -- they currently add up to {total}%."

        if error:
            flash(error, "error")
            return render_template(
                "buyer/evaluation_new.html",
                form_name=name, form_description=description,
                form_rows=list(zip(labels, weights)) or [("", "")],
                max_criteria=MAX_EVAL_CRITERIA,
            )

        template_id = dbm.execute(
            "INSERT INTO eval_templates (owner_user_id, company, name, description, is_shared) "
            "VALUES (?, ?, ?, ?, 1)",
            (g.user["id"], g.user["company"], name, description),
        )
        for pos, (label, weight) in enumerate(parsed):
            dbm.execute(
                "INSERT INTO eval_criteria (template_id, label, weight, position) "
                "VALUES (?, ?, ?, ?)",
                (template_id, label, weight, pos),
            )
        flash("Evaluation template created and shared with your team.", "success")
        return redirect(url_for("buyer_evaluations"))
    return render_template(
        "buyer/evaluation_new.html",
        form_name="", form_description="",
        form_rows=[("", 20)] * 5,
        max_criteria=MAX_EVAL_CRITERIA,
    )


@app.route("/app/buyer/evaluations/start-project", methods=("POST",))
@role_required("buyer")
def buyer_start_project():
    # Handles two entry points with one route: the single-vendor "Start
    # evaluation" button on a vendor's own profile page (vendor.html posts
    # one vendor_id), and the "Ready to evaluate" multi-select form on the
    # Evaluations tab (evaluations.html posts several, all sharing one
    # template + one project name) -- see MAX_EVAL_CRITERIA's neighbor
    # comment style for why this stays one route instead of two near-
    # identical ones.
    seen = set()
    vendor_ids = []
    for v in request.form.getlist("vendor_ids"):
        try:
            vid = int(v)
        except (TypeError, ValueError):
            continue
        if vid not in seen:
            seen.add(vid)
            vendor_ids.append(vid)
    template_id = request.form.get("template_id")
    name = request.form.get("name", "").strip()

    fallback = request.referrer or url_for("buyer_evaluations")
    if not vendor_ids:
        flash("Choose at least one vendor to evaluate.", "error")
        return redirect(fallback)
    if not template_id:
        flash("Choose an evaluation template first.", "error")
        return redirect(fallback)

    # Re-starting an evaluation for a single vendor already being evaluated
    # against this exact template (e.g. clicking "Continue evaluation"
    # again from that vendor's profile) reopens that project instead of
    # spinning up a duplicate -- matches the old single-vendor behavior. A
    # multi-vendor batch from "Ready to evaluate" always starts a fresh
    # project, even if one vendor happens to overlap with a past one,
    # since that's a deliberate new round of comparison.
    if len(vendor_ids) == 1:
        existing = dbm.query(
            "SELECT * FROM evaluations WHERE template_id=? AND vendor_id=? AND company=?",
            (template_id, vendor_ids[0], g.user["company"]), one=True,
        )
        if existing:
            return redirect(url_for("buyer_project_detail", project_id=existing["project_id"]))

    project_id = dbm.execute(
        "INSERT INTO eval_projects (template_id, company, name, created_by) VALUES (?, ?, ?, ?)",
        (template_id, g.user["company"], name, g.user["id"]),
    )
    vendor_names = []
    for vendor_id in vendor_ids:
        dbm.execute(
            "INSERT INTO evaluations (template_id, vendor_id, company, created_by, project_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (template_id, vendor_id, g.user["company"], g.user["id"], project_id),
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
        if vendor:
            vendor_names.append(vendor["company_name"])
    if len(vendor_names) == 1:
        log_activity(g.user["id"], f"started an evaluation for {vendor_names[0]}")
    else:
        log_activity(g.user["id"], f"started an evaluation project for {', '.join(vendor_names)}")
    return redirect(url_for("buyer_project_detail", project_id=project_id))


@app.route("/app/buyer/evaluations/project/<int:project_id>", methods=("GET", "POST"))
@role_required("buyer")
def buyer_project_detail(project_id):
    project = dbm.query("SELECT * FROM eval_projects WHERE id=?", (project_id,), one=True)
    if not project or project["company"] != g.user["company"]:
        abort(404)
    template = dbm.query("SELECT * FROM eval_templates WHERE id=?", (project["template_id"],), one=True)
    criteria = dbm.query(
        "SELECT * FROM eval_criteria WHERE template_id=? ORDER BY position", (project["template_id"],)
    )
    evals = dbm.query(
        "SELECT e.*, v.company_name, v.accent, v.initials, v.wiki_logo_url, v.logo_link_url, v.logo_upload_data_url, v.website "
        "FROM evaluations e JOIN vendors v ON v.id = e.vendor_id "
        "WHERE e.project_id=? ORDER BY e.id",
        (project_id,),
    )
    if not evals:
        abort(404)

    if request.method == "POST":
        # Every criterion x vendor cell in the grid is its own score/comment
        # field, keyed by that vendor's evaluation id so scoring one
        # vendor's "Ease of integration" never collides with another's --
        # see the criterion-cell markup in project_detail.html.
        for ev in evals:
            for c in criteria:
                score = request.form.get(f"score_{ev['id']}_{c['id']}")
                comment = request.form.get(f"comment_{ev['id']}_{c['id']}", "").strip()
                if score:
                    dbm.execute(
                        "INSERT INTO eval_scores (evaluation_id, criterion_id, user_id, score, comment) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(evaluation_id, criterion_id, user_id) "
                        "DO UPDATE SET score=excluded.score, comment=excluded.comment",
                        (ev["id"], c["id"], g.user["id"], int(score), comment),
                    )
            # Free-text space for whatever the team found on Gartner Peer
            # Insights, per vendor -- BF doesn't pull real review data from
            # Gartner, this is just a manually-typed reference note.
            gartner_peer_note = request.form.get(f"gartner_peer_note_{ev['id']}", "").strip()
            dbm.execute(
                "UPDATE evaluations SET gartner_peer_note=? WHERE id=?", (gartner_peer_note, ev["id"])
            )
        log_activity(
            g.user["id"],
            f"submitted scores for {', '.join(ev['company_name'] for ev in evals)}",
        )
        flash("Your scores were saved.", "success")
        return redirect(url_for("buyer_project_detail", project_id=project_id))

    reviewers = {r["id"]: r for r in dbm.query(
        "SELECT * FROM users WHERE company=? AND role='buyer'", (g.user["company"],)
    )}
    total_weight = sum(c["weight"] for c in criteria) or 1

    vendor_columns = []
    for ev in evals:
        scores = dbm.query("SELECT * FROM eval_scores WHERE evaluation_id=?", (ev["id"],))
        my_scores = {s["criterion_id"]: s for s in scores if s["user_id"] == g.user["id"]}
        weighted_sum = 0
        cells = {}
        for c in criteria:
            vals = [s["score"] for s in scores if s["criterion_id"] == c["id"]]
            avg = round(sum(vals) / len(vals), 1) if vals else None
            weighted_sum += (avg or 0) * c["weight"]
            cells[c["id"]] = {"avg": avg, "count": len(vals), "my_score": my_scores.get(c["id"])}
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

        vendor_columns.append({
            "evaluation_id": ev["id"], "vendor_id": ev["vendor_id"],
            "company_name": ev["company_name"], "accent": ev["accent"], "initials": ev["initials"],
            "logo_url": vendor_display_logo_url(ev),
            "website": ev["website"],
            "gartner_peer_note": ev["gartner_peer_note"],
            "gartner_url": gartner_peer_insights_url(ev["company_name"]),
            "overall": overall, "reviewer_rows": reviewer_rows, "cells": cells,
        })

    project_name = project_display_name(project["name"], [v["company_name"] for v in vendor_columns])
    return render_template(
        "buyer/project_detail.html",
        project=project, project_name=project_name, template=template,
        criteria=criteria, vendors=vendor_columns,
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
        "SELECT s.*, u.name buyer_name, u.company buyer_company, u.photo_data_url buyer_photo "
        "FROM shortlist s "
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
        files = request.files

        # Logo: an uploaded file wins if one was chosen this save; otherwise
        # the existing upload (if any) is left alone. "Remove current logo"
        # clears both the upload and the link, falling back through the
        # rest of vendor_display_logo_url's chain (wiki logo, favicon,
        # initials). Validated/rejected before anything else is saved, same
        # as the account-photo upload this mirrors.
        logo_data_url, logo_error = _read_uploaded_vendor_logo(files)
        if logo_error:
            flash(logo_error, "error")
            return redirect(url_for("seller_profile"))
        remove_logo = form.get("remove_logo") == "on"
        if remove_logo:
            new_logo_link_url = ""
            new_logo_upload_data_url = None
        else:
            new_logo_link_url = form.get("logo_link_url", "").strip()
            new_logo_upload_data_url = logo_data_url if logo_data_url else vendor["logo_upload_data_url"]

        founded_year = form.get("founded_year", "").strip()
        founded_year = int(founded_year) if founded_year.isdigit() else None
        company_size = form.get("company_size", "").strip()
        if company_size not in COMPANY_SIZE_BANDS:
            company_size = None

        new_category = _ensure_technology_category(form.get("new_technology_category", ""))
        technology_categories = [
            c for c in form.getlist("technology_categories") if c in all_technology_categories()
        ]
        if new_category and new_category not in technology_categories:
            technology_categories.append(new_category)
        # `category` (a single display label shown on vendor cards, the
        # compare table, etc.) is no longer directly editable -- it's
        # derived from the seller's selected Technology Categories so
        # those older, single-value display sites keep showing something
        # sensible without needing their own multi-category redesign.
        category = " / ".join(technology_categories) if technology_categories else "Uncategorized"

        new_segment = _ensure_technology_segment(form.get("new_segment", ""))
        segments = [s for s in form.getlist("segments") if s in all_technology_segments()]
        if new_segment and new_segment not in segments:
            segments.append(new_segment)

        # Initials are no longer a seller-editable field (removed per
        # Kevin's request, alongside adding the logo above) -- auto-derived
        # from the company name instead, same formula every other vendor
        # row uses (_derive_vendor_accent_initials).
        initials = _derive_initials(form["company_name"].strip())

        # A seller can type just the bare domain ("acme.com") -- the field
        # is plain text now, not type="url", specifically so that isn't
        # rejected by browser URL validation. Default the scheme to https://
        # so the stored value is still a real, clickable URL everywhere else
        # it's used (buyer/vendor.html's website link, etc.); a seller who
        # explicitly types http:// gets to keep that instead.
        website = form.get("website", "").strip()
        if website and not re.match(r"^https?://", website, re.IGNORECASE):
            website = "https://" + website

        # Same phone_country pattern as account_profile()'s phone fields --
        # see PHONE_COUNTRIES / static/js/phone-format.js. Defaults to US.
        contact_phone_country = (form.get("contact_phone_country", "US").strip().upper() or "US")[:2]

        dbm.execute(
            # accent is no longer an editable field on this form (removed
            # per Kevin's request) -- deliberately left out of this UPDATE
            # so a save never overwrites the vendor's existing accent color.
            "UPDATE vendors SET company_name=?, category=?, tagline=?, description=?, "
            "website=?, initials=?, logo_link_url=?, logo_upload_data_url=?, company_size=?, "
            "founded_year=?, hq_location=?, contact_email=?, contact_phone=?, "
            "contact_phone_country=? WHERE id=?",
            (
                form["company_name"].strip(), category, form["tagline"].strip(),
                form["description"].strip(), website,
                initials, new_logo_link_url, new_logo_upload_data_url, company_size, founded_year,
                form.get("hq_location", "").strip(), form.get("contact_email", "").strip(),
                form.get("contact_phone", "").strip(), contact_phone_country, vendor["id"],
            ),
        )
        dbm.execute("DELETE FROM vendor_tags WHERE vendor_id=?", (vendor["id"],))
        for tag in form.get("tags", "").split(","):
            tag = tag.strip()
            if tag:
                dbm.execute(
                    "INSERT INTO vendor_tags (vendor_id, tag) VALUES (?, ?)", (vendor["id"], tag)
                )
        dbm.execute("DELETE FROM vendor_segments WHERE vendor_id=?", (vendor["id"],))
        for segment in dict.fromkeys(segments):
            dbm.execute(
                "INSERT INTO vendor_segments (vendor_id, segment) VALUES (?, ?)",
                (vendor["id"], segment),
            )
        dbm.execute("DELETE FROM vendor_technology_categories WHERE vendor_id=?", (vendor["id"],))
        for cat in dict.fromkeys(technology_categories):
            dbm.execute(
                "INSERT INTO vendor_technology_categories (vendor_id, category) VALUES (?, ?)",
                (vendor["id"], cat),
            )
        flash("Your company profile updated — buyers will see the latest version.", "success")
        return redirect(url_for("seller_profile"))
    tags = ", ".join(vendor_tags(vendor["id"]))
    selected_segments = vendor_segments(vendor["id"])
    selected_technology_categories = vendor_technology_categories(vendor["id"])
    listings = vendor_listings(vendor["id"])
    announcements = vendor_announcements(vendor["id"])
    awards = vendor_awards(vendor["id"])
    return render_template(
        "seller/profile.html", vendor=vendor, tags=tags, listings=listings,
        all_segments=all_technology_segments(), selected_segments=selected_segments,
        all_technology_categories=all_technology_categories(),
        selected_technology_categories=selected_technology_categories,
        company_sizes=COMPANY_SIZE_BANDS,
        announcements=announcements, awards=awards,
        logo_url=vendor_display_logo_url(vendor),
        phone_countries=PHONE_COUNTRIES,
    )


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
        flash("Product listing added to your company profile.", "success")
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


def _validate_announcement_or_award_form(form):
    """Shared validation for the "add" forms on both My Company sections
    (Marketing Posts/Announcements and Awards/Recognition) -- same shape,
    just filed into different tables. No explicit Link/Write-up choice --
    "kind" is inferred from whichever of url/body the seller filled in, so
    the form is just a title plus one of two optional fields (fill in a
    link, or write a blurb). Returns (kind, title, url, body, error);
    error is None on success."""
    title = form.get("title", "").strip()
    url = form.get("url", "").strip()
    body = form.get("body", "").strip()
    if not title:
        return None, title, url, body, "Give it a title."
    if url:
        return "link", title, url, "", None
    if body:
        return "text", title, "", body, None
    return None, title, url, body, "Add a link or a short write-up."


@app.route("/app/seller/announcements/new", methods=("POST",))
@role_required("seller")
def seller_announcement_new():
    vendor = seller_vendor(g.user)
    kind, title, url, body, error = _validate_announcement_or_award_form(request.form)
    if error:
        flash(error, "error")
    else:
        dbm.execute(
            "INSERT INTO vendor_announcements (vendor_id, kind, title, url, body) VALUES (?, ?, ?, ?, ?)",
            (vendor["id"], kind, title, url, body),
        )
        flash("Added to Marketing Posts & Announcements.", "success")
    return redirect(url_for("seller_profile"))


@app.route("/app/seller/announcements/<int:announcement_id>/delete", methods=("POST",))
@role_required("seller")
def seller_announcement_delete(announcement_id):
    vendor = seller_vendor(g.user)
    row = dbm.query(
        "SELECT * FROM vendor_announcements WHERE id=? AND vendor_id=?",
        (announcement_id, vendor["id"]), one=True,
    )
    if row:
        dbm.execute("DELETE FROM vendor_announcements WHERE id=?", (announcement_id,))
        flash("Removed.", "success")
    return redirect(url_for("seller_profile"))


@app.route("/app/seller/awards/new", methods=("POST",))
@role_required("seller")
def seller_award_new():
    vendor = seller_vendor(g.user)
    kind, title, url, body, error = _validate_announcement_or_award_form(request.form)
    if error:
        flash(error, "error")
    else:
        dbm.execute(
            "INSERT INTO vendor_awards (vendor_id, kind, title, url, body) VALUES (?, ?, ?, ?, ?)",
            (vendor["id"], kind, title, url, body),
        )
        flash("Added to Awards & Recognition.", "success")
    return redirect(url_for("seller_profile"))


@app.route("/app/seller/awards/<int:award_id>/delete", methods=("POST",))
@role_required("seller")
def seller_award_delete(award_id):
    vendor = seller_vendor(g.user)
    row = dbm.query(
        "SELECT * FROM vendor_awards WHERE id=? AND vendor_id=?", (award_id, vendor["id"]), one=True,
    )
    if row:
        dbm.execute("DELETE FROM vendor_awards WHERE id=?", (award_id,))
        flash("Removed.", "success")
    return redirect(url_for("seller_profile"))


# Sellers can see the same vendor directory buyers browse on Discover --
# vendor "About" info (name, tagline, description, segments) is already
# public-style content any BuyersForce user can see elsewhere (e.g. LinkedIn
# company pages), so there's no reason to hide the competitive landscape
# from sellers. What sellers do NOT get here: BuyersForce ratings, products &
# pricing, or any "take action" buyer tooling (shortlist/evaluate/message) --
# those stay buyer-only. This mirrors buyer_discover's query shape rather
# than sharing code with it, matching how buyer/seller features are kept as
# separate routes+templates throughout this app.
@app.route("/app/seller/vendors")
@role_required("seller")
def seller_all_vendors():
    q = request.args.get("q", "").strip()
    known_segments = all_technology_segments()
    segments = [s for s in request.args.getlist("segment") if s in known_segments]
    company_size = request.args.get("company_size", "")
    known_categories = all_technology_categories()
    technology_categories = [
        c for c in request.args.getlist("technology_category") if c in known_categories
    ]
    sql = "SELECT * FROM vendors WHERE 1=1"
    args = []
    if technology_categories:
        placeholders = ",".join(["?"] * len(technology_categories))
        sql += (
            f" AND id IN (SELECT vendor_id FROM vendor_technology_categories WHERE category IN ({placeholders}))"
        )
        args += technology_categories
    if q:
        # ILIKE, not LIKE -- LIKE is case-sensitive in Postgres, so a lowercase
        # search like "tines" would never match a stored "Tines".
        sql += (
            " AND (company_name ILIKE ? OR tagline ILIKE ? OR description ILIKE ? "
            "OR hq_location ILIKE ?)"
        )
        args += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
    if segments:
        placeholders = ",".join(["?"] * len(segments))
        sql += (
            f" AND id IN (SELECT vendor_id FROM vendor_segments WHERE segment IN ({placeholders}))"
        )
        args += segments
    if company_size:
        sql += " AND company_size = ?"
        args.append(company_size)
    letter = request.args.get("letter", "").strip().upper()[:1]
    if letter and letter not in DISCOVER_JUMP_LETTERS:
        letter = ""
    if letter == "#":
        # No leading A-Z letter -- Postgres regex, case-insensitive.
        sql += " AND company_name !~* '^[a-z]'"
    elif letter:
        sql += " AND company_name ILIKE ?"
        args.append(letter + "%")
    sort = request.args.get("sort", "name_asc")
    if sort not in DISCOVER_SORT_KEYS:
        sort = "name_asc"
    if sort in ("size_asc", "size_desc"):
        case_when = " ".join(
            f"WHEN company_size = ? THEN {idx}" for idx, _band in enumerate(COMPANY_SIZE_BANDS)
        )
        size_rank = f"CASE {case_when} ELSE {len(COMPANY_SIZE_BANDS)} END"
        sql += f" ORDER BY {size_rank} {'DESC' if sort == 'size_desc' else 'ASC'}, company_name"
        args += list(COMPANY_SIZE_BANDS)
    elif sort in ("founded_asc", "founded_desc"):
        direction = "DESC" if sort == "founded_desc" else "ASC"
        sql += f" ORDER BY founded_year IS NULL, founded_year {direction}, company_name"
    else:
        sql += f" ORDER BY company_name {'DESC' if sort == 'name_desc' else 'ASC'}"
    vendors = dbm.query(sql, args)
    vendor_data = []
    for v in vendors:
        vendor_data.append({
            **dict(v),
            "tags": vendor_tags(v["id"]),
            "segments": vendor_segments(v["id"]),
            "logo_url": vendor_display_logo_url(v),
        })
    return render_template(
        "seller/all_vendors.html",
        vendors=vendor_data,
        all_segments=known_segments,
        selected_segments=segments,
        company_sizes=COMPANY_SIZE_BANDS,
        all_technology_categories=known_categories,
        selected_technology_categories=technology_categories,
        q=q,
        company_size=company_size,
        sort_options=DISCOVER_SORT_OPTIONS,
        sort=sort,
        jump_letters=DISCOVER_JUMP_LETTERS,
        letter=letter,
    )


@app.route("/app/seller/vendors/<int:vendor_id>")
@role_required("seller")
def seller_view_vendor(vendor_id):
    vendor = dbm.query("SELECT * FROM vendors WHERE id=?", (vendor_id,), one=True)
    if not vendor:
        abort(404)
    tags = vendor_tags(vendor_id)
    segments = vendor_segments(vendor_id)
    announcements = vendor_announcements(vendor_id)
    awards = vendor_awards(vendor_id)
    logo_url = vendor_display_logo_url(vendor)
    return render_template(
        "seller/vendor_view.html", vendor=vendor, tags=tags, segments=segments, logo_url=logo_url,
        announcements=announcements, awards=awards,
    )


# A seller (already listed themselves) can flag a competitor that's
# missing from the directory -- same idea as buyer_discover's "suggest a
# vendor", just filed under its own vendor_requests kind ('seller_referral')
# so admin can tell the two apart. Mirrors suggest_vendor's logic closely
# on purpose; see admin_vendor_request_decide for the shared deny/approve
# handling of both thread-based referral kinds.
@app.route("/app/seller/vendors/suggest", methods=("GET", "POST"))
@role_required("seller")
def seller_suggest_vendor():
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        website = request.form.get("website", "").strip()
        if not company_name or not website:
            flash("Company name and website are required.", "error")
            return redirect(url_for("seller_suggest_vendor"))

        segments = _parse_proposed_segments(",".join(request.form.getlist("segments")))
        company_size = request.form.get("company_size", "").strip()
        if company_size not in COMPANY_SIZE_BANDS:
            company_size = None
        founded_year = request.form.get("founded_year", "").strip()
        founded_year = int(founded_year) if founded_year.isdigit() else None
        hq_location = request.form.get("hq_location", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        notes = request.form.get("notes", "").strip()

        admin = get_admin_user()
        if not admin:
            flash("Vendor suggestions aren't set up yet — there's no BuyersForce admin account to reach.", "error")
            return redirect(url_for("seller_suggest_vendor"))

        thread = get_or_create_direct_thread(g.user["id"], admin["id"])
        ensure_contact(g.user["id"], contact_user_id=admin["id"])
        ensure_contact(admin["id"], contact_user_id=g.user["id"])

        summary_lines = [f"New vendor suggestion: {company_name} ({website})"]
        if segments:
            summary_lines.append(f"Segments: {', '.join(segments)}")
        if company_size:
            summary_lines.append(f"Company size: {company_size}")
        if founded_year:
            summary_lines.append(f"Founded: {founded_year}")
        if hq_location:
            summary_lines.append(f"HQ: {hq_location}")
        if contact_name or contact_email or contact_phone:
            summary_lines.append(
                f"Contact: {contact_name or '—'} · {contact_email or '—'} · {contact_phone or '—'}"
            )
        if notes:
            summary_lines.append(f"Notes: {notes}")
        dbm.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (thread["id"], g.user["id"], "\n".join(summary_lines)),
        )

        dbm.execute(
            "INSERT INTO vendor_requests (kind, requested_by_user_id, company_name, website, "
            "proposed_segments, company_size, founded_year, hq_location, contact_name, "
            "contact_email, contact_phone, notes, thread_id) "
            "VALUES ('seller_referral', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], company_name, website, ",".join(segments), company_size, founded_year,
             hq_location, contact_name, contact_email, contact_phone, notes, thread["id"]),
        )
        log_activity(g.user["id"], f"suggested a vendor ({company_name})")
        flash("Thank you! You'll be contacted by a BuyersForce admin shortly.", "success")
        return redirect(url_for("seller_thread", thread_id=thread["id"]))

    return render_template(
        "seller/suggest_vendor.html", all_segments=all_technology_segments(), company_sizes=COMPANY_SIZE_BANDS,
    )


@app.route("/app/seller/leads")
@role_required("seller")
def seller_leads():
    vendor = seller_vendor(g.user)
    leads = dbm.query(
        "SELECT s.*, u.name buyer_name, u.company buyer_company, u.photo_data_url buyer_photo, "
        "u.title buyer_title, "
        "u.open_to_buy buyer_open_to_buy, u.outreach_enabled buyer_outreach_enabled, "
        "u.outreach_informational buyer_outreach_informational, "
        "u.outreach_marketing_events buyer_outreach_marketing_events, "
        "u.outreach_none buyer_outreach_none "
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
        "SELECT t.*, u.name buyer_name, u.company buyer_company, u.photo_data_url buyer_photo, "
        "(SELECT body FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_body, "
        "(SELECT created_at FROM messages WHERE thread_id=t.id ORDER BY created_at DESC LIMIT 1) last_at "
        "FROM threads t JOIN users u ON u.id = t.buyer_user_id "
        "WHERE t.type='vendor' AND t.vendor_id=? ORDER BY last_at DESC",
        (vendor["id"],),
    )
    direct_threads = _direct_threads_for(g.user)
    return render_template(
        "seller/messages.html", threads=threads, vendor=vendor, direct_threads=direct_threads
    )


@app.route("/app/seller/messages/<int:thread_id>", methods=("GET", "POST"))
@role_required("seller")
def seller_thread(thread_id):
    thread = _load_thread_for_user(thread_id, g.user)
    info = thread_display_info(thread, g.user)
    buyer = info.get("buyer") or info.get("other_user")
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if buyer and is_message_blocked(buyer["id"], g.user):
            flash("This buyer isn't available to message right now.", "error")
        elif body:
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
    mark_thread_read(g.user["id"], thread_id)
    return render_template("seller/thread.html", thread=thread, messages=messages, info=info)


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
