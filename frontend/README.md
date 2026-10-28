# Colyv frontend

Lives in the same repository as the backend (`nicheconnect-tn`), under `frontend/`. The two meet at the API contract, `docs/api/openapi.json` at the repository root.

**Open decisions (not yet approved by both founders):** where this code lives and which framework the apps use (Flutter is what exists here; Adhi's locked baseline, D-047, is Expo). See `docs/PROPOSAL_FRONTEND_HOME_AND_STACK.md`. The plan: `design/screen-plan.md` (every screen) and `design/execution-plan.md` (dates, pace with the backend). Run `pnpm api:changes` each Monday.

| Part | What | Status |
|---|---|---|
| `apps/web` | The website (Next.js, TypeScript, Tailwind). One site; a creator and a brand each see their own screens after login. | Foundation builds |
| `apps/mobile` | The app (Flutter). One app, same role split. | Not created: Flutter is not installed on this machine yet |
| `../docs/api/openapi.json` | The backend's committed API contract. The frontend reads it directly; never edit it from here. | Source of truth |
| `packages/api` | Typed client generated from `../docs/api/openapi.json` (`pnpm api:types`). | Generated |
| `tokens/tokens.json` | The one source of colour, spacing, radius, motion and type. `pnpm tokens` writes CSS for the site and Dart for the app. Values are placeholders until the designer's brandbook arrives. | Placeholder values |

## Commands

    pnpm install
    pnpm api:types
    pnpm tokens
    pnpm web                 # http://localhost:3000
    pnpm build
    pnpm lint

## Rules carried over from the backend repository

- English only. Words come from message files, never typed into a screen.
- A screen that needs a field the API does not return is a backend request, not a frontend decision.
- Money is whole paise on the wire and rupees with Indian digit grouping on screen.
- Payment wording is facts only: "marked paid", "confirmed received", "disputed". Never language about holding or protecting money.
- The access token lives in memory, never in localStorage.
- The backend must list the site's address in `CORS_ALLOWED_ORIGINS` for the browser to call it.
- Standards: `docs/standards/frontend.md` and `ux.md` in the backend repository.

## Sign-in and the session (website)

- The **access token** (15 minutes) lives in the page's memory only. The **refresh token** (30 days) lives in an `httpOnly`, `SameSite=Strict` cookie, set and read only by the three routes under `apps/web/src/app/api/session` (`verify`, `refresh`, `logout`). The page's scripts can never read it, so a stolen script cannot steal a long-lived login. This is what `docs/standards/frontend.md` section 10 asks for.
- A reload asks `/api/session/refresh` for a new access token. Renewals take turns across tabs (a Web Lock), because the backend ends every login when a refresh token is presented twice.
- Signing out in one tab signs out every tab.

**What this needs from the backend side** (not changes to the API itself):
1. The website's server runs as a server, not as static files, because the session routes run on it.
2. `TRUSTED_PROXIES` must include the website's server, so the backend's per-address limits (3 login codes per 10 minutes per address) count the person and not the website. The routes pass `X-Forwarded-For` on.
3. `CORS_ALLOWED_ORIGINS` must list the website's address for the calls the browser makes directly.

## Checks

    pnpm test        # unit tests (Node's built-in runner)
    pnpm e2e         # browser tests: builds the site, starts a stand-in for the login endpoints, drives Chrome
    pnpm lint
    pnpm build

