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
DROP TABLE IF EXISTS eval_projects CASCADE;
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
DROP TABLE IF EXISTS technology_categories CASCADE;
DROP TABLE IF EXISTS technology_segments CASCADE;
DROP TABLE IF EXISTS vendor_technology_categories CASCADE;
DROP TABLE IF EXISTS vendor_announcements CASCADE;
DROP TABLE IF EXISTS vendor_awards CASCADE;
DROP TABLE IF EXISTS vendor_claim_requests CASCADE;
DROP TABLE IF EXISTS vendor_listing_reports CASCADE;
DROP TABLE IF EXISTS eval_project_no_award_reasons CASCADE;

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
    -- "Open to Outreach" -- a buyer-only signal shown to sellers (leads
    -- dashboard, conversation header). outreach_enabled is the parent
    -- toggle; open_to_buy, outreach_informational, and
    -- outreach_marketing_events are independent sub-options under it;
    -- outreach_none ("Not seeking outreach") is mutually exclusive with
    -- those three, enforced in _apply_profile_form(). See migrate.py's
    -- _add_outreach_columns for the equivalent migration (and backfill)
    -- on a pre-existing database.
    open_to_buy INTEGER NOT NULL DEFAULT 0,
    outreach_enabled INTEGER NOT NULL DEFAULT 0,
    outreach_informational INTEGER NOT NULL DEFAULT 0,
    outreach_marketing_events INTEGER NOT NULL DEFAULT 0,
    outreach_none INTEGER NOT NULL DEFAULT 0,
    photo_data_url TEXT,
    -- 'revoked' (added 2026-09-28): an admin removed this user's access after it was active -- see app.py's admin_users_revoke/admin_users_restore. Reversible, same as vendors.status = 'removed'.
    account_status TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('pending', 'active', 'denied', 'revoked')),
    -- Per-account light/dark toggle, set from Account > Profile >
    -- Appearance. Defaults to 'light' so nobody's view changes until they
    -- opt in. See migrate.py's _add_theme_preference_column for the
    -- equivalent migration on a pre-existing database.
    theme_preference TEXT NOT NULL DEFAULT 'light' CHECK (theme_preference IN ('light', 'dark'))
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
    -- Soft delete for a listing: 'removed' hides it from Discover/All
    -- Vendors and from its own profile page for everyone but an admin, but
    -- keeps the row (and anything referencing it -- evaluations, ratings,
    -- shortlist entries) intact and restorable. See app.py's
    -- admin_vendors_remove/admin_vendor_restore.
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    removed_at TEXT,
    -- Primary human contact for this listing (buyers and other sellers at
    -- the same company see this alongside contact_email/contact_phone).
    contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT,
    contact_phone TEXT,
    -- Which PHONE_COUNTRIES entry contact_phone is formatted/dialed for
    -- (see app.py's phone-format.js wiring on My Company) -- mirrors
    -- users.phone_country's role for the account phone fields.
    contact_phone_country TEXT NOT NULL DEFAULT 'US',
    source TEXT NOT NULL DEFAULT '',
    -- A specific, verified Wikipedia/Wikimedia Commons logo image URL,
    -- set for admin-seeded vendors where one was found and quality-checked
    -- (see the vendor-logo enrichment pass). NULL falls back to the
    -- website-favicon guess in app.py's vendor_favicon_url.
    wiki_logo_url TEXT,
    -- Seller-provided logo, either pasted in directly (a URL to an image
    -- already hosted somewhere) or uploaded and stored inline as a base64
    -- data URI (mirrors users.photo_data_url -- see app.py's
    -- _read_uploaded_vendor_logo). Display precedence, see
    -- vendor_display_logo_url in app.py: logo_upload_data_url,
    -- logo_link_url, wiki_logo_url, favicon guess, then initials.
    logo_link_url TEXT,
    logo_upload_data_url TEXT,
    -- BuyersForce is meant to span more than cybersecurity eventually (see
    -- app.py's TECHNOLOGY_CATEGORIES) -- every vendor today is
    -- 'cybersecurity' since that's the only category built out so far, but
    -- this is the column the Discover page's top-level category filter
    -- reads, ahead of the existing segment filter underneath it.
    technology_category TEXT NOT NULL DEFAULT 'cybersecurity',
    -- Public/private ownership, and (only when public) the stock ticker --
    -- see seller_profile's editor form. Mandatory fields there once a
    -- seller has claimed a listing (ownership_status always; stock_ticker
    -- only if ownership_status = 'public'), but left nullable at the
    -- schema level since ~235 admin-seeded, unclaimed vendors predate this
    -- column (backfilled by migrate.py's _backfill_vendor_ownership data
    -- patch, defaulting to 'private' except for a confirmed-public list).
    ownership_status TEXT CHECK (ownership_status IN ('public', 'private')),
    stock_ticker TEXT,
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

-- Seller/admin-extensible master lists backing the "Technology Category"
-- and "Sub-Categories / Segments" pickers (see app.py's
-- all_technology_categories()/all_technology_segments() and the
-- _ensure_technology_category()/_ensure_technology_segment() "add a new
-- one" helpers). Seeded once by migrate.py's _seed_technology_taxonomy
-- from what used to be app.py's only source of truth.
CREATE TABLE technology_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE UNIQUE INDEX technology_categories_name_uniq
ON technology_categories (lower(name));

CREATE TABLE technology_segments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE UNIQUE INDEX technology_segments_name_uniq
ON technology_segments (lower(name));

-- A vendor's own selected Technology Categories -- multi-select, mirrors
-- vendor_segments' shape exactly.
CREATE TABLE vendor_technology_categories (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    category TEXT NOT NULL
);
CREATE UNIQUE INDEX vendor_technology_categories_uniq
ON vendor_technology_categories (vendor_id, category);

-- Seller-authored "About" content shown on the vendor's public profile
-- (buyer/vendor.html, seller/vendor_view.html) as well as managed from My
-- Company. Each entry is either a direct hyperlink out to something
-- already live on the vendor's own site (so it stays current without the
-- seller re-entering anything here) or a short free-text blurb written
-- directly in BuyersForce. Shown most-recent-first (see app.py's
-- vendor_announcements/vendor_awards).
CREATE TABLE vendor_announcements (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    kind TEXT NOT NULL CHECK (kind IN ('link', 'text')),
    title TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- Same shape as vendor_announcements, for industry awards/recognition.
CREATE TABLE vendor_awards (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    kind TEXT NOT NULL CHECK (kind IN ('link', 'text')),
    title TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- Only one seller per company can edit that company's My Company listing
-- (vendors.seller_user_id is that single editor). Anyone else at the same
-- company (matched by their own Account "Company" field -- see app.py's
-- seller_company_vendor) sees the listing read-only with a "Claim this
-- company listing" link, which files one of these -- a request that sits
-- in the admin queue (like vendor_requests) until decided. Approving one
-- doesn't create anything; it just reassigns vendors.seller_user_id to
-- the requester (see admin_vendor_claim_decide).
CREATE TABLE vendor_claim_requests (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    requested_by_user_id INTEGER NOT NULL REFERENCES users(id),
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    resolved_at TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

-- A "report a problem or error on this listing" note from any seller who
-- can see the listing (the editor or not) -- purely informational for
-- admin, no approve/deny decision to make, just an open/resolved queue
-- item (see admin_listing_report_resolve).
CREATE TABLE vendor_listing_reports (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    reported_by_user_id INTEGER REFERENCES users(id),
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    resolved_at TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

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
--
-- reference_number is a short ticket number (e.g. "BF-4001") shown to the
-- requester and the admin so a specific request is easy to reference in
-- follow-up -- especially once there are a lot of them around launch. It
-- starts well above 1 on purpose, so the numbering doesn't read as "request
-- #1, #2, #3..." on a brand new platform.
CREATE SEQUENCE IF NOT EXISTS support_request_ref_seq START 4000;
CREATE TABLE support_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    category TEXT NOT NULL CHECK (category IN ('tech_support', 'bug_report', 'feature_request', 'other')),
    notes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
    thread_id INTEGER REFERENCES threads(id),
    reference_number INTEGER UNIQUE DEFAULT nextval('support_request_ref_seq'),
    -- An optional screenshot/file the requester attached (see
    -- _read_uploaded_support_attachment in app.py) -- all four are NULL
    -- when nothing was attached. Stored inline as a base64 data URL, same
    -- pattern as eval_project_artifacts.
    attachment_filename TEXT,
    attachment_content_type TEXT,
    attachment_data_url TEXT,
    attachment_size_bytes INTEGER,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- A request to add a company to the vendor directory -- a buyer or seller
-- suggesting a vendor they know (kind='buyer_referral' / 'seller_referral',
-- tied to their own account and an admin message thread), or a vendor's own
-- contact asking to be listed before they have any BuyersForce account at
-- all (kind='seller_signup', submitted from the public /join-as-vendor
-- page). Approving any kind creates a real vendors row; approving a
-- seller_signup additionally creates the contact's own seller account
-- (created_user_id) via the same invite-link mechanism used elsewhere.
CREATE TABLE vendor_requests (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('buyer_referral', 'seller_referral', 'seller_signup')),
    requested_by_user_id INTEGER REFERENCES users(id),
    company_name TEXT NOT NULL,
    website TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    proposed_segments TEXT NOT NULL DEFAULT '',
    proposed_technology_categories TEXT NOT NULL DEFAULT '',
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
    -- Set when THIS user deletes the thread out of their own view --
    -- never the other party's. NULL means not deleted. A thread older
    -- than 30 days past this timestamp is treated as permanently gone
    -- (see the folder-filtering queries in app.py) without needing a
    -- separate purge job -- it just stops being selected by anything.
    deleted_at TEXT,
    -- Manual override: this user pushed an already-read thread back
    -- into "unread" (bold in the list) as a personal follow-up flag.
    -- Cleared the next time they actually open the thread (see
    -- mark_thread_read in app.py), same as the computed unread check
    -- it's OR'd together with.
    manually_unread BOOLEAN NOT NULL DEFAULT false,
    -- This user flagged the thread as important -- purely a per-viewer
    -- highlight, never shared with the other party.
    is_flagged BOOLEAN NOT NULL DEFAULT false,
    -- This user saved the thread into their own "Saved" bucket, which
    -- pulls it out of its normal section so the main list stays
    -- clean. Also per-viewer only.
    is_saved BOOLEAN NOT NULL DEFAULT false,
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
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    -- An optional screenshot/file on a reply, same base64 data-URL pattern
    -- support_requests already uses -- lets either side keep attaching
    -- files to an ongoing conversation, not just the opening message.
    attachment_filename TEXT,
    attachment_content_type TEXT,
    attachment_data_url TEXT,
    attachment_size_bytes INTEGER
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
    -- The top of the scoring scale shown on this template's scorecards
    -- (bottom is always 1) -- e.g. 5 for a 1-5 scale, 10 for 1-10. Set once
    -- at creation (see buyer_evaluation_new in app.py) and left fixed after
    -- that, since changing it once scores exist would make old and new
    -- scores mean different things. eval_scores.score's own CHECK is
    -- widened to the broadest scale any template can pick (1-10) -- the
    -- per-template ceiling below is enforced in app.py, not by Postgres,
    -- since a CHECK can't reference another table.
    scale_max INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE eval_criteria (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES eval_templates(id),
    label TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);

-- A single scorecard shared by every vendor a buyer is comparing side by
-- side against the same template (e.g. the 3 vendors they just moved to
-- Evaluations together) -- see evaluations.project_id below. "name" is
-- optional: a buyer can type one when starting the project, but the app
-- always falls back to an auto-generated "Vendor A vs. Vendor B" name
-- (project_display_name() in app.py) when it's blank, so this can be ''.
CREATE TABLE eval_projects (
    id SERIAL PRIMARY KEY,
    -- NULL means "no scorecard chosen yet" -- a project can hold vendors
    -- and notes with nothing to score them against, until someone creates
    -- a template or pulls one in from the library (see
    -- buyer_project_update_meta and buyer_evaluation_new in app.py).
    template_id INTEGER REFERENCES eval_templates(id),
    company TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    -- 'active' projects show under "Active evaluations"; 'closed' ones move
    -- to "Archive" (see buyer_evaluations in app.py). Closing never deletes
    -- anything -- the scorecard, every score, and every comment stay right
    -- where they are and stay viewable/exportable, this just records the
    -- outcome and files the project out of the active list. Reopening (see
    -- buyer_project_reopen) clears the outcome fields below and puts it
    -- back to 'active'.
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    closed_at TEXT,
    closed_by INTEGER REFERENCES users(id),
    -- The winning vendor, if any -- must be one of the vendors actually in
    -- this project (enforced in buyer_project_close). NULL covers both "not
    -- closed yet" and "closed with no vendor awarded" -- the latter is
    -- distinguished by status='closed' plus no_award_other_text/the rows in
    -- eval_project_no_award_reasons below.
    selected_vendor_id INTEGER REFERENCES vendors(id),
    -- The free-text half of "no vendor awarded, here's why" (checkbox
    -- reasons live in eval_project_no_award_reasons) -- capped at 500
    -- characters in buyer_project_close.
    no_award_other_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- Multi-select reasons for closing a project with no vendor awarded --
-- one row per reason checked, mirroring the vendor_segments/vendor_tags
-- one-row-per-tag shape rather than packing a CSV into a single column.
CREATE TABLE eval_project_no_award_reasons (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES eval_projects(id),
    reason TEXT NOT NULL CHECK (reason IN (
        'no_vendor_fit', 'selected_outside_matrix', 'lost_budget',
        'poor_timing', 'deprioritized', 'on_hold', 'other'
    ))
);
CREATE UNIQUE INDEX eval_project_no_award_reasons_uniq
ON eval_project_no_award_reasons (project_id, reason);

-- Per-project access list (2026-10-17): an evaluation is private to its
-- creator (eval_projects.created_by, the implicit "owner" -- not a row
-- here) plus whoever the owner explicitly adds. user_id is NULL for a
-- brand-new teammate until they accept the invite (invite_id points at
-- the invites row created for them; accept_invite() backfills user_id +
-- accepted_at once they set a password). 'editor' can score/comment/add
-- vendors/close+reopen like an owner; 'commenter' can leave comments
-- (including a comment with no score -- see eval_scores.score below)
-- but can't change the official record; 'viewer' is read-only.
-- Projects created before this table existed were backfilled with every
-- buyer at the company as 'editor' (see migrate.py), matching exactly
-- what they could already do -- only NEW projects are private-by-default.
CREATE TABLE eval_project_collaborators (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES eval_projects(id),
    user_id INTEGER REFERENCES users(id),
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'commenter', 'editor')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    invite_id INTEGER REFERENCES invites(id),
    accepted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE UNIQUE INDEX eval_project_collaborators_uniq
ON eval_project_collaborators (project_id, email);

-- Supporting documents for a project (RFP responses, proposals, contract
-- drafts, etc.) -- a simple per-project file shelf, not tied to any one
-- vendor/criterion. Stored inline as a base64 data URL (data_url), same
-- approach as vendors.logo_upload_data_url and users.photo_data_url --
-- no object storage/volume to keep in sync (see migrate.py's project
-- facts for why volumes are avoided here). size_bytes is the original
-- (pre-base64) file size, enforced in app.py since a CHECK can't see the
-- decoded length. Anyone with access to the project (see
-- eval_project_collaborators above) can view/download; only the owner
-- and 'editor' collaborators can upload or remove one (app.py).
CREATE TABLE eval_project_artifacts (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES eval_projects(id),
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    data_url TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

-- A point-in-time PDF/Excel snapshot handed off via "Share via message"
-- on project_detail.html -- a copy of exactly what was checked in the
-- vendor/criteria picker at send time, never live access to the real
-- evaluation (which keeps changing after the share goes out). Same
-- inline-base64 storage as eval_project_artifacts above. thread_id/
-- message_id are the direct-message thread and the specific message
-- that announced it (an existing-buyer recipient, or a brand-new
-- external-email thread when they're not a BuyersForce member yet --
-- see get_or_create_external_thread); buyer_download_share gates on
-- thread participation alone, deliberately not on the project's own
-- access list, since the recipient usually has no role on the project
-- at all. Never shared with a seller/vendor contact (app.py enforces
-- that) -- an evaluation is competitive intelligence about vendors, and
-- one of them could be the recipient's own employer.
CREATE TABLE eval_project_shares (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES eval_projects(id),
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    message_id INTEGER NOT NULL REFERENCES messages(id),
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    data_url TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    shared_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    -- Mirrors the parent project's template_id (NULL when the project has
    -- no scorecard yet) -- kept in sync by buyer_start_project and
    -- buyer_project_update_meta. Nothing in app.py actually scores against
    -- this column (buyer_project_detail always reads the project's own
    -- template_id), so this is really just a legacy duplicate.
    template_id INTEGER REFERENCES eval_templates(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    company TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    -- Every evaluation belongs to exactly one project -- even a lone-vendor
    -- one, since a project is just "one or more vendors scored against the
    -- same template at the same time." This is what makes several vendors'
    -- rows render as columns of one shared scorecard instead of separate
    -- pages (buyer_project_detail in app.py).
    project_id INTEGER NOT NULL REFERENCES eval_projects(id),
    -- Free-text space for whatever the team found on Gartner Peer Insights --
    -- BF doesn't pull real review data from Gartner (see
    -- gartner_peer_insights_url() in app.py), this is a manually-typed
    -- reference note the team fills in themselves, surfaced back on Compare.
    gartner_peer_note TEXT NOT NULL DEFAULT '',
    -- The actual star number (out of 5) behind gartner_peer_note -- the
    -- note stays free text ("4.5/5 stars, 120 reviews"), but there's
    -- nothing to rank vendors by without a real number, so this is what
    -- project_detail.html's green/yellow Gartner highlight (gartner_rank
    -- in app.py) is computed from. NULL means no rating entered.
    gartner_rating REAL CHECK (gartner_rating IS NULL OR gartner_rating BETWEEN 0 AND 5),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    -- A buyer can pull a vendor out of the comparison entirely, even one
    -- that's already been scored (see buyer_project_vendor_action in
    -- app.py), unlike most "remove" actions here this one is NOT
    -- recoverable: that route deletes every eval_scores row tied to
    -- this evaluation when it sets removed_at, and project_detail.html
    -- warns the buyer of that before they confirm. NULL means still in
    -- the comparison. The row itself is kept (not deleted) so it can be
    -- reused -- adding the same vendor back clears these two columns
    -- instead of inserting a fresh row, but with a clean, scoreless
    -- slate since the history is really gone.
    removed_at TEXT,
    removed_by INTEGER REFERENCES users(id),
    -- A buyer's own gut-feel ranking of this vendor (1 = their first
    -- choice, 2 = second, etc.), entirely separate from -- and allowed to
    -- disagree with -- the weighted score computed from eval_scores.
    -- Set from the "Your pick" select on project_detail.html
    -- (buyer_project_set_vendor_rank in app.py), which can change it as
    -- often as the buyer likes. NULL means no preference set. Nothing
    -- enforces one vendor per rank -- two vendors can both be ranked #1
    -- if the buyer sets them that way.
    manual_rank INTEGER,
    -- Free-text rationale for manual_rank -- why the buyer ranked this
    -- vendor the way they did, independent of the weighted score. Same
    -- "Your pick" box, saved by the same route. Empty string, not NULL,
    -- to match gartner_peer_note's convention above.
    manual_rank_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE eval_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id),
    criterion_id INTEGER NOT NULL REFERENCES eval_criteria(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    -- Widened from the original 1-5 to the broadest scale any template can
    -- pick (see eval_templates.scale_max) -- the actual per-template
    -- ceiling is enforced in app.py's buyer_project_detail, not here.
    -- NULL (2026-10-17) means a 'commenter' collaborator left feedback on
    -- this cell without scoring it -- every average/overall calculation
    -- in app.py filters these out rather than treating them as a zero.
    score INTEGER CHECK (score IS NULL OR score BETWEEN 1 AND 10),
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
