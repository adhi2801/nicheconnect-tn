# Colyv frontend

Lives in the same repository as the backend (`nicheconnect-tn`), under `frontend/`. The two meet at the API contract, `docs/api/openapi.json` at the repository root.

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
