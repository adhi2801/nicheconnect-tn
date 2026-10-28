"use client";

import { useSyncExternalStore } from "react";
import { getServerSessionState, getSessionState, subscribeToSession, type SessionState } from "./session";

/** The signed-in state of this tab. The server never has one, so it always renders "restoring". */
export const useSession = (): SessionState => useSyncExternalStore(subscribeToSession, getSessionState, getServerSessionState);
