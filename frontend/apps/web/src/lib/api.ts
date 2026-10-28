import { createApi } from "@colyv/api";
import { getAccessToken, renewSession } from "./session";

// Every call carries the in-memory access token. A refusal as signed-out renews it once and sends the call again.
export const api = createApi(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", getAccessToken, async () => ((await renewSession()) ? getAccessToken() : null));
