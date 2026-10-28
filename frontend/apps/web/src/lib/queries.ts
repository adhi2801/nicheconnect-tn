import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { ApiError, apiErrorFrom } from "./errors";
import type { Role } from "./session";

// Server data lives in one query cache (docs/standards/frontend.md section 9). Each screen asks for what it shows, and nothing here
// is copied into another store. A failed call becomes an ApiError that says what kind of failure it was.
async function unwrap<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await request;
  } catch {
    throw new ApiError("network");
  }
  if (result.data !== undefined) return result.data;
  throw apiErrorFrom(result.response, result.error);
}

export type Profile = { found: true; name: string } | { found: false };

/** The person's own profile. A new account has none yet (404), which is a state and not an error. */
export function useProfile(role: Role) {
  return useQuery({
    queryKey: ["profile", role],
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<Profile> => {
      try {
        if (role === "creator") return { found: true, name: (await unwrap(api.GET("/api/v1/creators/me"))).display_name };
        return { found: true, name: (await unwrap(api.GET("/api/v1/brands/me"))).name };
      } catch (error) {
        if (error instanceof ApiError && error.kind === "not_found") return { found: false };
        throw error;
      }
    },
  });
}

/** What is waiting on the person, most urgent first. Worked out fresh each time, so it also refreshes when the tab regains focus. */
export const useAttention = () => useQuery({ queryKey: ["attention"], queryFn: () => unwrap(api.GET("/api/v1/me/attention")) });

export const usePaymentTotals = () => useQuery({ queryKey: ["payment-totals"], queryFn: () => unwrap(api.GET("/api/v1/payments/mine/totals")) });

export const useUnreadCount = () =>
  useQuery({ queryKey: ["unread"], queryFn: () => unwrap(api.GET("/api/v1/notifications/unread-count")), refetchInterval: 60_000, refetchIntervalInBackground: false });
