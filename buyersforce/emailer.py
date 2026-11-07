"""
Outbound transactional email, via Resend (https://resend.com).

BuyersForce can't send any email until RESEND_API_KEY is set as an
environment variable (Railway -> buyersforce-web -> Variables). Until
then, send_email() logs what it would have sent and returns False --
it never pretends to succeed. Once a key is set, sending just works;
no code changes needed.

Resend's free tier covers this comfortably to start, and its default
sender (onboarding@resend.dev) works with no domain setup -- useful to
get real delivery working today. Sending from your own address (e.g.
notifications@buyersforce.io) means verifying that domain with Resend
first and setting EMAIL_FROM to it.
"""
import base64
import html as html_lib
import json
import os
import urllib.error
import urllib.request

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "BuyersForce <onboarding@resend.dev>"


def send_email(to_email, subject, text, reply_to=None, html=None, attachments=None, from_override=None):
    """Best-effort send. Returns True only on a confirmed successful
    send; False (logged) for anything else, including "not configured
    yet" -- callers should treat False as "message saved, but nobody
    was actually emailed" rather than raising.

    from_override, when given, replaces the display name on the "from"
    header for just this one send (e.g. "Frankie (BuyersForce AI
    Assistant) <...>" for an alert she's the one sending) while keeping
    the SAME underlying mailbox every other BuyersForce email uses --
    Resend only accepts a verified address/domain, so this is never a
    way to send from somewhere else, just a friendlier display name.
    See _frankie_from_addr below.

    reply_to, when given, is where a reply should land. BuyersForce's
    sending address (EMAIL_FROM) is send-only -- there's no inbox behind
    it, so a reply sent there bounces with "address not found". Setting
    reply_to makes a recipient's own "Reply" button do the right thing
    instead of relying on them to notice and retype an address.

    html, when given, is sent alongside text -- most email apps show it
    instead of the plain-text version, so it's the one that can carry
    styling (e.g. distinguishing BuyersForce's own note from the
    sender's message). Recipients whose email app can't render HTML
    still get the plain text.

    attachments, when given, is a list of {"filename", "content_bytes",
    "content_type"} dicts -- raw bytes, never pre-encoded, since this is
    the one place that talks to Resend's actual wire format (base64
    strings, no content_type field at all -- Resend infers it from the
    filename extension).
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"[emailer] RESEND_API_KEY not set -- not emailing {to_email}: {subject!r}")
        return False

    from_addr = from_override or os.environ.get("EMAIL_FROM", DEFAULT_FROM)
    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = [reply_to]
    if attachments:
        payload["attachments"] = [
            {
                "filename": a["filename"],
                "content": base64.b64encode(a["content_bytes"]).decode("ascii"),
            }
            for a in attachments
        ]
    payload = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Resend's API sits behind Cloudflare, which blocks Python's
            # default "Python-urllib/x.y" user agent as a bot signature
            # (HTTP 403, Cloudflare error 1010). A normal-looking user
            # agent avoids that.
            "User-Agent": "BuyersForce/1.0 (+https://buyersforce.io)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print(f"[emailer] Resend rejected the email to {to_email}: {e.code} {e.read()[:300]}")
        return False
    except urllib.error.URLError as e:
        print(f"[emailer] Could not reach Resend for {to_email}: {e}")
        return False


def send_message_notification(to_email, sender, body, signup_url):
    """Notifies someone who isn't a BuyersForce member yet that a member
    sent them a message. sender is a users row (dict-like). signup_url
    is where they can go to request their own BuyersForce account.

    The BuyersForce-authored note (as opposed to the sender's own
    message) is styled in teal in the HTML version, so it's visually
    obvious which part a person actually typed and which part is the
    platform talking.
    """
    subject = f"{sender['name']} sent you a message on BuyersForce"
    note = (
        f"BuyersForce is an invite-only platform connecting technology buyers and vendors. "
        f"You don't have an account yet, so just hit reply and it'll go straight to "
        f"{sender['name']}. Want an account of your own? Request access here: {signup_url}"
    )
    text = (
        f"{sender['name']} ({sender['company']}) sent you a message through BuyersForce:\n\n"
        f"\"{body}\"\n\n"
        f"{note}"
    )
    html = (
        f"<p>{html_lib.escape(sender['name'])} ({html_lib.escape(sender['company'])}) sent you "
        f"a message through BuyersForce:</p>"
        f"<blockquote style=\"margin:0 0 16px; padding:8px 12px; border-left:3px solid #ccc; "
        f"color:#111;\">{html_lib.escape(body)}</blockquote>"
        f"<p style=\"color:teal; font-style:italic;\">BuyersForce is an invite-only platform "
        f"connecting technology buyers and vendors. You don't have an account yet, so just hit "
        f"reply and it'll go straight to {html_lib.escape(sender['name'])}. Want an account of "
        f"your own? <a href=\"{html_lib.escape(signup_url)}\" style=\"color:teal;\">Request "
        f"access here</a>.</p>"
    )
    return send_email(to_email, subject, text, reply_to=sender["email"], html=html)


def send_evaluation_share(to_email, sender, project_name, note, file_bytes, filename, content_type):
    """Notifies someone who isn't a BuyersForce member yet that a buyer
    shared an evaluation snapshot with them -- mirrors
    send_message_notification, but the point of this one IS the
    attachment (the recipient has no account to log in and click a
    download link with, unlike an existing member, who gets the same
    file as a link in their BuyersForce Messages instead -- see
    buyer_project_share/buyer_download_share in app.py). note is the
    optional free-text message the sender added; content_type is unused
    here (Resend infers it from filename) but kept for a consistent call
    shape with the rest of this module.
    """
    subject = f"{sender['name']} shared a BuyersForce evaluation with you: {project_name}"
    note_block = f'\n\n"{note}"' if note else ""
    text = (
        f"{sender['name']} ({sender['company']}) shared a snapshot of their \"{project_name}\" "
        f"evaluation on BuyersForce -- see the attached {filename}.{note_block}\n\n"
        f"This is a point-in-time copy, not live access to their evaluation -- it won't update if "
        f"they change anything later.\n\n"
        f"BuyersForce is an invite-only platform connecting technology buyers and vendors. You "
        f"don't have an account yet, so just hit reply and it'll go straight to {sender['name']}."
    )
    note_html = (
        f"<blockquote style=\"margin:12px 0; padding:8px 12px; border-left:3px solid #ccc; "
        f"color:#111;\">{html_lib.escape(note)}</blockquote>"
    ) if note else ""
    html = (
        f"<p>{html_lib.escape(sender['name'])} ({html_lib.escape(sender['company'])}) shared a "
        f"snapshot of their <strong>{html_lib.escape(project_name)}</strong> evaluation on "
        f"BuyersForce -- see the attached {html_lib.escape(filename)}.</p>"
        f"{note_html}"
        f"<p style=\"color:#666; font-size:13px;\">This is a point-in-time copy, not live access "
        f"to their evaluation -- it won't update if they change anything later.</p>"
        f"<p style=\"color:teal; font-style:italic;\">BuyersForce is an invite-only platform "
        f"connecting technology buyers and vendors. You don't have an account yet, so just hit "
        f"reply and it'll go straight to {html_lib.escape(sender['name'])}.</p>"
    )
    return send_email(
        to_email, subject, text, reply_to=sender["email"], html=html,
        attachments=[{"filename": filename, "content_bytes": file_bytes}],
    )


def send_signup_decision(to_email, approved, login_url=None):
    """Notifies someone who requested a BuyersForce account (self-signup,
    pending admin review) of the outcome. Kept deliberately brief and
    generic on denial -- no need to spell out exactly why."""
    if approved:
        subject = "Your BuyersForce account is approved"
        text = f"Good news -- your BuyersForce account request has been approved.\n\nLog in here: {login_url}"
        html = (
            f"<p>Good news — your BuyersForce account request has been approved.</p>"
            f"<p><a href=\"{html_lib.escape(login_url or '')}\">Log in to BuyersForce</a></p>"
        )
    else:
        subject = "Your BuyersForce account request"
        text = (
            "Thanks for your interest in BuyersForce. After review, we're not able to "
            "approve your account request at this time."
        )
        html = f"<p>{html_lib.escape(text)}</p>"
    return send_email(to_email, subject, text, html=html)


def send_role_change_decision(to_email, approved, new_role=None, login_url=None):
    """Notifies someone who asked to switch between buyer and seller (via
    the "Request a change" button on Account > Profile) of the outcome,
    mirroring send_signup_decision."""
    if approved:
        subject = "Your BuyersForce account type has been updated"
        text = f"Your BuyersForce account is now set up as a {new_role}.\n\nLog in here: {login_url}"
        html = (
            f"<p>Your BuyersForce account is now set up as a "
            f"<strong>{html_lib.escape(new_role or '')}</strong>.</p>"
            f"<p><a href=\"{html_lib.escape(login_url or '')}\">Log in to BuyersForce</a></p>"
        )
    else:
        subject = "Your BuyersForce account type request"
        text = (
            "Thanks for letting us know. After review, we're leaving your BuyersForce account "
            "type as-is for now -- reach out if you'd like to discuss."
        )
        html = f"<p>{html_lib.escape(text)}</p>"
    return send_email(to_email, subject, text, html=html)


def _frankie_from_addr():
    """The display name used on the handful of alerts Frankie (BuyersForce's
    AI assistant) sends herself -- the AI support-ticket agent's "new
    ticket, here's my suggested resolution" alert to Kj (see
    send_support_ticket_alert below). Keeps the exact SAME underlying
    mailbox every other BuyersForce email already sends from (DEFAULT_FROM,
    or EMAIL_FROM once a custom domain is verified with Resend) --
    Resend rejects a "from" address that isn't verified, so this only
    ever changes the friendly display name in front of it, never the
    actual address.
    """
    base = os.environ.get("EMAIL_FROM", DEFAULT_FROM)
    if "<" in base and ">" in base:
        addr = base[base.index("<") + 1: base.index(">")]
    else:
        addr = base.strip()
    return f"Frankie (BuyersForce AI Assistant) <{addr}>"


def send_support_ticket_alert(
    to_email, requester, reference_number, category_label, headline, resolution,
    suggested_status, dashboard_url,
):
    """Sent to Kj the moment a new support ticket is submitted and Frankie
    has drafted a suggested resolution for it (run_support_triage in
    ai_assistant.py, called from support_new in app.py) -- the external
    alert for Kj's "AI support ticket agent" ask. Branded as coming from
    Frankie herself (_frankie_from_addr), since she's the one who
    triaged it -- not a generic system notice. Always links straight to
    the admin dashboard, where the actual approve/modify/reject/defer
    decision happens; this email is a heads-up, never itself the place
    the decision gets made (no "reply to approve" affordance -- that
    would mean trusting an email reply body as an admin action, which
    this never does).

    requester is a users row (dict-like); headline and resolution are
    the two text fields of run_support_triage's result; suggested_status
    is one of 'open'/'in_progress'/'resolved'.
    """
    status_label = {"open": "Open", "in_progress": "In progress", "resolved": "Resolved"}.get(
        suggested_status, suggested_status
    )
    subject = f"New ticket #BF-{reference_number}: {headline or category_label}"
    text = (
        f"{requester['name']} ({requester['company']}) submitted a {category_label.lower()} "
        f"ticket (#BF-{reference_number}).\n\n"
        f"I've drafted a suggested reply:\n\n"
        f"\"{resolution}\"\n\n"
        f"My recommended status if you approve it as-is: {status_label}.\n\n"
        f"Review, edit, or decide on it here: {dashboard_url}\n\n"
        f"-- Frankie"
    )
    html = (
        f"<p>{html_lib.escape(requester['name'])} ({html_lib.escape(requester['company'])}) submitted a "
        f"{html_lib.escape(category_label.lower())} ticket (<strong>#BF-{reference_number}</strong>).</p>"
        f"<p>I've drafted a suggested reply:</p>"
        f"<blockquote style=\"margin:0 0 16px; padding:8px 12px; border-left:3px solid #17948f; "
        f"color:#111;\">{html_lib.escape(resolution)}</blockquote>"
        f"<p>My recommended status if you approve it as-is: <strong>{html_lib.escape(status_label)}</strong>.</p>"
        f"<p><a href=\"{html_lib.escape(dashboard_url)}\" style=\"color:#17948f; font-weight:600;\">Review it on "
        f"your BuyersForce dashboard &rarr;</a></p>"
        f"<p style=\"color:#888; font-size:13px; font-style:italic;\">-- Frankie</p>"
    )
    return send_email(to_email, subject, text, html=html, from_override=_frankie_from_addr())


def send_member_message_alert(to_email, sender, body, thread_url):
    """A fellow BuyersForce member's "you have a new message" email --
    mirrors send_message_notification above (which is for someone who
    isn't a member yet), generalized to members too (Kj's "notify me or
    any user of a message" ask -- see notify_new_message in app.py,
    which throttles how often this actually fires per thread so an
    active back-and-forth doesn't flood anyone's inbox). Unlike the
    non-member version, there's no signup pitch and no reply-to-this-
    email affordance -- the recipient already has a real account, so
    the only call to action is to go look at it in BuyersForce itself.
    Deliberately NOT Frankie-branded (plain BuyersForce, like every
    other non-AI system email) -- Frankie's own voice is reserved for
    the support-ticket alert above, which she actually triaged.
    """
    subject = f"{sender['name']} sent you a message on BuyersForce"
    text = (
        f"{sender['name']} ({sender['company']}) sent you a message on BuyersForce:\n\n"
        f"\"{body}\"\n\n"
        f"Reply here: {thread_url}"
    )
    html = (
        f"<p>{html_lib.escape(sender['name'])} ({html_lib.escape(sender['company'])}) sent you a message on "
        f"BuyersForce:</p>"
        f"<blockquote style=\"margin:0 0 16px; padding:8px 12px; border-left:3px solid #ccc; "
        f"color:#111;\">{html_lib.escape(body)}</blockquote>"
        f"<p><a href=\"{html_lib.escape(thread_url)}\" style=\"color:teal; font-weight:600;\">Reply on "
        f"BuyersForce &rarr;</a></p>"
    )
    return send_email(to_email, subject, text, html=html)
