const { test, expect } = require('@playwright/test');

test('AI contradiction demo renders a complete ledger and provenance contradiction', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button', { name: /import ai contradiction demo/i }).click();
  await expect(page.locator('#results')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#ledgerPath .ledger-step')).toHaveCount(6);
  await expect(page.locator('#ledgerPath')).toContainText(/supported/);
  await expect(page.locator('#aiForensics')).toContainText(/contradicted/);
  await page.locator('#ledgerPath .ledger-step').nth(1).click();
  await expect(page.locator('#ledgerReceipt')).toBeVisible();
  expect(errors).toEqual([]);
});
