import { test, expect } from "@playwright/test";
test("configure, explore, inspect, replay, and validate a map", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Simulation studio/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Configure scenario", exact: true })
    .click();
  await page.getByLabel("Grid width", { exact: true }).fill("16");
  await page.getByLabel("Grid height", { exact: true }).fill("16");
  await page
    .getByRole("combobox", { name: "Allocation strategy", exact: true })
    .selectOption("independent");
  await page
    .getByRole("button", { name: "Generate environment", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Single step", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Resume exploration", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Inspect agent 2", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Inspect internal map", exact: true })
    .click();
  await expect(page.getByLabel("Knowledge view")).toHaveValue("agent");
  await page
    .getByRole("button", { name: "Resume exploration", exact: true })
    .click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Resume exploration", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Replay tick", { exact: true }).press("Home");
  await expect(
    page.getByText("Recorded tick 0", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Live", exact: true }).click();
  await page
    .getByRole("button", { name: "Stop simulation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Scenario builder", exact: true })
    .click();
  await page
    .getByLabel("Scenario name", { exact: true })
    .fill("Browser test map");
  await page
    .getByRole("button", { name: "Validate & save", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Simulation studio/ }),
  ).toBeVisible();
});
