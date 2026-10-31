# CLAUDE.md — BuyersForce project guide

## How to communicate with Kj

- Address him as "Kj," not "Kevin" (his full name is Kevin Jackson, but he goes by Kj).
- Use layman's terms. No unexplained jargon — Kj is the product owner, not a programmer.
- Keep it concise. Get to the heart of the matter first; add detail only when asked.
- When something breaks, lead with what it means for the product and what the fix is, not the technical play-by-play.
- When Kj needs to do something (like commit files on GitHub), give short, numbered, click-by-click steps.

## Project facts

- BuyersForce: invite-only web app for technology buyers, live at
  https://buyersforce-web-production.up.railway.app
- Code lives in GitHub repo `yannielli/buyersforce`, in the `buyersforce/` folder.
  Claude commits and pushes file changes directly (via the `claude-ssh` deploy-key remote --
  see the daily backup routine for how it's set up); every push to `main` auto-deploys on
  Railway. (Before 2026-10-15, Kj committed changes himself through the GitHub website --
  he can still ask Claude to show a diff before pushing if he wants to double check something.)
- Database: Railway's managed Postgres (service "Postgres" in the `buyersforce` project).
  Do NOT switch back to SQLite or Railway volumes — volumes had an unresolved data-wiping bug.
- Kj is the admin account. One email = one role (buyer, seller, or admin);
  he uses separate email addresses to test buyer and seller views.
- seed.py only seeds an empty database, so real data survives redeploys. Never break that guard.

## Project history (read this first in a new chat)

Claude does not carry memory between chats -- only this file and git history
do. `git log` has the full detailed record (commit messages are written to
stand alone); this is the short version so a new chat knows the lay of the
land in one read, without Kj having to re-explain months of context.

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
- **Frankie's visual identity** (2026-10-31): custom mascot artwork (Kj's
  ChatGPT-generated character, torso-up on transparent PNGs, pre-cropped to
  head/shoulders) wired in as `.frankie-avatar` -- the launcher button, both
  panel headers, and every assistant chat row in Discover's floating panel
  and the Build-with-Frankie wizard's embedded panels, swapped by mood
  (neutral/thinking/wave/shrug/excited -- `point` is captured but not yet
  used). Source art: static/img/frankie/ (`*-head.png` = what's wired in;
  `full/*.png` = original uncropped renders, kept for a possible larger
  placement later). Kj is producing animated (Runway, white background)
  versions of the same six moods in parallel -- not wired in yet, would be
  a round-two swap-in once ready. (2026-10-31, same day: Kj liked the small
  zoomed avatars in chat but wanted a bigger, more personalized Frankie on
  Discover, so added a second floating element -- `.ai-mascot-btn`, the
  full torso-up `wave` pose at ~104px with a gentle float animation --
  hovering just above the launcher pill button; clicking it opens the same
  panel as the button -- SUPERSEDED same day, see below.)
- **Frankie mascot v2** (2026-10-31, later same day): Kj didn't like the
  floating/animated version -- wanted her static, with zero gap, sitting
  directly on top of a Frankie button so she reads as sticking out of it,
  and wanted the identical treatment anywhere Frankie has a button to
  stand on (consistency across the app). Replaced the fixed-position
  floating mascot with a reusable pattern: `.frankie-mascot-wrap`
  (`position: relative`) wraps a button/link + `.frankie-mascot-btn`
  (`position: absolute; bottom: 100%; left: 50%; transform:
  translateX(-50%)`), so she's pinned to the top-center of whatever's in
  the wrapper with zero gap, at any button width, no JS and no animation.
  Used on Discover's floating launcher (`#aiLauncherWrap`) and the
  Evaluate page's "Build with Frankie" button. Source art:
  `static/img/frankie/mascot/*.png` -- cropped tight to content (no
  transparent margin below her feet) so the zero-gap stacking looks
  seamless; `full/*.png` stays as the untouched original renders.
  (2026-10-31, later still: Kj caught that on Evaluate her head was
  rendering under the sticky topbar -- `.frankie-mascot-wrap`'s own
  height in the page-header's flex row doesn't include the mascot,
  since she's `position: absolute`, so there wasn't actually enough
  clearance above the button for her to fit without reaching into the
  topbar. Added a `.page-header-frankie` modifier (48px margin-top),
  applied only to Evaluate's `<div class="page-header">` -- scoped so
  other pages' page-header spacing is untouched. Confirmed this time
  with a pixel-level zoom crop, not just a glance at the full screenshot
  -- that's how the first version's identical clipping bug got missed.)
- **Infra**: Claude pushes directly to `main` via the `claude-ssh` deploy-key
  remote (since 2026-10-15); every push auto-deploys on Railway. Database is
  Railway's managed Postgres -- never SQLite or Railway volumes (data-wiping
  bug, unresolved, don't revisit).

Known rough edges worth remembering, not yet fixed:
- The cross-page compare tray (above) is client-side/localStorage only --
  it doesn't sync across devices or browsers, and a cleared browser profile
  loses it. Fine for now; revisit only if Kj asks for it to be shared/
  synced.
