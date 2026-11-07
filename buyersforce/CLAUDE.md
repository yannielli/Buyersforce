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
- **Infra**: Claude pushes directly to `main` via the `claude-ssh` deploy-key
  remote (since 2026-10-15); every push auto-deploys on Railway. Database is
  Railway's managed Postgres -- never SQLite or Railway volumes (data-wiping
  bug, unresolved, don't revisit).

Known rough edges worth remembering, not yet fixed:
- The cross-page compare tray (above) is client-side/localStorage only --
  it doesn't sync across devices or browsers, and a cleared browser profile
  loses it. Fine for now; revisit only if Kj asks for it to be shared/
  synced.
