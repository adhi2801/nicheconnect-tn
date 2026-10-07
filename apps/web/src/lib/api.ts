import { createApi } from "@colyv/api";

// The access token lives in memory only (docs/standards/frontend.md section 7): never localStorage.
let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { accessToken = t; };

export const api = createApi(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", () => accessToken);
