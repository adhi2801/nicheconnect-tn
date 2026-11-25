import { ApiError, apiErrorFrom, retryDelayMs } from "./errors.ts";

// Every write carries an Idempotency-Key (D-040, frontend.md section 5), so a retry after a dropped connection or a busy backend can
// never apply twice: the backend answers the second try with the first one's result.
//
// One key per intent. The same body sent again (a double tap, a retry) keeps its key; a changed body is a new intent and gets a new
// key, because the backend refuses a key reused with a different body (idempotency_key_reused).

export type Attempt<T> = () => Promise<{ data?: T; error?: unknown; response: Response }>;

/** A key the backend accepts: long, random, unguessable. */
export const newIdempotencyKey = (): string => crypto.randomUUID();

export class IntentKeys {
  private held: { body: string; key: string } | null = null;
  private readonly make: () => string;

  // A plain field, not a parameter property: Node's test runner strips types and cannot run that TypeScript-only syntax.
  constructor(make: () => string = newIdempotencyKey) {
    this.make = make;
  }

  /** The key for this body: the same as last time if the body is unchanged, a new one otherwise. */
  keyFor(body: unknown): string {
    const serial = JSON.stringify(body ?? null);
    if (this.held?.body !== serial) this.held = { body: serial, key: this.make() };
    return this.held.key;
  }

  /** After a success the intent is done: the next write, even with the same body, is a new one. */
  done(): void {
    this.held = null;
  }
}

type Options = { sleep?: (ms: number) => Promise<void>; random?: () => number; maxBusyRetries?: number };

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Sends a write, retrying only a busy backend (503 `service_busy`): it waits what Retry-After asked plus jitter, at most three times,
 * repeating the same request with the same key. A 429 is the person's own pace and is never retried. A dropped connection becomes
 * ApiError("network"): the person retries, with the same key, so nothing is applied twice.
 */
export async function sendWrite<T>(attempt: Attempt<T>, { sleep = wait, random = Math.random, maxBusyRetries = 3 }: Options = {}): Promise<T> {
  for (let tries = 0; ; tries++) {
    let result: Awaited<ReturnType<Attempt<T>>>;
    try {
      result = await attempt();
    } catch {
      throw new ApiError("network");
    }
    if (result.data !== undefined) return result.data;
    const error = apiErrorFrom(result.response, result.error);
    if (error.kind !== "busy" || tries >= maxBusyRetries) throw error;
    await sleep(retryDelayMs(error, random));
  }
}
