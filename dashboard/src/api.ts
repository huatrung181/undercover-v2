export type Status =
  "waiting" | "in_progress" | "awaiting_sign_off" | "decided";
export type Verdict = "approve" | "decline" | "refer";

export interface QueuedClaim {
  claim_id: string;
  claim_type: string;
  summary: string;
  customer_name: string;
  submitted_on: string;
  amount_claimed: number;
  status: Status;
  decision: Verdict | null;
  payout: number | null;
}

export interface Claim {
  claim_id: string;
  policy_id: string;
  customer_id: string;
  claim_type: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  summary: string;
  story: string;
  items: { description: string; category: string; amount: number }[];
  amount_claimed: number;
  documents: { name: string; type: string; content: string }[];
  status: Status;
  decision: {
    decision: Verdict;
    payout: number;
    reason: string;
    policy_section: string;
    decided_at: string;
  } | null;
  payment: { amount: number; paid_at: string } | null;
  sign_off: { handler_id: string; signed_at: string } | null;
}

export interface Policy {
  policy_id: string;
  plan: string;
  purchased_on: string;
  trip: {
    destination: string;
    departs_on: string;
    returns_on: string;
    trip_cost: number;
  };
  travelers: string[];
  plan_details: { name: string };
  add_on_details: { add_on: string; name: string }[];
}

export interface Step {
  id: number;
  thread_id: string;
  kind: "model" | "tool_call" | "tool_result" | "error";
  text: string;
  created_at: string;
}

export interface Handler {
  handler_id: string;
  name: string;
  role: string;
  can_approve_over_limit: boolean;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const { detail } = (await response.json()) as { detail: string };
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function post<T>(url: string, body?: object): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export const listClaims = () => request<QueuedClaim[]>("/api/claims");
export const getClaim = (id: string) => request<Claim>(`/api/claims/${id}`);
export const getPolicy = (id: string) => request<Policy>(`/api/policies/${id}`);
export const listSteps = (id: string) =>
  request<Step[]>(`/api/claims/${id}/steps`);
export const listHandlers = () => request<Handler[]>("/api/handlers");
export const getInstructions = () =>
  request<{ instructions: string }>("/api/instructions");
export const runAgent = (id: string) =>
  post<{ thread_id: string }>(`/api/claims/${id}/runs`);
export const signOff = (id: string, handlerId: string) =>
  post<{ status: Status }>(`/api/claims/${id}/sign-off`, {
    handler_id: handlerId,
  });
