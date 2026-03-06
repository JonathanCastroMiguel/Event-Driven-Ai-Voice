import { test, expect } from "@playwright/test";

test.describe("Voice Client Page", () => {
  test("page loads with title and start button", async ({ page }) => {
    await page.goto("/");

    // Header shows app title
    await expect(
      page.getByRole("heading", { name: "Voice AI Client" }),
    ).toBeVisible();

    // Start Call button is visible and enabled
    const startButton = page.getByRole("button", { name: "Start Call" });
    await expect(startButton).toBeVisible();
    await expect(startButton).toBeEnabled();
  });

  test("shows status indicator", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Ready to start")).toBeVisible();
  });

  test("shows transcription panel placeholder", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Transcriptions will appear here during the call."),
    ).toBeVisible();
  });

  test("shows mic and agent indicators", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("You")).toBeVisible();
    await expect(page.getByText("Agent")).toBeVisible();
  });
});
