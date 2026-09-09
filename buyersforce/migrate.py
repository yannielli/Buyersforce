"""
Incremental schema migrations for BuyersForce (PostgreSQL).

schema.sql only ever runs against a brand-new, empty database (seed.py
skips it once real data exists), so a change that needs to reach the
LIVE database has to happen here instead, as an idempotent migration
that's safe to run on every deploy. start.sh runs this once, in a single
process, before gunicorn starts any workers -- so there's no risk of two
workers racing to add the same column.

Every statement below is written to be safe to run repeatedly: CREATE
TABLE/INDEX IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, and a constraint
check that only touches the DB when the constraint actually needs
widening.
"""
import json
import os

import psycopg2

from db import _database_url


def run_migrations():
    con = psycopg2.connect(_database_url())
    con.autocommit = True
    try:
        with con.cursor() as cur:
            _add_contacts_table(cur)
            _add_direct_messaging_columns(cur)
            _widen_thread_type_check(cur)
            _add_thread_reads_table(cur)
            _add_profile_columns(cur)
            _add_blocked_vendors_table(cur)
            _add_account_status_and_photo(cur)
            _backfill_demo_profiles(cur)
            _add_phone_country_and_role_requests(cur)
            _migrate_legacy_timezones(cur)
            _add_vendor_directory_columns(cur)
            _seed_vendor_directory(cur)
    finally:
        con.close()


def _add_contacts_table(cur):
    # A per-user personal address book. A row with contact_user_id set is
    # a fellow BuyersForce member; a row with external_email set instead
    # is someone reached by email who isn't a member (yet). Rows are
    # added automatically the first time two people message each other.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            contact_user_id INTEGER REFERENCES users(id),
            external_name TEXT,
            external_email TEXT,
            created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS contacts_owner_contact_uniq
        ON contacts (owner_user_id, contact_user_id)
        WHERE contact_user_id IS NOT NULL
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS contacts_owner_external_email_uniq
        ON contacts (owner_user_id, external_email)
        WHERE contact_user_id IS NULL AND external_email IS NOT NULL
        """
    )


def _add_direct_messaging_columns(cur):
    # New columns on threads supporting 1:1 "direct" conversations --
    # teammate-to-teammate, or a message to someone who isn't a member
    # yet (participant_b_id stays NULL and external_name/email carry
    # who it's for). The existing 'vendor' and 'teammate' thread shapes
    # are untouched.
    for ddl in (
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS participant_a_id INTEGER REFERENCES users(id)",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS participant_b_id INTEGER REFERENCES users(id)",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS external_name TEXT",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS external_email TEXT",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS pending_email_sent_at TEXT",
    ):
        cur.execute(ddl)


def _widen_thread_type_check(cur):
    # Find whichever CHECK constraint governs threads.type (Postgres
    # auto-names it, and we'd rather not guess) and, if it doesn't
    # already allow 'direct', replace it with one that does.
    cur.execute(
        """
        SELECT con.conname, pg_get_constraintdef(con.oid) AS def
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'threads' AND con.contype = 'c'
        """
    )
    for conname, condef in cur.fetchall():
        if "'vendor'" in condef and "type" in condef and "'direct'" not in condef:
            cur.execute(f'ALTER TABLE threads DROP CONSTRAINT "{conname}"')
            cur.execute(
                "ALTER TABLE threads ADD CONSTRAINT threads_type_check "
                "CHECK (type IN ('vendor','teammate','partner','direct'))"
            )


def _add_thread_reads_table(cur):
    # Tracks the highest message id each user has seen in each thread, so
    # we can show an unread-messages badge. Deliberately a message-id
    # cursor rather than a timestamp: this app's timestamps only have
    # one-second resolution, so a message posted in the same second as a
    # "mark as read" could otherwise tie and be miscounted as read.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_reads (
            user_id INTEGER NOT NULL REFERENCES users(id),
            thread_id INTEGER NOT NULL REFERENCES threads(id),
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, thread_id)
        )
        """
    )


def _add_profile_columns(cur):
    # Mandatory profile fields (first/last name, a personal backup email,
    # phone, US state, job title) plus optional ones (address, secondary
    # phone, LinkedIn, timezone) and, for buyers only, the "Open to Buy"
    # signal. `title` already existed but was never surfaced in the UI.
    # Completeness is computed on the fly from these columns (see
    # profile_is_complete() in app.py) rather than tracked with a separate
    # flag, so there's nothing here that can drift out of sync.
    for ddl in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS personal_email TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS state TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line1 TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line2 TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS zip TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS secondary_phone TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS linkedin_url TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS no_linkedin INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS open_to_buy INTEGER NOT NULL DEFAULT 0",
    ):
        cur.execute(ddl)

    # Our seeded seller accounts are named "<Company> Team" (there's no
    # single point-of-contact yet), so the generic split below would give
    # them a nonsense name like first="Aegis" / last="Shield Team". Give
    # these specific demo accounts a real-looking person name first.
    # COALESCE means this never overwrites a name someone's since edited.
    demo_seller_names = {
        "sam@aegisshield.io": ("Sam", "Rios"),
        "jen@ironcladid.com": ("Jen", "Park"),
        "omar@sentinelgrid.ai": ("Omar", "Haddad"),
        "lee@vaultstream.com": ("Lee", "Nguyen"),
    }
    for email, (first, last) in demo_seller_names.items():
        cur.execute(
            """
            UPDATE users SET
                first_name = COALESCE(first_name, %s),
                last_name = COALESCE(last_name, %s)
            WHERE email = %s
            """,
            (first, last, email),
        )

    # Best-effort backfill so existing accounts aren't staring at a
    # completely blank name when they hit the new profile screen -- split
    # the existing single `name` field on the first space. Only touches
    # rows that don't have a first_name yet, so it's safe to re-run.
    cur.execute(
        """
        UPDATE users SET
            first_name = COALESCE(first_name, split_part(name, ' ', 1)),
            last_name = COALESCE(last_name, NULLIF(substring(name FROM position(' ' IN name) + 1), ''))
        WHERE first_name IS NULL
        """
    )


def _add_blocked_vendors_table(cur):
    # A buyer-owned blocklist: a row with blocked_user_id set targets a
    # specific known seller account; blocked_email targets someone by
    # email even if they're not (yet) associated with that row's company;
    # blocked_company blocks every seller at a vendor company, present or
    # future. At least one of the three must be set. Enforced in
    # _can_message() and wherever a seller posts into an existing thread.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS blocked_vendors (
            id SERIAL PRIMARY KEY,
            buyer_user_id INTEGER NOT NULL REFERENCES users(id),
            blocked_user_id INTEGER REFERENCES users(id),
            blocked_email TEXT,
            blocked_company TEXT,
            created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
            CHECK (blocked_user_id IS NOT NULL OR blocked_email IS NOT NULL OR blocked_company IS NOT NULL)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS blocked_vendors_buyer_user_uniq
        ON blocked_vendors (buyer_user_id, blocked_user_id)
        WHERE blocked_user_id IS NOT NULL
        """
    )


def _add_account_status_and_photo(cur):
    # account_status gates self-signup: an admin-invited account is
    # 'active' immediately (unchanged behavior), while a self-signup
    # request starts 'pending' and can't log in until an admin approves
    # it (or is permanently blocked via 'denied'). photo_data_url holds
    # an uploaded profile photo as a data: URL -- stored in the database
    # rather than on disk, since Railway's filesystem doesn't persist
    # across deploys. NULL means "use the initials avatar" everywhere the
    # app already draws one.
    for ddl in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_data_url TEXT",
    ):
        cur.execute(ddl)
    cur.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'users_account_status_check'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT users_account_status_check
                CHECK (account_status IN ('pending', 'active', 'denied'));
            END IF;
        END $$;
        """
    )


def _backfill_demo_profiles(cur):
    # Realistic-looking fake profile data for the seeded demo accounts, so
    # testing isn't blocked staring at a blank mandatory-profile screen.
    # Only fills columns that are still NULL, so it never overwrites a
    # real edit made after this ran. Real (non-demo) accounts are
    # untouched since their emails won't match this list.
    demo_profiles = {
        "dana@meridianhealth.com": ("dwhitfield.personal@gmail.com", "(617) 555-0142", "MA", "Eastern"),
        "priya@meridianhealth.com": ("priya.kapoor.pk@gmail.com", "(617) 555-0198", "MA", "Eastern"),
        "marcus@meridianhealth.com": ("marcus.ide.mi@gmail.com", "(617) 555-0173", "MA", "Eastern"),
        "grace@northwindbank.com": ("grace.lin.gl@gmail.com", "(312) 555-0110", "IL", "Central"),
        "tomas@northwindbank.com": ("tomas.reyes.tr@gmail.com", "(312) 555-0187", "IL", "Central"),
        "sam@aegisshield.io": ("sam.rios.sr@gmail.com", "(415) 555-0134", "CA", "Pacific"),
        "jen@ironcladid.com": ("jen.park.jp@gmail.com", "(512) 555-0121", "TX", "Central"),
        "omar@sentinelgrid.ai": ("omar.haddad.oh@gmail.com", "(212) 555-0199", "NY", "Eastern"),
        "lee@vaultstream.com": ("lee.nguyen.ln@gmail.com", "(206) 555-0156", "WA", "Pacific"),
    }
    for email, (personal_email, phone, state, timezone) in demo_profiles.items():
        cur.execute(
            """
            UPDATE users SET
                personal_email = COALESCE(personal_email, %s),
                phone = COALESCE(phone, %s),
                state = COALESCE(state, %s),
                timezone = COALESCE(timezone, %s)
            WHERE email = %s
            """,
            (personal_email, phone, state, timezone, email),
        )


def _add_phone_country_and_role_requests(cur):
    # Phone numbers now carry which country's dial code/format they use
    # (defaults to 'US' since that's been the only shape phone numbers have
    # taken so far -- existing rows are all US, correctly left alone by
    # this default). Also adds a lightweight approval queue for a buyer or
    # seller who thinks their account type is wrong and wants a BF admin to
    # fix it -- role itself stays admin-only to change directly.
    for ddl in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_country TEXT NOT NULL DEFAULT 'US'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS secondary_phone_country TEXT",
    ):
        cur.execute(ddl)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS role_change_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            previous_role TEXT NOT NULL,
            requested_role TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
            created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
            resolved_at TEXT,
            resolved_by INTEGER REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS role_change_requests_one_pending_uniq
        ON role_change_requests (user_id)
        WHERE status = 'pending'
        """
    )


def _migrate_legacy_timezones(cur):
    # The time zone field started out as six US-only labels
    # ("Eastern".."Hawaii") before the picker became worldwide (real IANA
    # zone names like "America/New_York"). Translate any rows still
    # holding an old label to its IANA equivalent so existing users see
    # their zone correctly selected instead of the field going blank.
    # Idempotent: once migrated, a row's value no longer matches any of
    # these old labels, so re-running this is a no-op for it.
    legacy_map = {
        "Eastern": "America/New_York",
        "Central": "America/Chicago",
        "Mountain": "America/Denver",
        "Pacific": "America/Los_Angeles",
        "Alaska": "America/Anchorage",
        "Hawaii": "Pacific/Honolulu",
    }
    for old_value, new_value in legacy_map.items():
        cur.execute(
            "UPDATE users SET timezone = %s WHERE timezone = %s", (new_value, old_value)
        )


def _add_vendor_directory_columns(cur):
    # Supports the admin-seeded cybersecurity vendor directory: a bigger
    # LinkedIn-About-page-style set of demographic fields on vendors, plus
    # a controlled multi-select segment/category system (vendor_segments)
    # separate from the freeform vendor_tags a seller can already type.
    # seller_user_id is relaxed to nullable so an admin-seeded ("unclaimed")
    # vendor can exist with no real seller account behind it yet.
    cur.execute("ALTER TABLE vendors ALTER COLUMN seller_user_id DROP NOT NULL")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS company_size TEXT")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS founded_year INTEGER")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS hq_location TEXT")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS contact_email TEXT")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS contact_phone TEXT")
    cur.execute("ALTER TABLE vendors ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT ''")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS vendors_seeded_company_name_uniq
        ON vendors (company_name)
        WHERE seller_user_id IS NULL
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vendor_segments (
            id SERIAL PRIMARY KEY,
            vendor_id INTEGER NOT NULL REFERENCES vendors(id),
            segment TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS vendor_segments_vendor_segment_uniq
        ON vendor_segments (vendor_id, segment)
        """
    )


# Chart palette from static/css/style.css's --series-1..5 tokens, reused
# here so admin-seeded vendor badges pick up the same brand colors instead
# of defaulting to a single blue for all 241+ of them.
_SEED_ACCENT_PALETTE = ["#3b82f6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"]


def _seed_vendor_directory(cur):
    # One-time (idempotent) load of a curated, admin-editable cybersecurity
    # vendor directory compiled from free public sources -- GitHub's
    # awesome-cybersecurity list, CB Insights market-map articles, and
    # Momentum Cyber's Cybersecurity Almanac (Gartner has no usable API at
    # any price point, so it isn't a source here). See
    # seed_data/vendor_seed_list.json for the compiled data and its
    # per-entry "source" field for provenance.
    #
    # These rows are admin-curated "unclaimed" listings (seller_user_id IS
    # NULL) meant to pre-populate the directory before real vendors sign
    # up. A future "claim this listing" flow (tracked separately, not
    # built yet) will let a verified rep from that company take over
    # editing rights -- for now these are read-only to buyers and editable
    # only by an admin.
    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data", "vendor_seed_list.json")
    if not os.path.exists(seed_path):
        return
    with open(seed_path) as f:
        seed_vendors = json.load(f)

    for i, entry in enumerate(seed_vendors):
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        cur.execute(
            "SELECT id FROM vendors WHERE company_name = %s AND seller_user_id IS NULL",
            (name,),
        )
        row = cur.fetchone()
        if row:
            vendor_id = row[0]
        else:
            categories = entry.get("categories") or []
            initials = "".join(w[0] for w in name.split()[:2]).upper()[:3] or "VN"
            accent = _SEED_ACCENT_PALETTE[i % len(_SEED_ACCENT_PALETTE)]
            cur.execute(
                """
                INSERT INTO vendors (
                    seller_user_id, company_name, category, tagline, description,
                    website, accent, initials, company_size, source
                ) VALUES (NULL, %s, %s, '', %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    name,
                    categories[0] if categories else "Uncategorized",
                    entry.get("description") or "",
                    entry.get("website") or "",
                    accent,
                    initials,
                    entry.get("company_size"),
                    entry.get("source") or "",
                ),
            )
            vendor_id = cur.fetchone()[0]

        for segment in entry.get("categories") or []:
            cur.execute(
                "SELECT 1 FROM vendor_segments WHERE vendor_id = %s AND segment = %s",
                (vendor_id, segment),
            )
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO vendor_segments (vendor_id, segment) VALUES (%s, %s)",
                    (vendor_id, segment),
                )


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied.")
