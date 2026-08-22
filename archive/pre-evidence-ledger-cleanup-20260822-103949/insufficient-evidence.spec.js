const { test, expect } = require('@playwright/test');

test('an early loss never inherits a later event explanation', async ({ page }) => {
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button', { name: /run built-in test csv/i }).click();
  await expect(page.locator('#results')).toBeVisible({ timeout: 15000 });
  const markers = page.locator('.loss-marker');
  await expect(markers).toHaveCount(5);

  await markers.nth(4).click();
  await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
  await markers.nth(0).click();
  await expect(page.locator('#timelineStatus')).toContainText(/Need 50 prior marks/);
  await expect(page.locator('#branches')).toContainText(/NO COMPLETE FLOW YET/);
  await expect(page.locator('#snapshotIdentity')).toHaveText('—');
});
