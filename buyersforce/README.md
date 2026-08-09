# BuyersForce

A working prototype of **BuyersForce** — a dedicated SaaS platform for technology
*buyers* (engineering teams evaluating complex technology like cybersecurity, IT,
and infrastructure tools), built to demonstrate the product concept end-to-end:
vendor discovery, buyer-initiated messaging, collaborative evaluation scorecards,
meeting scheduling, and a seller-side portal for vendor profiles, leads, and
partner collaboration.

This is a real, runnable full-stack application — Flask backend, SQLite
database, server-rendered pages, and no build step required.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 seed.py                 # creates buyersforce.db with demo data
python3 app.py                  # starts the server on http://localhost:5055
```

Then open **http://localhost:5055** in your browser.

## Demo logins

The login page (`/login`) lists every seeded account with a one-click "Log in"
button. All demo accounts also use the password `demo1234` if you want to type
credentials manually.

- **Buyer:** `dana@meridianhealth.com` — Director of Security Engineering at
  Meridian Health, a healthcare company evaluating cybersecurity vendors.
  Her teammates `priya@meridianhealth.com` and `marcus@meridianhealth.com`
  share the same evaluation templates and team threads, so you can see
  collaborative scoring in action.
- **Seller:** `sam@aegisshield.io` — the vendor account for Aegis Shield, a
  cloud security company. Try messaging it from the buyer side, then log in
  as the seller to see the lead and reply.

## What's implemented

**Buyer side**
- Vendor discovery with search, category filtering, and a side-by-side
  comparison view (up to 3 vendors)
- Vendor profile pages with product listings, pricing, and features
- A pipeline/shortlist with status tracking (discovered → shortlisted →
  evaluating → selected)
- Buyer-initiated messaging — vendors can never start a conversation
- Meeting requests with vendor confirm/decline
- A shared, reusable evaluation template library with weighted criteria
- Collaborative scorecards — every teammate scores independently, with a
  weighted overall score and a per-reviewer breakdown chart
- Internal team threads, scoped to your company

**Seller side**
- An editable vendor profile with live preview (what buyers actually see)
- Product listing management (add/remove features and pricing)
- A leads dashboard that only shows buyers who have *engaged* — no passive
  visitor tracking, which is a deliberate contrast with how vendor sites
  behave today
- A mock "Sync to Salesforce" action on each lead
- Buyer messaging (reply-only, matching the buyer-controlled model)
- A partner/reseller collaboration portal

## Project structure

```
app.py                 Flask app: routes for buyer + seller areas, auth
db.py                  Lightweight SQLite helper (raw SQL, no ORM)
schema.sql             Database schema
seed.py                 Seeds realistic demo data (run this once before first use)
templates/             Jinja2 templates (landing page, buyer app, seller app)
static/css/style.css   Hand-written design system (no CSS framework/CDN)
static/js/app.js       Small progressive-enhancement JS (no build step)
```

## Notes on design choices

- No external CDNs or npm packages are used anywhere — everything (fonts,
  icons-as-emoji, styles, interactivity) is self-contained so the app runs
  offline with zero build tooling.
- Auth is intentionally simple (Werkzeug password hashing + Flask sessions)
  since this is a product prototype, not a security-hardened production app.
  Swap in a real identity provider before shipping this for real.
- The database is SQLite for portability; the schema (see `schema.sql`) maps
  cleanly onto Postgres if you want to move this toward production.
