"""Seed BuyersForce with realistic demo data."""
import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash

# DB_PATH can be overridden via env var to point at a persistent volume
# mount (e.g. /data/buyersforce.db on Railway) so data survives redeploys.
# Falls back to a file next to this script for local development.
DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "buyersforce.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Admin account -- configurable via env vars so a real password can be set at
# deploy time instead of being hardcoded in source. Falls back to a random
# password (printed once at seed time) if not provided.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "kj.jackson9@gmail.com")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Kevin Jackson")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)

# Demo seed accounts get random, unknown passwords -- nobody is meant to log
# in as them directly. The admin grants/regrants access via an invite link
# from the admin panel, which works for existing accounts too (password reset).
def _random_password_hash():
    return generate_password_hash(secrets.token_urlsafe(16))


def run():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript(open(SCHEMA_PATH).read())
    cur = con.cursor()

    def user(role, name, email, company, title="", is_admin=0, password_hash=None):
        cur.execute(
            "INSERT INTO users (role, name, email, password_hash, company, title, is_admin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (role, name, email, password_hash or _random_password_hash(), company, title, is_admin),
        )
        return cur.lastrowid

    # ---- Admin account (master access -- controls who else can sign in) ----
    user("admin", ADMIN_NAME, ADMIN_EMAIL, "BuyersForce", "Administrator",
         is_admin=1, password_hash=generate_password_hash(ADMIN_PASSWORD))

    # ---- Buyers: two buying teams so collaboration is visible ----
    dana = user("buyer", "Dana Whitfield", "dana@meridianhealth.com", "Meridian Health",
                "Director of Security Engineering")
    priya = user("buyer", "Priya Kapoor", "priya@meridianhealth.com", "Meridian Health",
                 "Senior Security Engineer")
    marcus = user("buyer", "Marcus Ide", "marcus@meridianhealth.com", "Meridian Health",
                  "VP of Infrastructure")
    grace = user("buyer", "Grace Lin", "grace@northwindbank.com", "Northwind Bank",
                 "Head of Cloud Security")
    tomas = user("buyer", "Tomas Reyes", "tomas@northwindbank.com", "Northwind Bank",
                 "Security Engineer")

    # ---- Sellers ----
    seller_defs = [
        ("Aegis Shield", "sam@aegisshield.io", "Cloud Security", "#2a78d6", "AS",
         "Runtime protection for cloud-native workloads",
         "Aegis Shield gives engineering teams a single control plane for detecting and "
         "stopping threats across containers, Kubernetes, and serverless — without slowing "
         "down deploys.",
         "aegisshield.io",
         ["Kubernetes", "Runtime Security", "CNAPP", "Threat Detection"],
         [
             ("Runtime Defense", "Per-workload pricing",
              "Real-time anomaly detection on running containers|"
              "Auto-generated network policies|eBPF-based sensor with <1% CPU overhead|"
              "Native Kubernetes admission controller"),
             ("Cloud Posture Manager", "Flat annual license",
              "Continuous misconfiguration scanning across AWS, GCP, Azure|"
              "Auto-remediation playbooks|Compliance mapping to SOC 2, PCI-DSS, HIPAA"),
         ]),
        ("Ironclad Identity", "jen@ironcladid.com", "Identity & Access", "#1baf7a", "II",
         "Zero-trust access for every engineer and every service",
         "Ironclad Identity replaces static credentials with short-lived, policy-driven access "
         "for humans and machines, so engineering teams can move fast without leaving standing "
         "privileges behind.",
         "ironcladid.com",
         ["Zero Trust", "IAM", "Secrets Management", "SSO"],
         [
             ("Access Broker", "Per-seat pricing",
              "Just-in-time privileged access with automatic expiry|"
              "Full audit trail exportable to your SIEM|"
              "Native Okta, Azure AD and Google Workspace integration"),
             ("Secrets Vault", "Usage-based pricing",
              "Dynamic secrets for databases and cloud APIs|Automatic rotation|"
              "Kubernetes CSI driver for zero-code adoption"),
         ]),
        ("Sentinel Grid", "omar@sentinelgrid.ai", "Threat Detection", "#eb6834", "SG",
         "AI-driven detection and response for hybrid environments",
         "Sentinel Grid correlates signal across endpoint, network, and cloud to cut alert "
         "fatigue and give engineering teams a prioritized, explainable queue of real threats.",
         "sentinelgrid.ai",
         ["XDR", "SIEM", "SOAR", "Threat Intel"],
         [
             ("XDR Platform", "Per-endpoint pricing",
              "Cross-signal correlation across endpoint, network, cloud|"
              "Automated triage with explainable AI scoring|"
              "One-click response playbooks"),
         ]),
        ("Vaultstream Data Security", "lee@vaultstream.com", "Data Security", "#4a3aa7", "VD",
         "Discover, classify, and protect sensitive data everywhere it lives",
         "Vaultstream continuously scans structured and unstructured data across your cloud "
         "and SaaS stack, flags exposure, and enforces policy at the point of access.",
         "vaultstream.com",
         ["DSPM", "DLP", "Data Classification"],
         [
             ("Data Security Posture Mgmt", "Per-TB pricing",
              "Automated discovery of sensitive data across cloud stores|"
              "Risk-prioritized remediation queue|Native integration with data warehouses"),
         ]),
    ]

    vendor_ids = {}
    for name, email, category, accent, initials, tagline, desc, site, tags, listings in seller_defs:
        sid = user("seller", f"{name} Team", email, name, "Vendor Success")
        cur.execute(
            "INSERT INTO vendors (seller_user_id, company_name, category, tagline, description, "
            "website, accent, initials) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, name, category, tagline, desc, site, accent, initials),
        )
        vid = cur.lastrowid
        vendor_ids[name] = vid
        for tag in tags:
            cur.execute("INSERT INTO vendor_tags (vendor_id, tag) VALUES (?, ?)", (vid, tag))
        for lname, pricing, feats in listings:
            cur.execute(
                "INSERT INTO listings (vendor_id, name, description, pricing_model) "
                "VALUES (?, ?, ?, ?)",
                (vid, lname, "", pricing),
            )
            lid = cur.lastrowid
            for feat in feats.split("|"):
                cur.execute(
                    "INSERT INTO listing_features (listing_id, feature_text) VALUES (?, ?)",
                    (lid, feat),
                )

    con.commit()

    # ---- Shortlist activity for Meridian Health (the featured buying team) ----
    def shortlist(buyer_id, vendor_name, status):
        cur.execute(
            "INSERT INTO shortlist (buyer_user_id, vendor_id, status) VALUES (?, ?, ?)",
            (buyer_id, vendor_ids[vendor_name], status),
        )

    shortlist(dana, "Aegis Shield", "evaluating")
    shortlist(dana, "Sentinel Grid", "shortlisted")
    shortlist(dana, "Ironclad Identity", "discovered")
    shortlist(priya, "Aegis Shield", "evaluating")
    shortlist(grace, "Vaultstream Data Security", "shortlisted")
    shortlist(grace, "Ironclad Identity", "evaluating")
    con.commit()

    # ---- A vendor conversation, buyer-initiated ----
    cur.execute(
        "INSERT INTO threads (type, buyer_user_id, vendor_id, subject, created_by) "
        "VALUES ('vendor', ?, ?, 'Conversation with Aegis Shield', ?)",
        (dana, vendor_ids["Aegis Shield"], dana),
    )
    t1 = cur.lastrowid
    aegis_seller = cur.execute(
        "SELECT id FROM users WHERE email='sam@aegisshield.io'"
    ).fetchone()[0]
    convo = [
        (dana, "Hi Aegis team — we're evaluating runtime protection for our EKS clusters. "
               "Can you share how your sensor overhead compares at scale?"),
        (aegis_seller, "Thanks for reaching out, Dana! Our eBPF sensor typically runs under "
                       "1% CPU overhead even on large clusters — happy to share benchmark data "
                       "and set up a technical deep-dive whenever works for your team."),
        (dana, "That would be great. Priya from my team will likely join too — she owns our "
               "container security roadmap."),
    ]
    for sender, body in convo:
        cur.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (t1, sender, body),
        )
    con.commit()

    # ---- Internal team thread ----
    cur.execute(
        "INSERT INTO threads (type, buyer_user_id, subject, created_by) VALUES "
        "('teammate', NULL, '[Meridian Health] Runtime security shortlist', ?)",
        (dana,),
    )
    t2 = cur.lastrowid
    team_convo = [
        (dana, "Kicking off our shortlist for runtime protection — Aegis Shield and Sentinel "
               "Grid both look strong. Let's use the standard security-tooling scorecard."),
        (priya, "Agreed. I'll get my scores in on Aegis Shield by Friday."),
        (marcus, "Budget-wise either works. Care most about integration effort and support SLAs."),
    ]
    for sender, body in team_convo:
        cur.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body) VALUES (?, ?, ?)",
            (t2, sender, body),
        )
    con.commit()

    # ---- Evaluation template (shared library) ----
    cur.execute(
        "INSERT INTO eval_templates (owner_user_id, company, name, description, is_shared) "
        "VALUES (?, 'Meridian Health', 'Security Tooling Scorecard', "
        "'Standard rubric for evaluating security vendors across technical fit, integration, "
        "and support.', 1)",
        (dana,),
    )
    tmpl1 = cur.lastrowid
    criteria = [
        ("Technical fit for our stack", 3),
        ("Ease of integration", 2),
        ("Support & SLA quality", 2),
        ("Pricing transparency", 1),
        ("Roadmap alignment", 2),
    ]
    crit_ids = []
    for i, (label, weight) in enumerate(criteria):
        cur.execute(
            "INSERT INTO eval_criteria (template_id, label, weight, position) VALUES (?, ?, ?, ?)",
            (tmpl1, label, weight, i),
        )
        crit_ids.append(cur.lastrowid)

    cur.execute(
        "INSERT INTO eval_templates (owner_user_id, company, name, description, is_shared) "
        "VALUES (?, 'Northwind Bank', 'Vendor Risk & Fit Rubric', "
        "'Cross-functional rubric covering security, compliance, and operational readiness.', 1)",
        (grace,),
    )
    con.commit()

    # ---- Active evaluation with multiple reviewers scoring Aegis Shield ----
    cur.execute(
        "INSERT INTO evaluations (template_id, vendor_id, company, created_by) VALUES (?, ?, ?, ?)",
        (tmpl1, vendor_ids["Aegis Shield"], "Meridian Health", dana),
    )
    eval1 = cur.lastrowid

    dana_scores = [5, 4, 4, 3, 4]
    priya_scores = [4, 5, 3, 4, 4]
    for cid, score in zip(crit_ids, dana_scores):
        cur.execute(
            "INSERT INTO eval_scores (evaluation_id, criterion_id, user_id, score, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (eval1, cid, dana, score, ""),
        )
    for cid, score in zip(crit_ids, priya_scores):
        cur.execute(
            "INSERT INTO eval_scores (evaluation_id, criterion_id, user_id, score, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (eval1, cid, priya, score, ""),
        )
    cur.execute(
        "UPDATE eval_scores SET comment=? WHERE evaluation_id=? AND user_id=? AND criterion_id=?",
        ("Sensor overhead benchmarks matched our own load tests.", eval1, dana, crit_ids[0]),
    )
    cur.execute(
        "UPDATE eval_scores SET comment=? WHERE evaluation_id=? AND user_id=? AND criterion_id=?",
        ("Kubernetes admission controller dropped in with almost no config.", eval1, priya, crit_ids[1]),
    )
    con.commit()

    # ---- Meeting requests ----
    cur.execute(
        "INSERT INTO meetings (buyer_user_id, vendor_id, proposed_time, note, status) "
        "VALUES (?, ?, '2026-08-04 10:00:00', 'Technical deep-dive on eBPF sensor architecture', "
        "'confirmed')",
        (dana, vendor_ids["Aegis Shield"]),
    )
    cur.execute(
        "INSERT INTO meetings (buyer_user_id, vendor_id, proposed_time, note, status) "
        "VALUES (?, ?, '2026-08-06 14:00:00', 'Intro call for Sentinel Grid XDR platform', "
        "'requested')",
        (dana, vendor_ids["Sentinel Grid"]),
    )
    cur.execute(
        "INSERT INTO meetings (buyer_user_id, vendor_id, proposed_time, note, status) "
        "VALUES (?, ?, '2026-08-05 09:30:00', 'Data classification demo for PCI scope', "
        "'requested')",
        (grace, vendor_ids["Vaultstream Data Security"]),
    )
    con.commit()

    # ---- Activity log ----
    activities = [
        (dana, "started an evaluation for Aegis Shield", ""),
        (priya, "submitted scores for Aegis Shield", ""),
        (dana, "requested a meeting with Aegis Shield", ""),
        (dana, "marked Sentinel Grid as shortlisted", ""),
        (grace, "marked Vaultstream Data Security as shortlisted", ""),
    ]
    for uid, verb, detail in activities:
        cur.execute(
            "INSERT INTO activity_log (user_id, verb, detail) VALUES (?, ?, ?)", (uid, verb, detail)
        )
    con.commit()

    # ---- Partner contacts for a seller ----
    aegis_seller_id = cur.execute(
        "SELECT id FROM users WHERE email='sam@aegisshield.io'"
    ).fetchone()[0]
    cur.execute(
        "INSERT INTO partner_contacts (seller_user_id, name, org, role, email) VALUES "
        "(?, 'Renata Cole', 'CloudScale Resellers', 'Channel Manager', 'renata@cloudscale.com')",
        (aegis_seller_id,),
    )
    cur.execute(
        "INSERT INTO partner_contacts (seller_user_id, name, org, role, email) VALUES "
        "(?, 'Devon Marsh', 'AWS ISV Alliance', 'Alliance Partner', 'devon@amazon-alliance.example')",
        (aegis_seller_id,),
    )
    con.commit()
    con.close()
    print("Seeded buyersforce.db")
    print("")
    print("=" * 60)
    print(f"Admin login: {ADMIN_EMAIL}")
    if not os.environ.get("ADMIN_PASSWORD"):
        print(f"Admin password (auto-generated): {ADMIN_PASSWORD}")
        print("Log in and change this immediately from Account settings.")
    else:
        print("Admin password: set via ADMIN_PASSWORD environment variable.")
    print("=" * 60)
    print("")
    print("Demo buyer/seller accounts were seeded with random, unknown")
    print("passwords. Use the admin panel's 'Grant access' action to send")
    print("any of them (or a new person) a link to set their own password.")


if __name__ == "__main__":
    run()
