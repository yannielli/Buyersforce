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

- **Ticketing rewired off Messages; Open Tickets merged into All Tickets**
  (2026-11-07, Kj's follow-up): two fixes to Support Queue.
  1) Viewing or replying to a support ticket used to land on the shared
     `admin_thread` view/template, which is also Messages' own thread
     page -- nav highlighted "Messages", the back-link said "All
     messages", even though the ticket itself lives on Support Queue
     now. `admin_thread` is still the one shared route for every thread
     type (direct, vendor, teammate, support ticket) -- duplicating it
     risked drifting out of sync with buyer/seller's own thread views --
     so instead it now works out whether the thread it's showing is
     ticket-shaped (has a `support_requests` row, or is a vendor
     suggestion thread) and sets `g.admin_thread_is_ticket` + passes
     `is_ticket_thread` into the template. `base.html`'s nav and
     `admin/thread.html`'s back-link both branch on that flag: a ticket
     thread highlights "Support Queue" and says "← Back to Support
     Queue"; every other thread keeps "Messages" / "← All messages".
     Same route, same POST-to-reply handler -- just correctly branded
     either way, so Kj's "Messages has nothing to do with ticketing"
     holds for viewing AND replying.
  2) Support Queue's "Open tickets" (the always-visible decision list)
     and "All conversations" (the category-boxed inbox) were redundant
     -- merged into one "All tickets" section, keeping "All
     conversations"'s exact layout/organization. Each row is now a
     `<details>` accordion (`ticket_row()` in support_queue.html) --
     clicking it expands in place to show `ticket_panel()` for every
     ticket on that thread (the Build-this? Action/Defer/Reject form or
     resulting status, Frankie's suggested-resolution approve/modify/
     reject/defer form, Reply, Mark resolved) -- exactly what the old
     standalone Open Tickets list rendered, just one click down instead
     of always visible. Nothing from either section was dropped: the
     Resolved and Saved buckets got their own local accordion-aware
     versions (`ticket_resolved_subsection`/`ticket_saved_subsection`)
     instead of reusing `_thread_row.html`'s `thread_row`/
     `resolved_subsection`/`saved_subsection` macros, since those
     navigate away on click -- changing them would've affected Direct
     messages/Team threads and buyer/seller's own Messages pages too.
     `_admin_support_queue_context()`'s thread-scoped ticket query has
     no user join (unlike the old open-tickets query), so each ticket
     dict's requester_name/company/role now get backfilled from the
     thread's own `other_user` before the template sees it.
     Nav badges changed meaning along with this: `g.support_queue_count`
     used to be `support_requests.status='open'`, which never moved just
     from looking at a ticket -- now it's "ticket-shaped threads admin
     hasn't read yet" (the same unread-thread tracking `g.unread_count`
     uses), so it clears via the per-row mark-as-read toggle, replying,
     or any disposition action (admin_support_status/_decide/_engineering_
     decide all call `mark_thread_read` now too) -- matching Kj: "once I
     click it as read... or disposition the ticket... the new ticket
     counter... should change automatically." `g.engineering_queue_count`
     used to be `engineering_status='none'`, which only duplicated
     Support Queue's own "not yet decided" set -- now it's
     `engineering_status='action_requested'` ("Queued for Claude"), so
     clicking Action: Coding visibly moves a ticket off the Support
     Queue badge and onto the Engineering Queue badge, matching Kj:
     "if I move it over to Engineering Queue... it would show a new
     item in the counters." The Dashboard's own tiles (engineering_counts,
     keyed by exact pipeline stage) are unchanged by any of this -- only
     the two nav badges' definitions moved.

- **Support Queue category tabs; Engineering Queue ticket details inline**
  (2026-11-07, Kj's follow-up): two more changes to cut scrolling and
  reduce page-hopping.
  1) "All Tickets"'s stacked category boxes (Technical support, Report
     a bug or issue, Feature enhancement request, Something else, plus
     vendor suggestions) all used to render at once -- finding one
     category meant scrolling past every other one first. They're now
     a single-select tab row: All Tickets (every category) first, one
     tab per support category (each showing its open-ticket count) in
     `SUPPORT_CATEGORIES` order, then Archived last. Built as its own
     markup in support_queue.html rather than reusing the shared
     `_archive_toggle.html` partial (also used on Messages/buyer/seller
     pages), so the extra category tabs and "All Tickets" wording stay
     local to this page. Filtering happens client-template-side (a
     `category` query-string arg, Jinja `selectattr` over the already-
     built `support_boxes`) -- no new query, since every category's
     tickets were already being fetched and boxed, just all rendered
     at once. `_admin_support_queue_context()` now also returns
     `support_categories` (the ordered key/label list for the tab loop)
     and `category_counts` (per-category counts, including empty
     categories, for the "(0)" on an empty tab). Resolved/Saved stay
     unfiltered beneath whichever tab is open -- Kj didn't ask for
     those split by category too, and they're already collapsed
     accordions so they don't add much scroll either way. `ticket_panel()`
     now takes `next_url` (threaded through from `ticket_row()`) instead
     of hardcoding `#all-tickets` on its own 3 forms' `next` field, so
     taking a disposition action from inside a filtered tab redirects
     back to that same tab instead of resetting to "All Tickets".
  2) Engineering Queue's `ticket_card()` always had everything it
     needed already on the same `support_requests` row (the route's
     query already joins `users` for requester_name/company/role, and
     `SELECT sr.*` already carries notes/attachment/ai_suggested_
     resolution/decision) -- it just wasn't rendering most of it, so
     "View ticket" existed purely to see the rest. Nothing is actually
     copied or duplicated between the two queues; each ticket_card is
     now its own `<details>` accordion (same look/feel as Support
     Queue's `.thread-row-accordion`, new local classes `.eng-ticket*`
     since the layouts differ enough not to share one CSS block) that
     expands to show the full notes, the attachment (if any), and
     Frankie's suggested resolution (if any) -- i.e. everything "View
     ticket" used to require a trip to Support Queue for. The one thing
     that still needs a real navigation is replying to the requester
     (composing a message needs the thread view) -- that's now a
     "Reply to {name}" link inside the expanded panel instead of a
     "View ticket" link on the collapsed row. The existing per-status
     action buttons (Cancel request / Push to BF / Suggest another way
     / Move to Claude's queue / Mark handled by me / Reject / Reopen)
     are unchanged, just moved to sit beside `<summary>` as a sibling
     rather than inside it, since "Suggest another way" is itself a
     `<details>` and a `<details>` can't legally nest inside a
     `<summary>`.

- **Dashboard pending-ticket count + Support Queue status badges + Engineering
  Queue workflow buttons** (2026-11-07, same day, 3 small bug/quirk reports
  from Kj after using the day's earlier changes):
  1) Dashboard's "New tickets" tile (`engineering_counts.pending`) counted
     every `support_requests` row at `engineering_status='none'`, full stop
     -- but a ticket Kj had already closed via the ticket panel's "Mark
     resolved" button (`status='resolved'`) never gets an engineering
     disposition at all unless he separately Action/Defer/Rejects it, so it
     kept inflating this tile forever even though Support Queue's own "All
     tickets" view (which excludes `status='resolved'` via `split_resolved`)
     had already stopped showing it. Fix: added `AND status != 'resolved'`
     to that one query, so the tile matches what Support Queue itself
     considers still-open.
  2) Support Queue's ticket rows (`support_body()`) showed a generic
     "Open"/"In progress"/"Resolved" badge plus a redundant "N open
     ticket(s)" badge next to it, even once Kj had already dispositioned
     the ticket on the engineering side (Queued for Claude, Deferred, Build
     ready, etc.) -- that disposition was invisible without expanding the
     row. New `ENGINEERING_STATUS_META` dict (app.py, by `engineering_status`,
     shared global so any template can use it) gives each non-`'none'`
     status a label + the same color Engineering Queue's own section list
     uses for it; `support_body()` shows that colored badge instead of the
     generic one once a disposition exists, falling back to the old ticket-
     status badge for `'none'`. The "N open ticket(s)" badge is gone --
     Kj's call, since it was just adding noise next to the (now more
     informative) status badge.
  3) Engineering Queue workflow buttons Kj asked for, stage by stage:
     - **Queued for Claude**: Kj asked whether a button here can trigger an
       actual Claude coding session directly. No -- and this is deliberate,
       not a gap: see "How the loop actually closes" above (no DATABASE_URL
       or deploy credentials are ever wired into a chat session, and
       BuyersForce the web app has no way to summon Claude on its own). What
       changed instead: a new **Copy brief for Claude** button assembles the
       ticket's full context (category, requester, notes, Kj's note,
       attachment filename, a one-line instruction to mark it `build_ready`
       when done) into one clipboard copy (`copyEngBrief()`, plain
       `navigator.clipboard`), so pinging Claude in a chat is a paste
       instead of a re-type. Cancel request is unchanged.
     - **Build ready**: Push to BF and Suggest another way are unchanged;
       added **Cancel build**, a plain `action=reject` post to the existing
       `admin_support_engineering_decide` route (which already allows
       `reject` from any status -- only the separate "back to `none`"
       `_cancel` route was blocked here) with a confirm() since it archives
       the ticket.
     - **Approved to ship**: no button -- just a one-line status note
       ("Waiting on Claude to deploy -- moves to Shipped once it's
       pushed."), per Kj's "more of a status window" framing.
     - **Shipped**: new **Notify {name}** button / route
       (`admin_support_engineering_notify`) posts a canned "this is now
       live" message into the ticket's thread via the same INSERT INTO
       messages + `notify_new_message` pattern `admin_support_decide`'s
       approve/modify branch already uses, so the requester sees it exactly
       like any other admin reply and the feedback loop closes without Kj
       writing it by hand each time.

- **Admin Messages: compose is real now** (2026-11-07, Kj's report after
  the Engineering Queue work above: "lacks the ability to compose a
  message to anyone" + "missing the message action buttons"). Root
  cause of both: `admin_messages()`'s own docstring already said Direct
  messages was "a placeholder... nothing creates one of these today" --
  the shared `/app/messages/new` + `/app/messages/start` compose flow
  (`messages_new.html`, used by buyer/seller already) explicitly
  404'd for any role other than buyer/seller, so admin could never
  start a thread, which meant Direct messages stayed permanently empty
  -- and the per-row action icons (mark read/flag/save/archive) were
  never missing, there was just never a row to show them on. Fix, all
  in the existing shared machinery rather than anything admin-only:
  - `_can_message`: added `if user["role"] == "admin": return True`
    (except self) -- admin's Messages is a full inbox, not bound by the
    marketplace's buyer/seller matching rules.
  - `search_recipients`: new admin branch searches every user by
    name/company/email (no role/company restriction), instead of
    falling into the seller branch by accident (which would have
    limited admin to "buyers, or sellers at admin's own company" --
    i.e. no sellers at all, since admin's company isn't a real seller
    company).
  - `messages_new` / `messages_start`: role gate now allows
    `"admin"` too.
  - `messages_start`: admin always gets a plain
    `get_or_create_direct_thread`, never `thread_with_user`'s
    buyer<->vendor routing -- that path assumes whichever side isn't
    the buyer has a seller's vendor listing, which admin doesn't, and
    would `abort(400)` if admin messaged a buyer.
  - `messages_new.html`'s back-link and search label now branch on
    admin too (previously hardcoded buyer-or-seller).
  - New "+ New message" button on `admin/messages.html`'s page header,
    linking to the now-admin-capable `messages_new`.
  Net effect: admin can message any buyer or seller (or, once a second
  BuyersForce teammate account exists, another admin) straight from
  Messages, and every thread that creates shows up in Direct messages
  with the same 4 action icons every other thread row already has --
  nothing new needed there, since `_thread_row.html`'s `thread_row()`
  macro already renders them for any row, admin's included.

- **Admin reachable from any account, bulk-select on every Messages
  section** (2026-11-08, Kj's follow-up): two changes to Messages,
  requested together.
  - **Admin searchable/reachable both ways.** Kj: "anyone that has a
    Buyersforce account (buyer or seller) can message anyone from
    Buyersforce including me... my name and email should be
    searchable from my test accounts as buyers and sellers." The
    2026-11-07 admin-compose fix above only opened the door from
    admin's side; buyer/seller search still excluded admin entirely
    (`is_admin = 0` on both directory branches). Fix: `_can_message`
    now returns `True` whenever EITHER side is admin (not just when
    the viewer is admin), and `search_recipients`'s buyer branch drops
    `is_admin = 0` (now searches `role IN ('buyer','seller','admin')`)
    while the seller branch adds `OR role = 'admin'` alongside its
    existing buyer/same-company-seller match. Any buyer or seller
    typing Kj's name or email into message search now finds him, same
    as any other contact.
  - **Bulk-select checkboxes + toolbar, every section, all three
    Messages pages.** Kj: "for all messaging areas (admin, buyers,
    sellers) I need to have the ability to select multiple messages
    with check boxes so save, delete, archive, etc. So the buttons...
    should also be at the top of each messaging section." New
    `/app/messages/bulk` route (`messages_bulk_action`) takes an
    `action` (mark_read/mark_unread/flag/save/archive/restore) and a
    list of `thread_ids`, and loops the exact same per-thread
    mutations (`mark_thread_read`, `set_thread_flag`, etc.) the
    existing single-row icons already call -- so a bulk action behaves
    identically to clicking that icon on each row by hand, including
    the same `_load_thread_for_user` ownership check per id (skips any
    id that isn't actually this viewer's thread instead of failing the
    whole request; the checkboxes only ever list ids from that
    viewer's own already-scoped query results, so this is a defensive
    backstop, not the normal path).
    Structural challenge: a thread-list section can't be wrapped in
    one bulk-action `<form>`, because every row already has its own
    small per-row `<form>` (the 4 toggle icons) and HTML doesn't allow
    nested forms. Solved with the `form="<id>"` attribute instead --
    `_thread_row.html`'s `thread_row()` macro grew a `form_id` param
    that, when set, renders a plain (non-nested) checkbox pointing at
    `"<form_id>-bulk-form"`, a separate sibling `<form>` rendered by a
    new `bulk_bar(form_id, next_url, show_restore)` macro placed above
    the section's row list. `saved_subsection()`/`resolved_subsection()`
    thread `form_id` through the same way. Each section on a page
    needs its own unique `form_id` (direct/team/vendor/buyer/support)
    to keep the checkbox-to-toolbar wiring unambiguous when a page has
    more than one section. `app.js` wires "Select all" and a submit
    guard (empty-selection alert; `confirm()` on Archive via
    `data-bulk-confirm`) by querying `input[form="<id>"]` across the
    whole document, same reason -- the checkboxes aren't DOM
    descendants of the toolbar form they submit with.
    Rolled out to every section on all three Messages pages: admin
    (Direct, Team), buyer (Direct, Vendor, Team, Support &
    BuyersForce), seller (Direct, Buyer, Team, Support & BuyersForce).
    Scoped to Messages only, per Kj's wording ("admin, buyers,
    sellers") -- Support Queue's ticket rows use their own separate,
    `<details>`-based local macros (not `_thread_row.html`), so they're
    left out of this round; say if that should get the same treatment.

- **File attachments, everywhere a message can be composed** (2026-11-08,
  Kj's follow-up: "add in the capability in Messaging for admins, buyers
  and sellers in Messages to be able to attach files to any/all
  messages... I see it exists already in my admin view, but need in the
  buyer/seller messages too"). Replying inside an already-open thread
  (`admin/seller/buyer/thread.html`) already had a file input on all
  three roles -- that part was never actually broken. The real gap was
  every message-COMPOSE entry point, which is shared code across all
  three roles (so admin had the identical gap Kj just hadn't hit yet):
  - `/app/messages/start` (the "New message" search-and-compose flow
    behind `messages_new.html`, used by admin/buyer/seller alike) now
    reads `request.files.get("attachment")` and reuses
    `_insert_thread_message` for the normal (existing-BuyersForce-user)
    case; the "email someone not on BuyersForce yet" branch gets the
    same `_read_uploaded_support_attachment` encode/validate the support-
    ticket flow already uses, stored on the message row the same way (the
    attachment itself isn't emailed -- consistent with every other
    message notification, which only ever quotes the text body).
  - `buyer_new_team_thread` / `seller_new_team_thread` (the "+ New team
    thread" compose box on buyer/seller Messages) get the same
    `_insert_thread_message` treatment.
  - A message can now be sent with an attachment and no body text at
    all (previously a literal body was required even when a file said
    everything), matching how the existing thread-reply form already
    behaved.
  - Template side: `messages_new.html`'s compose form and both team-
    thread compose boxes gained `enctype="multipart/form-data"` plus the
    same "Attach a file (optional, up to 10MB)" field the thread-reply
    form already uses, so every compose surface now looks and behaves
    identically.
  Left out of this round, matching the Support Queue boundary Kj already
  drew for bulk-select: the AI-ticket-decision reply box
  (`admin_support_decide`) and the vendor-suggestion decision box
  (`admin_vendor_request_decide`), plus the buyer's quick "message this
  vendor" box on a vendor's profile page -- none of those are the
  Messages page Kj was pointing at. Say if any of those should get the
  same treatment.

- **File attachments, the last three spots** (2026-11-08, same day,
  Kj's follow-up: "attaching files is a pretty basic thing and should
  be consistent" -- extending the attachment work above to the three
  places explicitly left out of it):
  - `admin_support_decide`'s approve/modify reply (the AI-drafted
    resolution box on Support Queue) now takes an optional attachment,
    reusing `_insert_thread_message` the same way every other compose
    point does. Only wired for approve/modify, since reject/defer never
    post anything to the thread.
  - `admin_vendor_request_decide`'s deny and approve branches (the
    vendor-suggestion review form on the Dashboard) now take an
    optional attachment on the message posted back to a buyer/seller's
    referral thread. Doesn't apply to the `seller_signup` kind's email
    path (a prospective seller who filed their own listing, not a
    referral) -- there's no thread to store the file in, and emailer.py
    only sends plain text, no MIME attachments; extending that would
    mean building real email-attachment support, a bigger separate
    piece of work if ever wanted.
  - `buyer_message_vendor` (the "✉️ Message vendor" quick box on a
    vendor's profile page) now takes an optional attachment too, and
    (matching every other compose point) can be sent as a file alone
    with no text.
  Net effect: every place on BuyersForce where a human composes a
  message to another human now has the same "Attach a file (optional,
  up to 10MB)" control and the same backend path (`_insert_thread_message`
  for a thread message, or the support-attachment encode/validate for the
  one case that sends by email instead).

- **Quiet background refresh for nav badges and open threads**
  (2026-11-08, same day, Kj's question: "is there a periodic refresh...
  does it update right away for the sender and recipient or do they
  need to hit refresh" -- answer was no, BuyersForce had no live-push
  mechanism at all; this adds one, deliberately NOT as a full-page
  auto-refresh once Kj raised the obvious risk: a full reload would
  wipe an in-progress reply draft, a chosen file attachment (browsers
  can never restore a file input across a reload), an open "+ New team
  thread" box, or scroll position, anywhere in the app, not just
  Messages).
  - New `GET /app/poll/badges` -- just hands back the same
    `g.unread_count` / `g.support_queue_count` / `g.engineering_queue_count`
    `load_logged_in_user`'s `before_request` hook already recomputes on
    every request, as JSON. `static/js/app.js` polls it every 40s and
    swaps the nav badge's text in place (`setNavBadge`, creates the
    `<span class="nav-badge">` if one doesn't already exist, removes it
    if the count drops to 0) -- never a page reload, so nothing else on
    the page is touched.
  - New `GET /app/messages/<thread_id>/poll?after=<message id>` --
    returns any messages newer than `after` as JSON (via the same
    `_load_thread_for_user` access check every thread page already
    uses, so it's role-agnostic -- works the same for admin/buyer/
    seller). Marks the thread read as it goes, same as a normal page
    load would. `app.js` polls this every 30s on an open thread page
    and prepends new bubbles to the TOP of `.msg-list` (matching this
    app's newest-first convention everywhere -- unlike a typical chat
    app, this one is NOT scrolled/ordered oldest-at-bottom), built with
    `textContent` throughout (never `innerHTML`) so a message body can
    never be interpreted as markup. If the viewer was already scrolled
    to the top (reading the newest message), the view snaps back to
    the top automatically; if they'd scrolled down into older history,
    `scrollTop` is adjusted by exactly the new content's height so
    their view doesn't silently jump out from under them. The reply
    form itself is never touched by any of this.
  - `templates/base.html`: the one Messages nav link, and admin's
    Support Queue / Engineering Queue links, each got a stable `id`
    (`nav-messages-link` / `nav-support-queue-link` /
    `nav-engineering-queue-link`) for the JS to find (only one of the
    three Messages variants ever renders per page, so the shared id
    never collides); `<body>` grew a `data-logged-in` attribute so the
    polling only runs for a signed-in viewer, never on the public
    landing/login/signup pages.
  - `templates/admin|buyer|seller/thread.html`: `.msg-list` grew
    `data-thread-id` and `data-latest-id` (the highest message id
    already rendered, computed via `messages|max(attribute='id')`
    rather than trusting row order, since timestamps only have
    one-second resolution and a same-second tie could otherwise put a
    lower-id message first) so `app.js` knows which thread to poll and
    where to pick up from.
  - Both polls skip firing while the tab isn't visible
    (`document.visibilityState`), so a backgrounded tab doesn't keep
    hitting the server for no reason.
  - Deliberately out of scope for now: making the Support Queue ticket
    list itself (or any other list page) live-append new rows the same
    way -- this round only covers the nav badges (which already cover
    Support Queue/Engineering Queue's own "new since you last looked"
    counts) and an open thread's own messages.


- **EULA + Privacy Policy, required at new-account creation** (2026-11-08,
  same day, Kj's follow-up: "the new user needs to click a box to agree
  to our End User License Agreement and Privacy Policy" -- Kj supplied a
  sample Terms-of-Use document, written for an unrelated product
  ("Ergentor.ai"), to adapt rather than drafting from nothing). Two new
  public, no-login pages:
  - `GET /legal/eula` -> `templates/legal_eula.html` and
    `GET /legal/privacy` -> `templates/legal_privacy.html` -- deliberately
    two separate pages/URLs rather than one combined page with anchors
    (Kj: "make sure they are separate links... so the docs are
    separated"), each linking to the other at the top. Both are plain
    HTML, no login required, and are linked (opened in a new tab) from
    the new consent checkbox below, plus the site footer
    (`templates/base.html`).
  - Both documents are adapted from Kj's sample, NOT copied as-is --
    every Ergentor-specific fact was swapped for BuyersForce's real
    ones (confirmed by reading app.py/emailer.py/migrate.py rather than
    guessing): hosting is Railway (not Supabase), email is Resend, AI
    features (Frankie, AI-assisted support-ticket drafting) run on
    Anthropic -- and that's the *entire* sub-processor list; there's no
    Stripe/billing (BuyersForce has none), no Google/Slack/Twilio
    integration, no analytics or tracking cookies (just one functional
    session cookie), and no Cloudflare dependency of BuyersForce's own
    (the one "Cloudflare" hit in the codebase is a vendor company
    *listed in* the marketplace directory, unrelated to BuyersForce's
    own infrastructure). The sample's retroactive eligibility
    restriction (its users had to be US-based) was removed per Kj's
    explicit note: "A buyer or seller... can be located anywhere in the
    US or the world." The sample's "data deleted within 30 days of
    termination" promise was also deliberately NOT copied, since
    BuyersForce has no such automated job -- the retention language here
    is honest about what's actually implemented (delete/de-identify
    "within a reasonable time") rather than promising a feature that
    doesn't exist. Added a dedicated California Privacy Rights
    (CCPA/CPRA) section per Kj's "capture any california items" ask, plus
    California governing law (both already matched the sample). The
    company is referred to throughout as plain "BuyersForce" with no
    corporate suffix, per Kj: "BuyersForce is... not yet formalized into
    a C or S Corp or LLC... for now we can just call it 'BuyersForce'"
    -- which also meant fixing the site footer, which had been saying
    "BuyersForce, Inc." everywhere since the original landing-page build.
    Placeholder contact addresses (`legal@buyersforce.io`,
    `privacy@buyersforce.io`) are used throughout; these need to actually
    exist (or forward somewhere Kj checks) before go-live. **Not legal
    advice** -- both documents carry an HTML comment at the top saying so;
    Kj should have a California-licensed attorney review them (especially
    the arbitration clause and liability cap) before they govern real
    users.
  - `users` gained two nullable columns, `legal_accepted_at` and
    `legal_version` (migrate.py's `_add_users_legal_acceptance_columns
    _2026_11_08`; schema.sql updated to match). `legal_version` is
    `app.py`'s `LEGAL_DOC_VERSION` constant (bump it, and the "Effective
    Date" text in both templates, whenever the documents materially
    change) -- so it's always clear exactly which text version a given
    person agreed to.
  - New-signup consent checkbox added at the two, and only the two,
    places a brand-new BuyersForce account is ever actually created
    (traced through the real code rather than Kj's own guess of "after
    approval, reset password" -- there's no such step; approving a
    signup just flips `account_status` and emails a plain login link):
    `signup.html` (self-serve request) and `accept_invite.html`, but on
    accept-invite ONLY on the new-account branch, never the
    existing-user password-reset branch (`is_reset`) -- resetting a
    password isn't a new signup. Required server-side in both
    `signup()` and `accept_invite()`; unchecked shows the same flash-
    error pattern as every other validation on those forms.
  - Deliberately out of scope, per Kj's explicit decision ("New signups
    only (Recommended for now)"): no retroactive consent gate for
    already-active users. `legal_accepted_at`/`legal_version` stay NULL
    on every pre-existing account, on purpose.


- **Correction: "BF Pre-Launch Checklist" is NOT this app's
  `prelaunch_checklist_items` table** (2026-11-08, same day). Claude
  misread Kj's "Please add a couple of things to the BF Pre-Launch
  Checklist for me" as a request to insert rows into that table (it
  even added five rows across two migrations before catching the
  mistake). Kj's actual correction: "I didn't want you to do anything
  in the BF platform after creating the links to @privacy and @legal
  in the new account sign up process... The items I requested to be
  added to the 'BF Pre-Launch Checklist' is a running checklist
  document pinned in Claude to the left of the app." That document is
  the pinned "BuyersForce Pre-Launch Checklist" Claude Docs artifact
  (https://claude.ai/artifact/V7FqRdnoNvSEWxBunBs8BF) -- the five
  items went there instead (three under its "Needs coding (Claude's
  work)" section, two under "Kevin's own tasks (outside Claude
  coding)"), and the mistaken rows were reverted
  (`_revert_mistaken_prelaunch_items_2026_11_08`, replacing the two
  migrations that inserted them). **For any future session: a request
  to add to "the Pre-Launch Checklist" means that pinned Claude Docs
  artifact, never this table.** Kj's immediate follow-up: the original three
  rows (seeded 2026-11-07: SMS/Twilio, iOS app, Android app) were ALSO
  a mistake, not just the five this session added -- "Those items are
  NOT something we need in the BF platform at this time!... only exist
  as bullets in the BF Pre-Launch Checklist running doc in the pinned
  docs." `_empty_prelaunch_checklist_items_2026_11_08` clears the table
  to empty (not a DROP TABLE -- that's a bigger move than he asked for;
  ask him before taking it). **`prelaunch_checklist_items` has no
  legitimate use in this app at all -- don't insert into it for any
  reason, including a future "add to the checklist" ask. Everything
  checklist-related belongs ONLY in the pinned Claude Docs artifact
  above, never in this codebase or database.**
