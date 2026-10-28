import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { ApiError, apiErrorFrom } from "./errors";
import type { Memo } from "./deals";
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

/** Every deal the person is in. Pilot scale: up to five pages of a hundred, then it stops. */
export const useDeals = () =>
  useQuery({
    queryKey: ["deals"],
    queryFn: async () => {
      const memos: Memo[] = [];
      let cursor: string | undefined;
      for (let page = 0; page < 5; page++) {
        const result = await unwrap(api.GET("/api/v1/deal-memos/mine", { params: { query: { limit: 100, cursor } } }));
        memos.push(...result.items);
        if (!result.next_cursor) break;
        cursor = result.next_cursor;
      }
      return memos;
    },
  });

/** The newest payments, each with its campaign, brand and creator, so a table needs no call per row. */
export const usePayments = () => useQuery({ queryKey: ["payments"], queryFn: async () => (await unwrap(api.GET("/api/v1/payments/mine", { params: { query: { limit: 100 } } }))).items });
