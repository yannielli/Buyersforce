# CLAUDE.md — BuyersForce project guide

## How to communicate with Kevin

- Use layman's terms. No unexplained jargon — Kevin is the product owner, not a programmer.
- Keep it concise. Get to the heart of the matter first; add detail only when asked.
- When something breaks, lead with what it means for the product and what the fix is, not the technical play-by-play.
- When Kevin needs to do something (like commit files on GitHub), give short, numbered, click-by-click steps.

## Project facts

- BuyersForce: invite-only web app for technology buyers, live at
  https://buyersforce-web-production.up.railway.app
- Code lives in GitHub repo `yannielli/buyersforce`, in the `buyersforce/` folder.
  Claude commits and pushes file changes directly (via the `claude-ssh` deploy-key remote --
  see the daily backup routine for how it's set up); every push to `main` auto-deploys on
  Railway. (Before 2026-10-15, Kevin committed changes himself through the GitHub website --
  he can still ask Claude to show a diff before pushing if he wants to double check something.)
- Database: Railway's managed Postgres (service "Postgres" in the `buyersforce` project).
  Do NOT switch back to SQLite or Railway volumes — volumes had an unresolved data-wiping bug.
- Kevin is the admin account. One email = one role (buyer, seller, or admin);
  he uses separate email addresses to test buyer and seller views.
- seed.py only seeds an empty database, so real data survives redeploys. Never break that guard.

## Project history (read this first in a new chat)

Claude does not carry memory between chats -- only this file and git history
do. `git log` has the full detailed record (commit messages are written to
stand alone); this is the short version so a new chat knows the lay of the
land in one read, without Kevin having to re-explain months of context.

- **Buyer directory & discovery**: vendor directory with category/segment/
  company-size/technology-category filters, A-Z letter jump, admin CRUD for
  vendors/buyers/sellers. "Ask Frankie" AI directory assistant (renamed from
  "Bob") searches BuyersForce first, offers a web search as a deliberate
  second step, and can submit a new vendor suggestion.
- **Compare**: check vendors on Discover (or pull them in from an Ask
  Frankie result) to compare side-by-side; move up to a few into Evaluate's
  shortlist from there. (2026-10-17: compare selections now persist across
  Discover's letter/search/filter page reloads via a small cross-page tray,
  instead of resetting every time the page reloaded -- see "Known rough
  edges" below for what's still basic about it.)
- **Evaluations**: shared, reusable scorecard templates (configurable 1-5 /
  1-10 rating scale per template), collaborative scoring, weighted overall
  score, Gartner Peer Insights notes. A project can add criteria/vendors
  after scoring has started, and can be closed (with an outcome: selected
  vendor, or no award + reasons) and reopened -- nothing is ever deleted, so
  historical scores always point at something real.
- **Messaging, meetings, admin**: direct + vendor threads, meeting
  scheduling, support requests, invite-only signup with configurable invite
  expiration, an Admin Dashboard split out from Access Control.
- **Infra**: Claude pushes directly to `main` via the `claude-ssh` deploy-key
  remote (since 2026-10-15); every push auto-deploys on Railway. Database is
  Railway's managed Postgres -- never SQLite or Railway volumes (data-wiping
  bug, unresolved, don't revisit).

Known rough edges worth remembering, not yet fixed:
- The cross-page compare tray (above) is client-side/localStorage only --
  it doesn't sync across devices or browsers, and a cleared browser profile
  loses it. Fine for now; revisit only if Kevin asks for it to be shared/
  synced.
