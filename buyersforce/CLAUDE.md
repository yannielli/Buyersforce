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
- **Frankie on the Build-with-Frankie wizard** (2026-10-31, later still):
  Kj wanted her kept visible across the wizard's steps too, not just the
  two small chat-panel avatars inside it. Gave the wizard page-header a
  `.frankie-mascot-wrap` the same way (standing on the "<- Back to
  Evaluate" button, `page-header-frankie` for topbar clearance), and
  wired its mood to track whatever the two embedded chat panels'
  `addAssistantBubble`/`addTypingBubble` helpers already resolve (now
  also writing to a `FRANKIE_MASCOTS`-sourced `#frankieWizardMascot`
  image, not just the small per-row avatar) -- plus `excited` on
  reaching the final (review/submit) step. Also found and fixed a
  layout bug this surfaced: `.page-header`'s title block has no width
  constraint, so a long lede (this page's is) sized the flex item to
  its full unwrapped text width, forcing the button block onto its own
  line below -- `.page-header-frankie > div:first-child { flex: 1 1 0%;
  min-width: 0 }` makes the title shrink/wrap in place instead. This
  fix is shared by both page-header-frankie pages.
- **Fixed: Discover's floating "Ask Frankie" launcher had silently
  disappeared** (2026-10-31, later still). Root cause: the mascot-wizard
  commit above gave `#aiLauncherWrap` both `.ai-launcher-wrap` (which sets
  `position: fixed; right/bottom` to float it) and `.frankie-mascot-wrap`
  (which sets `position: relative`, defined later in style.css). Same
  specificity, so source order wins -- `.frankie-mascot-wrap` clobbered the
  fixed positioning and the whole launcher dropped into normal document
  flow, invisible unless scrolled to its exact flow position. Fixed by
  raising the launcher rule to the compound selector
  `.ai-launcher-wrap.frankie-mascot-wrap { position: fixed; ... }` so it
  wins regardless of source order, rather than depending on rule order
  (fragile -- the next unrelated CSS edit could flip it back). Also a
  verification-process note: the screenshot used to "confirm" that same
  earlier commit was staged with an inline `style="position:absolute;..."`
  on the test harness's wrapper div, which (being higher-specificity than
  any class rule) masked this exact bug and produced a false-positive
  pass. Re-verified this fix with a clean harness carrying no inline
  overrides, on a tall simulated page, confirming computed `position` and
  bounding box both before (buried in flow) and after (pinned
  bottom-right) the fix.
- **Shimmering star sparkle on both Frankie teal CTA buttons** (2026-11-07):
  Kj's ask -- Discover's "Ask Frankie" launcher and Evaluate's "Build with
  Frankie" should both show the same little animated star sparkle,
  continuously shimmering, not just on hover. Evaluate's button previously
  had a static "<sparkle emoji>" text character; Discover's had none (just
  the small circular Frankie head icon, which is a separate element and
  stays). Rather than invent a new icon, reused the app's existing
  "Googie" decorative sparkle motif -- the `#m-sparkle` SVG path + the
  `.shimmer` keyframe (scale/opacity pulse) already used on base.html's
  animated logo and landing.html's hero/CTA sections -- so the sparkle on
  these two buttons matches BuyersForce's established visual language
  instead of introducing a one-off. Each template defines its own tiny
  zero-size `<svg><defs>` sprite locally (same pattern landing.html
  already uses, since the defs live page-local, not in base.html), then
  `<use href="#m-sparkle" class="shimmer" fill="#fff">` inline right
  before the button label (after the avatar icon on Discover). New
  `.frankie-btn-sparkle` class in style.css just handles sizing/flex
  behavior; `.shimmer` does the animation. Added a
  `prefers-reduced-motion` override (same precedent as `.thinking-
  shimmer`) so the sparkle holds still instead of pulsing for users who
  asked for less motion. Verified light + dark mode zoomed screenshots,
  and sampled computed opacity/transform across several points in time to
  confirm the animation is actually running (not just class-named).
  (Same day, follow-up) Kj liked the single white sparkle but wanted more:
  2-3 differently-sized stars per button, in BF's own color scheme rather
  than plain white, plus the small circular Frankie head icon removed
  from Discover's button entirely (redundant now that the full mascot
  already stands on top of the same button). Changes: (1) each button now
  has three `#m-sparkle` `<use>`s at three sizes (13/10/7px) and three
  colors -- white, `var(--brand-mcm-coral)`, `var(--brand-mcm-mustard)` --
  the same three-color trio used on base.html's animated logo mark, so
  this reads as BF's actual brand palette rather than an arbitrary pick.
  Coral/mustard specifically because the palette's own comment
  (`--brand-mcm-coral` definition) already calls those two out as
  decoration-only accents, never button/badge fills on their own --
  exactly the role they play here, layered on top of the real teal button
  background rather than replacing it. Each gets a different
  `animation-delay` (0s/0.5s/1s) so the three twinkle out of phase rather
  than blinking in unison -- verified by sampling computed opacity on all
  three at several points in time and confirming they're never equal.
  (2) Removed discover.html's `<img class="ai-launcher-icon ...">` (the
  small round Frankie head) from the `#aiAssistantToggle` button, and the
  now-dead `.ai-launcher-icon` CSS rule along with it -- confirmed no
  other template referenced that class before deleting the rule.
  (Same day, second follow-up) The three sparkles were spread across the
  button -- one before the label, two after -- which wasn't what Kj had
  in mind. He wanted all three clustered together as one mark, to the
  left of the label, like a classic multi-star "sparkle" icon. Changed
  `.frankie-btn-sparkle` from a plain flex child to three children of a
  new `.frankie-btn-sparkles` wrapper span: the wrapper is a small fixed-
  size (20x18px) `position: relative` box, and the three stars inside it
  are `position: absolute` at hand-picked, overlapping offsets (big star
  lower-left, medium upper-right, small lower-right) so they read as one
  tight triangular cluster rather than a row. The wrapper itself is the
  single flex child that sits before the label text, so button spacing
  to the label is unaffected. Verified with zoomed light/dark
  screenshots on both buttons.
- **Infra**: Claude pushes directly to `main` via the `claude-ssh` deploy-key
  remote (since 2026-10-15); every push auto-deploys on Railway. Database is
  Railway's managed Postgres -- never SQLite or Railway volumes (data-wiping
  bug, unresolved, don't revisit).
- **AI support ticket agent + external message alerts** (2026-11-07): Kj's
  two-part ask -- (1) have Frankie triage every support ticket and draft a
  resolution for Kj to decide on, with an external alert directing him
  back; (2) alert anyone (admin or member) by email when they get a new
  BuyersForce message, not just support tickets.
  - **Ticket triage**: the moment a buyer/seller submits a ticket
    (`support_new`), `ai_assistant.run_support_triage()` drafts a
    verbatim-postable reply plus a recommended ticket status
    (open/in_progress/resolved), stored on the new
    `support_requests.ai_suggested_resolution` /
    `ai_suggested_status` / `ai_suggested_at` columns. Kj gets a
    Frankie-branded email (`emailer.send_support_ticket_alert`, from
    "Frankie (BuyersForce AI Assistant)", not a generic system notice)
    linking straight to the admin dashboard's Support requests section.
    A triage/email failure is caught and logged -- it never blocks the
    requester's own ticket submission.
  - **Kj's decision**: new `admin_support_decide` route and dashboard UI
    (an editable textarea pre-filled with Frankie's draft, right under
    each ticket) implement the four outcomes Kj asked for -- **Approve
    as drafted** and **Save edits & approve** both auto-post the
    resolution into the ticket's thread as the actual reply and move
    the ticket to the recommended (or admin-picked) status;
    **Reject** and **Defer** post nothing and leave status untouched.
    Recorded on `support_requests.decision` (`pending_review` /
    `approved` / `modified_approved` / `rejected` / `deferred`) +
    `decision_note` / `decided_at` / `decided_by`, mirroring the
    existing `vendor_requests` admin-decision pattern.
  - **Message alerts**: new `notify_new_message(thread_id,
    sender_user_id, body)` in app.py, called after every message
    insert in the file (the shared `_insert_thread_message` helper plus
    every other raw INSERT site). Throttled per (recipient, thread) via
    a new `thread_reads.last_alert_sent_at` column (members) /
    the existing `threads.pending_email_sent_at` (non-members) so an
    active back-and-forth doesn't flood an inbox -- first message of a
    thread, or the first one after a 20-minute quiet gap, always
    alerts. **Deliberately scoped to `direct` threads only**
    (`_resolve_message_recipient` returns `None` for `vendor`/
    `teammate`/`partner` threads, which can have more than one
    legitimate recipient -- left for a future pass if Kj wants it).
    Support ticket threads are excluded on purpose (the Frankie-branded
    ticket alert above supersedes it); `eval_project_share`'s
    external-recipient branch is excluded too (it already gets a
    richer `send_evaluation_share` email with the attachment).
  - **Pre-Launch Checklist, corrected** (2026-11-07, same day): Kj
    actually meant Claude's OWN pinned-items sidebar (claude.ai's left
    pane), not anything inside the BuyersForce app -- the first pass
    built a BF admin page for this by mistake (misread "pinned in the
    left pane" as a BF UI element, since BF has no left sidebar). That
    admin page (route, nav link, template) was removed the same day;
    the three TBD items (SMS/Twilio text alerts, iOS app, Android app)
    now live in a pinned Claude artifact/doc instead, outside this
    codebase -- see Claude's own pinned items, not BF, for the current
    checklist. `prelaunch_checklist_items` is an orphaned table left in
    the schema (harmless, unused) from the removed first pass -- fine
    to drop in a future cleanup, not worth a risky migration just for
    that.
  - Schema: `support_requests` gained the 7 columns above;
    `thread_reads` gained `last_alert_sent_at`.
- **Engineering decision queue, v2** (2026-11-07, same day as the above):
  Kj liked the AI-reply approve/modify/reject/defer flow as-is, but
  wanted a SEPARATE decision about whether the underlying feature/bug a
  ticket describes is worth actually building -- that's a different
  question from "should Frankie's drafted reply go out", and the two
  were tangled together in the first pass.
  - New **Reject / Defer / Action** buttons on the LEFT side of each
    ticket's pane on the Dashboard (`admin_support_engineering_decide`),
    visually separate from the existing Frankie reply box (unchanged).
    Reject archives it (out of the active queue, kept for reference);
    Defer tables it into a future queue; Action queues it for Claude to
    actually build, with Kj's note on what he wants.
  - New **Engineering Queue** admin page (top nav), `support_requests
    .engineering_status` state machine: `none` -> `rejected` |
    `deferred` | `action_requested` -> `build_ready` -> (`approved_to_
    ship` -> `shipped`) or back to `action_requested` via "Suggest
    another way". Kj's two buttons on a `build_ready` item -- **Push to
    BF** and **Suggest another way** -- live here
    (`admin_support_engineering_push` / `_suggest`).
  - **How the loop actually closes (important -- read before assuming
    this is automatic):** BuyersForce the web app has no way to
    autonomously summon Claude, and the live production database is
    deliberately never queried directly from a chat session (no
    DATABASE_URL is ever read into a conversation -- see the Credential
    Materialization guard that blocks even *listing* Railway variables).
    So: clicking **Action** just flags the ticket in the DB; Kj still
    has to tell Claude in a chat ("build ticket #BF-123") to actually
    start, same as every other change in this file. Once Claude's built
    it on a feature branch, Claude marks it `build_ready` (with a
    summary + branch name) the SAME way every other one-time data
    change in this app ever happens -- a one-shot `_data_patches`-
    guarded UPDATE added to `migrate.py` alongside the actual code
    fix, which applies itself on the next deploy. When Kj clicks **Push
    to BF**, that's `approved_to_ship` in the DB (an ordinary admin
    action, no credentials involved); Claude still has to actually do
    the `git push` to merge it to `main` (which it already can, via
    `claude-ssh` -- no new access needed), and marks it `shipped` the
    same one-shot-patch way. Net: no new infrastructure, no credentials
    ever touched, but also not push-button-automatic -- Kj pinging
    Claude is still the trigger at both the "go build it" and "I've
    pushed/shipped it" ends.
  - **Dashboard tiles** (2026-11-07, same day): a row of 6 small count
    tiles on the Dashboard ("Queued for Claude", "Build ready", "Approved
    to ship", "Shipped", "Deferred", "Rejected"), each linking straight to
    its section on the Engineering Queue page -- so Kj sees at a glance
    whether anything needs him without opening that page. Counts come from
    `_admin_dashboard_context()`'s new `engineering_counts` (one `GROUP BY
    engineering_status` query); colored semantically (warning tint for
    "needs your review", brand tint for "in progress", good tint for
    "shipped", plain/neutral for deferred/rejected) -- using the existing
    `--good-tint`/`--warning-tint`/`--brand-tint` tokens the badge classes
    already use, not `--brand-mcm-coral`/`--brand-mcm-mustard` (style.css's
    own comment on that variable already calls those two out as
    decoration-only accents, never button/badge/tile fills).
  - **"Action" split into Coding vs Admin** (2026-11-07, Kj's correction
    once he saw the three buttons in practice): not every ticket needs
    code -- a password reset or a user-account tweak, Kj just does it
    himself. The single "Action" button became two: **Action: Coding**
    (unchanged -- `engineering_status='action_requested'`, queued for
    Claude) and **Action: Admin** (new terminal `engineering_status=
    'admin_completed'`, set directly, never touches Claude's build queue
    at all). Both live side by side next to Defer/Reject on the
    Dashboard's per-ticket panel and get their own section + Dashboard
    tile on the Engineering Queue.
  - **Dashboard tiles v2 + button styling fixes** (2026-11-07, same day,
    Kj's follow-up after seeing v1 in practice): grew from 6 tiles to 8,
    laid out in 4 explicit rows exactly as Kj specified, and switched
    from tint/outline styling to solid fills with white text (matching
    the existing top-of-dashboard stat tiles' look) so the Engineering
    Queue reads as a bold color-coded strip instead of a muted one:
    - Row 1: **Pending** (brand-new tickets still at the `'none'`
      default -- not yet dispositioned at all) in bright blue
      (`--progress`). New `engineering_counts.pending` query in
      `_admin_dashboard_context()` (`COUNT(*) WHERE engineering_status =
      'none'`) -- kept separate from the existing `GROUP BY
      engineering_status` query since `'none'` rows are deliberately
      excluded there. Links to the Dashboard's own Support Requests
      section (`#support-requests`), not the Engineering Queue page,
      since undispositioned tickets never appear on that page.
    - Row 2: **Completed by admin** in green (`--good`).
    - Row 3: **Queued for Claude** in red (`--critical`), **Build ready
      -- your review** in orange (`--brand-mcm-coral`), **Approved to
      ship** in yellow (`--brand-mcm-mustard`), **Shipped** in green
      (`--good`).
    - Row 4: **Deferred** in teal (`--brand`), **Rejected (archive)** in
      flat gray (`--ink-muted`).
    Also fixed two bugs Kj reported in the per-ticket "Build this?"
    panel on the Support Requests list: the column was overlapping
    ticket info/images because `.btn`'s `white-space: nowrap` plus the
    column's `flex-shrink:0` forced it wider than its intended
    ~150-160px -- narrowed the column to a fixed 128px and added
    `white-space:normal; width:100%` to every button and the note input
    so text wraps instead of pushing the layout wider. And Defer/Reject
    had no visible "button box" because they used `.btn-ghost` (no
    fill/border) -- replaced with the same solid-fill inline-style
    pattern as the other two buttons. Reordered and recolored all four
    buttons to match their Dashboard tile counterparts: Note (optional,
    unstyled) -> **Action: Admin** (green) -> **Action: Coding** (red)
    -> **Defer** (teal) -> **Reject** (gray) -- so the color used for a
    disposition is consistent everywhere it shows up.

Known rough edges worth remembering, not yet fixed:
- The cross-page compare tray (above) is client-side/localStorage only --
  it doesn't sync across devices or browsers, and a cleared browser profile
  loses it. Fine for now; revisit only if Kj asks for it to be shared/
  synced.
- Message alerts (above) only cover `direct` threads (plus support
  tickets and eval shares via their own dedicated alerts) -- a `vendor`/
  `teammate`/`partner` thread never alerts anyone externally, since more
  than one person could reasonably be "the" recipient there and guessing
  wrong isn't safe. Revisit if Kj asks for those covered too.

- **Support Queue, split out of Dashboard/Messages** (2026-11-07, Kj's
  request): support tickets and vendor suggestions used to be spread
  across two places -- the "Build this?" decision list on the Dashboard
  and the "Support tickets" boxed-by-category section on Messages. Both
  moved intact onto one new page, `admin_support_queue` (nav item
  "Support Queue", positioned left of Engineering Queue): the actionable
  list (Frankie's suggested-reply approval + the engineering Action/
  Defer/Reject call) first, then the full ticket inbox (category boxes,
  Resolved/Saved buckets, Active/Archived toggle) below it, unchanged in
  shape from how Messages always rendered it. Direct messages and Team
  threads stay on Messages; the Engineering Queue tiles stay on the
  Dashboard -- only the ticket list itself moved. Judgment call worth
  flagging: vendor suggestions moved along with support tickets rather
  than staying on Messages, since the two have always shared one UI
  section ("Support tickets" boxed by category, with a dedicated
  "Vendor suggestions" box) -- splitting them apart would've left a
  "Support tickets" heading on Messages containing nothing but vendor
  suggestions. Revisit if Kj wants that split differently.
  Both Support Queue and Engineering Queue also picked up a nav badge,
  same spirit as Messages' unread-count badge: `g.support_queue_count`
  (tickets still at status='open', i.e. not yet replied/resolved) and
  `g.engineering_queue_count` (tickets still at engineering_status=
  'none', i.e. no Action/Defer/Reject call made yet -- same definition
  as the Dashboard's "Pending" tile), both computed in
  `load_logged_in_user()` alongside `g.unread_count`, admin-only.
  Follow-up (same day): the Dashboard's 8 count tiles got split into
  two section headers -- "Support Queue" (New tickets + Completed by
  admin, 2 tiles) above "Engineering Queue" (Queued for Claude/Build
  ready/Approved to ship/Shipped/Deferred/Rejected, 6 tiles) -- so the
  Engineering Queue tiles are exclusively about the code-build
  pipeline (Kj: "the Engineering Queue counters only reflect and link
  over to the Engineering Queue page as it should"), while New
  tickets (renamed from "Pending") and Completed by admin, neither of
  which involves Claude writing code, sit under their own Support
  Queue header instead. New tickets links to the Support Queue page
  (where undispositioned tickets actually live now); Completed by
  admin still links to its existing anchor on the Engineering Queue
  page, since that's still where the per-ticket Reopen control lives
  -- only its Dashboard grouping changed, not where it's managed.
