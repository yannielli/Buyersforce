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
import json
import os
import urllib.error
import urllib.request

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "BuyersForce <onboarding@resend.dev>"


def send_email(to_email, subject, text):
    """Best-effort send. Returns True only on a confirmed successful
    send; False (logged) for anything else, including "not configured
    yet" -- callers should treat False as "message saved, but nobody
    was actually emailed" rather than raising."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"[emailer] RESEND_API_KEY not set -- not emailing {to_email}: {subject!r}")
        return False

    from_addr = os.environ.get("EMAIL_FROM", DEFAULT_FROM)
    payload = json.dumps({
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": text,
    }).encode("utf-8")
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


def send_message_notification(to_email, sender, body):
    """Notifies someone who isn't a BuyersForce member yet that a member
    sent them a message. sender is a users row (dict-like)."""
    subject = f"{sender['name']} sent you a message on BuyersForce"
    text = (
        f"{sender['name']} ({sender['company']}) sent you a message through BuyersForce:\n\n"
        f"\"{body}\"\n\n"
        f"BuyersForce is an invite-only platform connecting technology buyers and vendors. "
        f"You don't have an account yet, so the fastest way to reply is directly to "
        f"{sender['email']}. If {sender['name']} invites you to BuyersForce, you'll be able "
        f"to reply from within the app instead."
    )
    return send_email(to_email, subject, text)
