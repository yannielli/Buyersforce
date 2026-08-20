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
  Kevin commits file changes through the GitHub website; every commit auto-deploys on Railway.
- Database: Railway's managed Postgres (service "Postgres" in the `buyersforce` project).
  Do NOT switch back to SQLite or Railway volumes — volumes had an unresolved data-wiping bug.
- Kevin is the admin account. One email = one role (buyer, seller, or admin);
  he uses separate email addresses to test buyer and seller views.
- seed.py only seeds an empty database, so real data survives redeploys. Never break that guard.
