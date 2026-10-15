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
