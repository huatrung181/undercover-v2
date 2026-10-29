import { vi } from "vitest";
import type { Claim, QueuedClaim } from "./api";

export type Routes = Record<string, unknown>;

/** Stub fetch with a JSON reply for each "METHOD url", or "url" for a GET. */
export function stubApi(routes: Routes) {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = method === "GET" ? url : `${method} ${url}`;
    if (!(key in routes)) {
      return Promise.resolve(
        Response.json({ detail: `No route ${key}` }, { status: 404 }),
      );
    }
    return Promise.resolve(Response.json(routes[key]));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

export const queued: QueuedClaim = {
  claim_id: "CLM-1001",
  claim_type: "trip_delay",
  summary: "Flight home canceled",
  customer_name: "Maya Patel",
  submitted_on: "2026-06-24",
  amount_claimed: 420,
  status: "waiting",
  decision: null,
  payout: null,
};

export const claim: Claim = {
  claim_id: "CLM-1001",
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled",
  story: "My flight home from Rome was canceled.",
  items: [
    { description: "Airport hotel", category: "accommodation", amount: 245 },
  ],
  amount_claimed: 245,
  documents: [
    { name: "Hotel receipt", type: "receipt", content: "Total paid: $245.00." },
  ],
  status: "waiting",
  decision: null,
  payment: null,
  sign_off: null,
};
