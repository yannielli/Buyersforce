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

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('buyer','seller','admin')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

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

CREATE TABLE vendors (
    id SERIAL PRIMARY KEY,
    seller_user_id INTEGER NOT NULL REFERENCES users(id),
    company_name TEXT NOT NULL,
    category TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    accent TEXT NOT NULL DEFAULT '#2a78d6',
    initials TEXT NOT NULL DEFAULT 'VN',
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
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
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(buyer_user_id, vendor_id)
);

-- A thread is always initiated by a buyer. type distinguishes vendor conversations
-- from internal teammate / partner conversations.
CREATE TABLE threads (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('vendor','teammate','partner')),
    buyer_user_id INTEGER REFERENCES users(id),
    vendor_id INTEGER REFERENCES vendors(id),
    subject TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

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
