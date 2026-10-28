import createClient from "openapi-fetch";
import type { paths } from "./schema";

export type { paths, components } from "./schema";

/**
 * One typed client for the whole API. Types come from docs/api/openapi.json, never typed by hand.
 * `renewToken`, when given, is called once if a request is refused as signed-out; the request is then sent again with the new token.
 */
export function createApi(baseUrl: string, getToken: () => string | null, renewToken?: () => Promise<string | null>) {
  const client = createClient<paths>({ baseUrl });
  const originals = new WeakMap<Request, Request>();
  client.use({
    onRequest({ request }) {
      const token = getToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      if (renewToken) originals.set(request, request.clone());
      return request;
    },
    async onResponse({ request, response }) {
      if (response.status !== 401 || !renewToken) return undefined;
      const original = originals.get(request);
      if (!original) return undefined;
      const token = await renewToken();
      if (!token) return undefined;
      original.headers.set("Authorization", `Bearer ${token}`);
      return fetch(original);
    },
  });
  return client;
}
