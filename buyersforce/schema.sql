-- BuyersForce schema

DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS vendors;
DROP TABLE IF EXISTS listings;
DROP TABLE IF EXISTS listing_features;
DROP TABLE IF EXISTS vendor_tags;
DROP TABLE IF EXISTS shortlist;
DROP TABLE IF EXISTS threads;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS meetings;
DROP TABLE IF EXISTS eval_templates;
DROP TABLE IF EXISTS eval_criteria;
DROP TABLE IF EXISTS evaluations;
DROP TABLE IF EXISTS eval_scores;
DROP TABLE IF EXISTS partner_contacts;
DROP TABLE IF EXISTS activity_log;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('buyer','seller')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_user_id INTEGER NOT NULL REFERENCES users(id),
    company_name TEXT NOT NULL,
    category TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    accent TEXT NOT NULL DEFAULT '#2a78d6',
    initials TEXT NOT NULL DEFAULT 'VN',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    pricing_model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE listing_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    feature_text TEXT NOT NULL
);

CREATE TABLE vendor_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    tag TEXT NOT NULL
);

CREATE TABLE shortlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    status TEXT NOT NULL DEFAULT 'discovered' CHECK (status IN ('discovered','evaluating','shortlisted','selected','passed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(buyer_user_id, vendor_id)
);

-- A thread is always initiated by a buyer. type distinguishes vendor conversations
-- from internal teammate / partner conversations.
CREATE TABLE threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('vendor','teammate','partner')),
    buyer_user_id INTEGER REFERENCES users(id),
    vendor_id INTEGER REFERENCES vendors(id),
    subject TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    sender_user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    proposed_time TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','confirmed','declined')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE eval_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    company TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_shared INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE eval_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES eval_templates(id),
    label TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES eval_templates(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    company TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE eval_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id),
    criterion_id INTEGER NOT NULL REFERENCES eval_criteria(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(evaluation_id, criterion_id, user_id)
);

CREATE TABLE partner_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    org TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Alliance Partner',
    email TEXT NOT NULL DEFAULT ''
);

CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    verb TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
