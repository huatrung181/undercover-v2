import { expect, type Page, test } from "@playwright/test";

async function runAgent(page: Page, claimId: string) {
  await page.goto(`/#/claims/${claimId}`);
  await page.getByRole("button", { name: "Run the agent" }).click();
  await expect(page.locator(".title-row")).toContainText("In progress");
  await expect(
    page.getByText(`get_claim({"claim_id": "${claimId}"})`),
  ).toBeVisible();
}

test("the queue shows every claim", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Claims queue" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(25);
  await page.getByRole("link", { name: "CLM-1004" }).click();
  await expect(page.getByRole("heading", { name: /CLM-1004/ })).toBeVisible();
  await expect(page.getByText("No decision yet.")).toBeVisible();
});

test("the agent decides a claim and pays it", async ({ page }) => {
  await runAgent(page, "CLM-1001");
  await expect(page.locator(".title-row")).toContainText("Decided");
  await expect(page.locator(".verdict")).toHaveText("Approved $420.00");
  await expect(page.getByText("Paid $420.00.")).toBeVisible();
  await expect(page.getByText("Claim CLM-1001 is done.")).toBeVisible();
  await page.getByRole("link", { name: "Back to the queue" }).click();
  const row = page.getByRole("row", { name: /CLM-1001/ });
  await expect(row).toContainText("Decided");
  await expect(row).toContainText("Approved");
});

test("a payout over $1,000 waits for a handler's sign-off", async ({
  page,
}) => {
  await runAgent(page, "CLM-1002");
  await expect(
    page.getByText("Payment waiting for a handler's sign-off."),
  ).toBeVisible();
  await expect(page.locator(".title-row")).toContainText(
    "Waiting for sign-off",
  );
  await expect(
    page.getByText(
      "pay_claim: Refused (403): A payout over $1,000.00 waits for a handler's sign-off",
    ),
  ).toBeVisible();
  await page.getByLabel("Handler").selectOption("Dana Whitfield");
  await page
    .getByRole("button", { name: "Sign off and pay $1,150.00" })
    .click();
  await expect(
    page.getByText("Paid $1,150.00 after sign-off by Dana Whitfield."),
  ).toBeVisible();
  await expect(page.locator(".title-row")).toContainText("Decided");
});

test("a declined claim is not paid", async ({ page }) => {
  await runAgent(page, "CLM-1005");
  await expect(page.locator(".verdict")).toHaveText("Declined");
  await expect(page.locator(".title-row")).toContainText("Decided");
  await expect(page.getByText(/^Paid/)).toHaveCount(0);
});

test("the agent's instructions are shown read only", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Agent instructions" }).click();
  await expect(page.getByText(/^You are the UnderCover Agent\./)).toBeVisible();
  await expect(page.locator("textarea, input")).toHaveCount(0);
});
