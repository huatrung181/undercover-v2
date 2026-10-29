import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { label, money } from "./format";
import { parseRoute } from "./hooks";
import { queued, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

it("shows the queue with counts by status", async () => {
  stubApi({
    "/api/claims": [
      queued,
      {
        ...queued,
        claim_id: "CLM-1002",
        status: "awaiting_sign_off",
        decision: "approve",
        amount_claimed: 1150,
        payout: 1150,
      },
      {
        ...queued,
        claim_id: "CLM-1003",
        status: "decided",
        decision: "refer",
        payout: 0,
      },
    ],
  });
  render(<App />);
  const row = (await screen.findByText("CLM-1002")).closest("tr");
  if (!row) throw new Error("no row for CLM-1002");
  expect(within(row).getByText("Waiting for sign-off")).toBeDefined();
  expect(within(row).getByText("Approved")).toBeDefined();
  expect(within(row).getAllByText("$1,150.00")).toHaveLength(2);
  expect(screen.getByText("Referred")).toBeDefined();
  const tiles = screen.getByLabelText("Claims by status");
  expect(tiles.textContent).toBe(
    "1Waiting0In progress1Waiting for sign-off1Decided",
  );
  expect(screen.getByText("CLM-1001").getAttribute("href")).toBe(
    "#/claims/CLM-1001",
  );
});

it("says when the backend is not responding", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);
  expect(
    await screen.findByText("The backend is not responding."),
  ).toBeDefined();
});

it("shows the agent's instructions", async () => {
  stubApi({
    "/api/instructions": { instructions: "You are the UnderCover Agent." },
  });
  window.location.hash = "#/instructions";
  render(<App />);
  expect(
    await screen.findByText("You are the UnderCover Agent."),
  ).toBeDefined();
  expect(
    screen
      .getByText("Agent instructions", { selector: "a" })
      .getAttribute("aria-current"),
  ).toBe("page");
});

it("follows the hash", async () => {
  stubApi({
    "/api/claims": [queued],
    "/api/instructions": { instructions: "The instructions." },
  });
  render(<App />);
  expect(await screen.findByText("Claims queue")).toBeDefined();
  window.location.hash = "#/instructions";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByText("The instructions.")).toBeDefined();
});

it("parses routes", () => {
  expect(parseRoute("")).toEqual({ page: "queue" });
  expect(parseRoute("#/claims/CLM-1001")).toEqual({
    page: "claim",
    claimId: "CLM-1001",
  });
  expect(parseRoute("#/instructions")).toEqual({ page: "instructions" });
  expect(parseRoute("#/elsewhere")).toEqual({ page: "queue" });
});

it("formats money and labels", () => {
  expect(money(1250)).toBe("$1,250.00");
  expect(label("trip_delay")).toBe("Trip delay");
});
