import { ApiError, apiErrorFrom, retryDelayMs } from "./errors.ts";

// Every write carries an Idempotency-Key (D-040, frontend.md section 5), so a retry after a dropped connection or a busy backend can
// never apply twice: the backend answers the second try with the first one's result.
//
// One key per intent. The same body sent again (a double tap, a retry) keeps its key; a changed body is a new intent and gets a new
// key, because the backend refuses a key reused with a different body (idempotency_key_reused).

/** One try of the write. It must pass `signal` to the request, so a stalled connection is given up on. */
export type Attempt<T> = (signal: AbortSignal) => Promise<{ data?: T; error?: unknown; response: Response }>;

/** How long one try may take before it is given up as a lost connection (frontend.md section 5: every request has a timeout). */
export const WRITE_TIMEOUT_MS = 20_000;

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

type Options = { sleep?: (ms: number) => Promise<void>; random?: () => number; maxBusyRetries?: number; timeoutMs?: number };

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Sends a write. It retries, with the same key, at most three times after Retry-After plus jitter, only when trying again is
 * certainly right: the backend is busy (503 `service_busy`), or an earlier try with this key is still being worked on (409
 * `idempotency_key_in_flight`, which then answers with that try's result). A 429 is the person's own pace and is never retried.
 * A dropped or stalled connection (each try gives up after `timeoutMs`) becomes ApiError("network"): the person retries, with the
 * same key, so nothing is applied twice.
 */
export async function sendWrite<T>(attempt: Attempt<T>, options: Options = {}): Promise<T> {
  return (await sendWriteWithStatus(attempt, options)).data;
}

/** As sendWrite, also giving the answer's status, for writes whose 200 and 201 mean different things (a report already open). */
export async function sendWriteWithStatus<T>(attempt: Attempt<T>, { sleep = wait, random = Math.random, maxBusyRetries = 3, timeoutMs = WRITE_TIMEOUT_MS }: Options = {}): Promise<{ data: T; status: number }> {
  for (let tries = 0; ; tries++) {
    let result: Awaited<ReturnType<Attempt<T>>>;
    try {
      result = await attempt(AbortSignal.timeout(timeoutMs));
    } catch {
      throw new ApiError("network");
    }
    if (result.data !== undefined) return { data: result.data, status: result.response.status };
    const error = apiErrorFrom(result.response, result.error);
    const tryAgain = error.kind === "busy" || error.code === "idempotency_key_in_flight";
    if (!tryAgain || tries >= maxBusyRetries) throw error;
    await sleep(retryDelayMs(error, random));
  }
}
