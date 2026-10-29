import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Claim, Step } from "./api";
import { ClaimPage } from "./ClaimPage";
import { claim, Refusal, type Routes, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const policy = {
  policy_id: "POL-2001",
  plan: "premium",
  purchased_on: "2026-04-22",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
  plan_details: { name: "UnderCover Premium" },
  add_on_details: [],
};

const handlers = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    can_approve_over_limit: true,
  },
];

const approved: Claim = {
  ...claim,
  status: "decided",
  decision: {
    decision: "approve",
    payout: 245,
    reason: "The delay is covered.",
    policy_section: "Section 3, Trip Delay",
    decided_at: "2026-10-29T14:30:00+00:00",
  },
  payment: { amount: 245, paid_at: "2026-10-29T14:31:00+00:00" },
};

const waitingForSignOff: Claim = {
  ...approved,
  status: "awaiting_sign_off",
  decision: approved.decision && { ...approved.decision, payout: 1150 },
  payment: null,
};

function show(found: Claim, steps: Step[] = [], extra: Routes = {}) {
  const fetch = stubApi({
    "/api/claims/CLM-1001": found,
    "/api/claims/CLM-1001/steps": steps,
    "/api/policies/POL-2001": policy,
    "/api/handlers": handlers,
    ...extra,
  });
  render(<ClaimPage claimId="CLM-1001" />);
  return fetch;
}

it("shows a waiting claim with its policy and runs the agent", async () => {
  const fetch = show(claim, [], {
    "POST /api/claims/CLM-1001/runs": { thread_id: "CLM-1001-1" },
  });
  expect(
    await screen.findByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  expect(screen.getByText("Airport hotel")).toBeDefined();
  expect(screen.getByText("Total paid: $245.00.")).toBeDefined();
  expect(await screen.findByText("UnderCover Premium")).toBeDefined();
  expect(screen.getByText("None")).toBeDefined();
  expect(screen.getByText("No decision yet.")).toBeDefined();
  expect(
    screen.getByText("The agent has not worked on this claim yet."),
  ).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Run the agent" }));
  await vi.waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/claims/CLM-1001/runs",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

it("says why the agent could not start", async () => {
  show(claim, [], {
    "POST /api/claims/CLM-1001/runs": new Refusal(
      409,
      "CLM-1001 must be waiting to run the agent",
    ),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Run the agent" }));
  expect(
    await screen.findByText("CLM-1001 must be waiting to run the agent"),
  ).toBeDefined();
});

it("shows the agent's steps while it works", async () => {
  const step = { thread_id: "t", created_at: "2026-10-29T14:30:00+00:00" };
  show({ ...claim, status: "in_progress" }, [
    { ...step, id: 1, kind: "tool_call", text: 'get_claim({"claim_id": "1"})' },
    { ...step, id: 2, kind: "model", text: "Thinking it over." },
    { ...step, id: 3, kind: "error", text: "The agent stopped." },
  ]);
  expect(await screen.findByText('get_claim({"claim_id": "1"})')).toBeDefined();
  expect(screen.getByText("Tool call")).toBeDefined();
  expect(screen.getByText("Thinking it over.")).toBeDefined();
  expect(screen.getByText("Error")).toBeDefined();
  expect(screen.getByText("The agent is working on this claim.")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Run the agent" })).toBeNull();
});

it("shows an approved and paid claim", async () => {
  show(approved);
  expect(await screen.findByText("Approved")).toBeDefined();
  expect(screen.getByText("The delay is covered.")).toBeDefined();
  expect(screen.getByText("Section 3, Trip Delay")).toBeDefined();
  expect(screen.getByText(/^Paid/).textContent).toBe("Paid $245.00.");
});

it("shows a declined claim with no payment", async () => {
  show({
    ...approved,
    decision: approved.decision && {
      ...approved.decision,
      decision: "decline",
      payout: 0,
    },
    payment: null,
  });
  expect(await screen.findByText("Declined")).toBeDefined();
  expect(screen.queryByText(/^Paid/)).toBeNull();
});

it("signs off a payout over the limit", async () => {
  const fetch = show(waitingForSignOff, [], {
    "POST /api/claims/CLM-1001/sign-off": { status: "decided" },
  });
  expect(
    await screen.findByText("Payment waiting for a handler's sign-off."),
  ).toBeDefined();
  const button = screen.getByRole("button", {
    name: "Sign off and pay $1,150.00",
  });
  expect(button.hasAttribute("disabled")).toBe(true);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(button);
  await vi.waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/claims/CLM-1001/sign-off",
      expect.objectContaining({ body: '{"handler_id":"HND-01"}' }),
    );
  });
});

it("says why a sign-off was refused", async () => {
  show(waitingForSignOff, [], {
    "POST /api/claims/CLM-1001/sign-off": new Refusal(403, "Not allowed"),
  });
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^Sign off/ }));
  expect(await screen.findByText("Not allowed")).toBeDefined();
});

it("shows who signed off", async () => {
  show({
    ...waitingForSignOff,
    status: "decided",
    payment: { amount: 1150, paid_at: "2026-10-29T15:00:00+00:00" },
    sign_off: { handler_id: "HND-01", signed_at: "2026-10-29T15:00:00+00:00" },
  });
  await vi.waitFor(() => {
    expect(screen.getByText(/^Paid/).textContent).toBe(
      "Paid $1,150.00 after sign-off by Dana Whitfield.",
    );
  });
});

it("says when the claim cannot be found", async () => {
  stubApi({});
  render(<ClaimPage claimId="CLM-9999" />);
  expect(
    await screen.findByText("No route /api/claims/CLM-9999"),
  ).toBeDefined();
});
