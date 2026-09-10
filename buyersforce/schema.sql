-- BuyersForce schema (PostgreSQL)

DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS vendors CASCADE;
DROP TABLE IF EXISTS listings CASCADE;
DROP TABLE IF EXISTS listing_features CASCADE;
DROP TABLE IF EXISTS vendor_tags CASCADE;
DROP TABLE IF EXISTS shortlist CASCADE;
DROP TABLE IF EXISTS threads CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS meetings CASCADE;
DROP TABLE IF EXISTS eval_templates CASCADE;
DROP TABLE IF EXISTS eval_criteria CASCADE;
DROP TABLE IF EXISTS evaluations CASCADE;
DROP TABLE IF EXISTS eval_scores CASCADE;
DROP TABLE IF EXISTS partner_contacts CASCADE;
DROP TABLE IF EXISTS activity_log CASCADE;
DROP TABLE IF EXISTS invites CASCADE;
DROP TABLE IF EXISTS contacts CASCADE;
DROP TABLE IF EXISTS thread_reads CASCADE;
DROP TABLE IF EXISTS blocked_vendors CASCADE;
DROP TABLE IF EXISTS role_change_requests CASCADE;
DROP TABLE IF EXISTS vendor_segments CASCADE;
DROP TABLE IF EXISTS support_requests CASCADE;
DROP TABLE IF EXISTS vendor_requests CASCADE;
DROP TABLE IF EXISTS vendor_ratings CASCADE;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('buyer','seller','admin')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    -- Profile fields, filled in via the mandatory post-signup profile
    -- screen (see profile_is_complete() in app.py) and editable later
    -- from Account > Profile. See migrate.py's _add_profile_columns for
    -- the equivalent migration on a pre-existing database.
    first_name TEXT,
    last_name TEXT,
    personal_email TEXT,
    phone TEXT,
    phone_country TEXT NOT NULL DEFAULT 'US',
    state TEXT,
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    zip TEXT,
    secondary_phone TEXT,
    secondary_phone_country TEXT,
    linkedin_url TEXT,
    no_linkedin INTEGER NOT NULL DEFAULT 0,
    timezone TEXT,
    open_to_buy INTEGER NOT NULL DEFAULT 0,
    photo_data_url TEXT,
    account_status TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('pending', 'active', 'denied'))
);

-- A buyer-owned blocklist so a buyer can stop a specific seller, or every
-- seller at a vendor company, from messaging them. See migrate.py's
-- _add_blocked_vendors_table for details.
CREATE TABLE blocked_vendors (
    id SERIAL PRIMARY KEY,
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    blocked_user_id INTEGER REFERENCES users(id),
    blocked_email TEXT,
    blocked_company TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    CHECK (blocked_user_id IS NOT NULL OR blocked_email IS NOT NULL OR blocked_company IS NOT NULL)
);
CREATE UNIQUE INDEX blocked_vendors_buyer_user_uniq
ON blocked_vendors (buyer_user_id, blocked_user_id)
WHERE blocked_user_id IS NOT NULL;

-- A buyer or seller who thinks their account type is wrong (e.g. picked
-- the wrong option at signup) can ask a BF admin to flip it, rather than
-- being able to change it themselves -- role stays admin-controlled. See
-- migrate.py's _add_phone_country_and_role_requests for details.
CREATE TABLE role_change_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    previous_role TEXT NOT NULL,
    requested_role TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    resolved_at TEXT,
    resolved_by INTEGER REFERENCES users(id)
);
CREATE UNIQUE INDEX role_change_requests_one_pending_uniq
ON role_change_requests (user_id)
WHERE status = 'pending';

-- Invite-only access control. An admin creates an invite for an email address;
-- the recipient uses the link to set their own password and activate the
-- account. Re-inviting an email that already has an account resets that
-- account's password via the same flow (used as a "grant/regain access" link).
CREATE TABLE invites (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('buyer','seller')),
    company TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    token TEXT NOT NULL UNIQUE,
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    expires_at TEXT NOT NULL,
    used_at TEXT
);

-- seller_user_id is nullable: an admin-seeded vendor (pre-populated from
-- public cybersecurity vendor lists -- see seed_data/vendor_seed_list.json
-- and migrate.py's _seed_vendor_directory) has no real seller account yet.
-- These "unclaimed" listings are admin-curated and read-only to buyers
-- until a future "claim this listing" flow (not built yet) lets a
-- verified rep from that company take over editing rights.
CREATE TABLE vendors (
    id SERIAL PRIMARY KEY,
    seller_user_id INTEGER REFERENCES users(id),
    company_name TEXT NOT NULL,
    category TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    accent TEXT NOT NULL DEFAULT '#2a78d6',
    initials TEXT NOT NULL DEFAULT 'VN',
    company_size TEXT,
    founded_year INTEGER,
    hq_location TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    source TEXT NOT NULL DEFAULT '',
    -- A specific, verified Wikipedia/Wikimedia Commons logo image URL,
    -- set for admin-seeded vendors where one was found and quality-checked
    -- (see the vendor-logo enrichment pass). NULL falls back to the
    -- website-favicon guess in app.py's vendor_favicon_url.
    wiki_logo_url TEXT,
    -- BuyersForce is meant to span more than cybersecurity eventually (see
    -- app.py's TECHNOLOGY_CATEGORIES) -- every vendor today is
    -- 'cybersecurity' since that's the only category built out so far, but
    -- this is the column the Discover page's top-level category filter
    -- reads, ahead of the existing segment filter underneath it.
    technology_category TEXT NOT NULL DEFAULT 'cybersecurity',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- Only enforced for admin-seeded ("unclaimed") vendors, so migrate.py's
-- seed step is idempotent across repeated runs/deploys. Real sellers keep
-- creating their own vendor row per account with no uniqueness constraint
-- on the name.
CREATE UNIQUE INDEX vendors_seeded_company_name_uniq
ON vendors (company_name)
WHERE seller_user_id IS NULL;

-- Controlled cybersecurity segment/category tags (see app.py's
-- CYBERSECURITY_SEGMENTS), distinct from the freeform vendor_tags below --
-- this is what powers the buyer-facing multi-select directory filter.
CREATE TABLE vendor_segments (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    segment TEXT NOT NULL
);
CREATE UNIQUE INDEX vendor_segments_vendor_segment_uniq
ON vendor_segments (vendor_id, segment);

CREATE TABLE listings (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    pricing_model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE listing_features (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    feature_text TEXT NOT NULL
);

CREATE TABLE vendor_tags (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    tag TEXT NOT NULL
);

CREATE TABLE shortlist (
    id SERIAL PRIMARY KEY,
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    status TEXT NOT NULL DEFAULT 'discovered' CHECK (status IN ('discovered','evaluating','shortlisted','selected','passed')),
    -- Set the first time status becomes 'selected' -- anchors the 90-day
    -- production check-in rating window (see vendor_ratings below).
    selected_at TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(buyer_user_id, vendor_id)
);

-- type distinguishes buyer<->vendor conversations, internal per-company
-- teammate discussion boards, seller partner threads, and general 1:1
-- "direct" conversations (teammate-to-teammate, or to someone who isn't
-- a member yet -- participant_b_id stays NULL and external_name/email
-- carry who it's for).
CREATE TABLE threads (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('vendor','teammate','partner','direct')),
    buyer_user_id INTEGER REFERENCES users(id),
    vendor_id INTEGER REFERENCES vendors(id),
    participant_a_id INTEGER REFERENCES users(id),
    participant_b_id INTEGER REFERENCES users(id),
    external_name TEXT,
    external_email TEXT,
    pending_email_sent_at TEXT,
    subject TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- A user's request for tech support, a bug report, or a feature idea. The
-- actual back-and-forth happens over the regular messaging system (see
-- thread_id, a 'direct' thread with the admin account) -- this table exists
-- so the admin dashboard can list, badge, and triage requests by category
-- and status without scanning every direct-message thread.
CREATE TABLE support_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    category TEXT NOT NULL CHECK (category IN ('tech_support', 'bug_report', 'feature_request')),
    notes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
    thread_id INTEGER REFERENCES threads(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- A request to add a company to the vendor directory -- either a buyer
-- suggesting a vendor they know (kind='buyer_referral', tied to their own
-- account and an admin message thread), or a vendor's own contact asking
-- to be listed before they have any BuyersForce account at all
-- (kind='seller_signup', submitted from the public /join-as-vendor page).
-- Approving either kind creates a real vendors row; approving a
-- seller_signup additionally creates the contact's own seller account
-- (created_user_id) via the same invite-link mechanism used elsewhere.
CREATE TABLE vendor_requests (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('buyer_referral', 'seller_signup')),
    requested_by_user_id INTEGER REFERENCES users(id),
    company_name TEXT NOT NULL,
    website TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    proposed_segments TEXT NOT NULL DEFAULT '',
    company_size TEXT,
    founded_year INTEGER,
    hq_location TEXT,
    contact_name TEXT,
    contact_title TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    thread_id INTEGER REFERENCES threads(id),
    created_vendor_id INTEGER REFERENCES vendors(id),
    created_user_id INTEGER REFERENCES users(id),
    denial_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    resolved_at TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

-- Tracks the highest message id each user has seen in each thread, to
-- compute an unread-messages badge. A message-id cursor rather than a
-- timestamp, since this app's timestamps only have one-second
-- resolution.
CREATE TABLE thread_reads (
    user_id INTEGER NOT NULL REFERENCES users(id),
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    last_read_message_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, thread_id)
);

-- A user's personal address book. A row with contact_user_id set is a
-- fellow BuyersForce member; one with external_email instead is someone
-- reached by email who isn't a member. Rows are added automatically the
-- first time two people message each other.
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    contact_user_id INTEGER REFERENCES users(id),
    external_name TEXT,
    external_email TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE UNIQUE INDEX contacts_owner_contact_uniq ON contacts (owner_user_id, contact_user_id)
    WHERE contact_user_id IS NOT NULL;
CREATE UNIQUE INDEX contacts_owner_external_email_uniq ON contacts (owner_user_id, external_email)
    WHERE contact_user_id IS NULL AND external_email IS NOT NULL;

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    sender_user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE meetings (
    id SERIAL PRIMARY KEY,
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    proposed_time TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','confirmed','declined')),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE eval_templates (
    id SERIAL PRIMARY KEY,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    company TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_shared INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE eval_criteria (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES eval_templates(id),
    label TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES eval_templates(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    company TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE eval_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id),
    criterion_id INTEGER NOT NULL REFERENCES eval_criteria(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(evaluation_id, criterion_id, user_id)
);

-- BuyersForce-native crowdsourced vendor ratings, visible platform-wide
-- (unlike eval_scores above, which is a private per-company scorecard).
-- One row per buyer per vendor per phase: 'evaluation' (rated any time
-- while actively considering a vendor) and 'production' (a check-in rating
-- that only opens up ~90 days after the buyer marks the vendor 'selected',
-- to see whether the initial read held up). Both phases score the same
-- three dimensions plus an overall so the numbers aggregate cleanly, but
-- the question wording shown to the buyer differs by phase (see
-- RATING_PHASE_QUESTIONS in app.py) since what matters pre-sale (buying
-- experience) and post-deployment (ongoing support, renewal confidence)
-- isn't quite the same question. Ratings are stored per-buyer but always
-- shown in aggregate/anonymized form -- no individual rater is ever named.
CREATE TABLE vendor_ratings (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    company TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('evaluation', 'production')),
    overall_score INTEGER NOT NULL CHECK (overall_score BETWEEN 1 AND 10),
    product_score INTEGER NOT NULL CHECK (product_score BETWEEN 1 AND 10),
    support_score INTEGER NOT NULL CHECK (support_score BETWEEN 1 AND 10),
    sales_score INTEGER NOT NULL CHECK (sales_score BETWEEN 1 AND 10),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(vendor_id, buyer_user_id, phase)
);

CREATE TABLE partner_contacts (
    id SERIAL PRIMARY KEY,
    seller_user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    org TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Alliance Partner',
    email TEXT NOT NULL DEFAULT ''
);

CREATE TABLE activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    verb TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);
