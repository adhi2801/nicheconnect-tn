# Colyv frontend

Separate from the backend repository (`nicheconnect-tn`). The two meet only at the API contract.

| Part | What | Status |
|---|---|---|
| `apps/web` | The website (Next.js, TypeScript, Tailwind). One site; a creator and a brand each see their own screens after login. | Foundation builds |
| `apps/mobile` | The app (Flutter). One app, same role split. | Not created: Flutter is not installed on this machine yet |
| `contract/openapi.json` | Copy of the backend's committed API contract. Never edit it here; run `pnpm contract:sync`. `contract/SOURCE.txt` says which backend commit it came from. | Synced from `040c6e3` |
| `packages/api` | Typed client generated from the contract (`pnpm api:types`). | Generated |
| `tokens/tokens.json` | The one source of colour, spacing, radius, motion and type. `pnpm tokens` writes CSS for the site and Dart for the app. Values are placeholders until the designer's brandbook arrives. | Placeholder values |

## Commands

    pnpm install
    pnpm contract:sync       # BACKEND=/path/to/nicheconnect-tn if it is not in your home folder
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
