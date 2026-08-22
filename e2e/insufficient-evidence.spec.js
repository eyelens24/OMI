const { test, expect } = require('@playwright/test');

test('every material loss has a stable snapshot and explanation when reselected', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button', { name: /run built-in test csv/i }).click();
  await expect(page.locator('#results')).toBeVisible({ timeout: 15000 });
  const markers = page.locator('.loss-marker');
  await expect(markers).toHaveCount(5);
  const seen = [];
  for (let index = 0; index < 5; index += 1) {
    await markers.nth(index).click();
    await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
    seen.push({
      snapshot: await page.locator('#snapshotIdentity').textContent(),
      flow: await page.locator('#branches').innerHTML(),
    });
  }
  for (let index = 0; index < 5; index += 1) {
    await markers.nth(index).click();
    await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
    expect(await page.locator('#snapshotIdentity').textContent()).toBe(seen[index].snapshot);
    expect(await page.locator('#branches').innerHTML()).toBe(seen[index].flow);
  }
  expect(errors).toEqual([]);
});
